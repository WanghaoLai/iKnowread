"""Run the production OCR command against an image-only PDF.

This is intentionally an executable release check instead of a package/version
check: it covers the OCRmyPDF CLI, Tesseract language data, PDF rasterization,
temporary-file permissions and text-layer generation together.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pypdfium2
from PIL import Image, ImageDraw, ImageFont

from app.services import ocr_service


EXPECTED_TEXT = "OCR RUNTIME CHECK 12345"


def _font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), 72)
    return ImageFont.load_default()


def _make_image_pdf(path: Path) -> None:
    image = Image.new("RGB", (1800, 500), "white")
    ImageDraw.Draw(image).text((90, 180), EXPECTED_TEXT, font=_font(), fill="black")
    image.save(path, "PDF", resolution=200.0)


def _extract_text(path: Path) -> str:
    document = pypdfium2.PdfDocument(path)
    try:
        page = document[0]
        try:
            text_page = page.get_textpage()
            try:
                return text_page.get_text_range()
            finally:
                text_page.close()
        finally:
            page.close()
    finally:
        document.close()


async def _check() -> None:
    with tempfile.TemporaryDirectory(prefix="iknowread-ocr-check-") as directory:
        source = Path(directory) / "image-only.pdf"
        output = Path(directory) / "searchable.pdf"
        _make_image_pdf(source)
        return_code, stderr = await ocr_service._run_command(source, output)
        if return_code != 0:
            raise RuntimeError(f"OCR command failed with exit code {return_code}: {stderr[-1000:]}")
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("OCR command did not create a non-empty PDF")
        extracted = " ".join(_extract_text(output).upper().split())
        if "OCR" not in extracted or "12345" not in extracted:
            raise RuntimeError(f"OCR text layer is missing expected text: {extracted!r}")


if __name__ == "__main__":
    asyncio.run(_check())
    print("OCR runtime check passed")
