"""Task #20 regression tests: vision/screen_capture.py + vision/ocr.py.

No live-screen dependency for CI safety: capture tests are skipped when
Pillow/ImageGrab cannot run headless; OCR is tested with a synthetic image.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vision.screen_capture import ScreenCaptureService
from vision.ocr import OCREngine, resolve_tesseract_cmd


@pytest.fixture(scope="module")
def service():
    return ScreenCaptureService(
        str(Path(__file__).resolve().parent.parent / "config" / "settings.json")
    )


def test_screenshots_dir_created_under_data(service):
    assert service.screenshots_dir.exists()
    assert "screenshots" in str(service.screenshots_dir)


def test_capture_returns_metadata_and_saves(service):
    result = service.capture(save=True)
    if not result.get("success"):
        pytest.skip(f"ImageGrab unavailable in this environment: {result.get('error')}")
    assert result["width"] > 0 and result["height"] > 0
    assert "file_path" in result
    path = Path(result["file_path"])
    assert path.exists() and path.stat().st_size > 0
    assert path.parent == service.screenshots_dir.resolve()
    # cleanup test artifact
    path.unlink(missing_ok=True)


def test_latest_screenshot_tracking(service):
    result = service.capture(save=True)
    if not result.get("success"):
        pytest.skip("ImageGrab unavailable in this environment")
    latest = service.latest_screenshot()
    assert latest is not None and latest.exists()
    latest.unlink(missing_ok=True)


def test_ocr_resolution_order_does_not_crash(tmp_path):
    # Empty config file -> falls through to which()/default; must return str or None
    cfg = tmp_path / "settings.json"
    cfg.write_text("{}", encoding="utf-8")
    resolved = resolve_tesseract_cmd(str(cfg))
    assert resolved is None or Path(resolved).exists()


def test_ocr_extract_from_synthetic_image():
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw, ImageFont

    engine = OCREngine(
        str(Path(__file__).resolve().parent.parent / "config" / "settings.json")
    )
    if not engine.available:
        pytest.skip("Tesseract not installed in this environment")

    img = Image.new("RGB", (300, 80), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except OSError:
        font = ImageFont.load_default()
    draw.text((10, 20), "ASC TEST 123", fill="black", font=font)

    result = engine.extract_text(img)
    assert result["success"] is True
    assert "123" in result["text"]


def test_ocr_handles_missing_file_gracefully():
    engine = OCREngine(
        str(Path(__file__).resolve().parent.parent / "config" / "settings.json")
    )
    result = engine.extract_text(r"Z:\nonexistent\image.png")
    assert result["success"] is False
    assert "error" in result
