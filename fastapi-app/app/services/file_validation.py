from __future__ import annotations

import asyncio
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


async def validate_document(file: UploadFile, ext: str) -> None:
    validator = _validate_pdf if ext == "pdf" else _validate_docx
    await asyncio.to_thread(validator, file.file)
