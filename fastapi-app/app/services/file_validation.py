from __future__ import annotations

import asyncio
import codecs
import zipfile

import pypdfium2
from fastapi import UploadFile

from app.common.exception_handler import CustomException
from app.config import settings


def _validate_pdf(stream) -> None:
    stream.seek(0)
    header = stream.read(1024)
    if not header.startswith(b"%PDF-"):
        raise CustomException("文件内容不是有效 PDF")
    stream.seek(0)
    try:
        document = pypdfium2.PdfDocument(stream, autoclose=False)
        try:
            pages = len(document)
            if pages < 1:
                raise CustomException("PDF 没有可读取的页面")
            if pages > max(1, settings.PDF_MAX_PAGES):
                raise CustomException(f"PDF 页数不能超过 {settings.PDF_MAX_PAGES} 页", status_code=413)
        finally:
            document.close()
    except CustomException:
        raise
    except Exception as exc:
        raise CustomException("PDF 结构无效、已损坏或需要密码") from exc
    finally:
        stream.seek(0)


def _validate_docx(stream) -> None:
    stream.seek(0)
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) > max(1, settings.DOCX_MAX_ENTRIES):
                raise CustomException("DOCX 内部文件数量过多", status_code=413)
            names = {entry.filename for entry in entries}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise CustomException("文件内容不是有效 DOCX")
            total = 0
            for entry in entries:
                if entry.flag_bits & 0x1:
                    raise CustomException("不支持加密的 DOCX")
                total += entry.file_size
                if total > max(1, settings.DOCX_MAX_UNCOMPRESSED_BYTES):
                    raise CustomException("DOCX 解压后内容过大", status_code=413)
                if entry.compress_size == 0 and entry.file_size > 0:
                    raise CustomException("DOCX 压缩结构异常")
                if entry.compress_size and entry.file_size / entry.compress_size > 200:
                    raise CustomException("DOCX 压缩比异常", status_code=413)
    except CustomException:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise CustomException("文件内容不是有效 DOCX") from exc
    finally:
        stream.seek(0)


def _validate_markdown(stream) -> None:
    """Require a bounded, well-formed UTF-8 text document.

    Markdown is stored verbatim and rendered by the browser. Validating it as
    text here prevents binary files from bypassing the document type boundary;
    active HTML is handled separately by the renderer's deny-by-default policy.
    """
    stream.seek(0)
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    has_content = False
    total = 0
    try:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            if total > max(1, settings.MARKDOWN_MAX_BYTES):
                raise CustomException(
                    f"Markdown 文件大小不能超过 {settings.MARKDOWN_MAX_BYTES // (1024 * 1024)}MB",
                    status_code=413,
                )
            text = decoder.decode(chunk)
            if any(ord(character) < 32 and character not in "\t\n\r" for character in text):
                raise CustomException("Markdown 文件包含无效控制字符")
            has_content = has_content or bool(text.strip())
        tail = decoder.decode(b"", final=True)
        if any(ord(character) < 32 and character not in "\t\n\r" for character in tail):
            raise CustomException("Markdown 文件包含无效控制字符")
        has_content = has_content or bool(tail.strip())
        if not has_content:
            raise CustomException("Markdown 文件内容为空")
    except UnicodeDecodeError as exc:
        raise CustomException("Markdown 文件必须使用 UTF-8 编码") from exc
    finally:
        stream.seek(0)


async def validate_document(file: UploadFile, ext: str) -> None:
    validators = {
        "pdf": _validate_pdf,
        "docx": _validate_docx,
        "md": _validate_markdown,
    }
    validator = validators.get(ext)
    if validator is None:
        raise CustomException("不支持的文件格式")
    await asyncio.to_thread(validator, file.file)
