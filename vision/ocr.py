"""Thin Tesseract OCR wrapper for ASC (task #20).

Reuses the same config resolution order as agents/vision_agent.py
(config vision.tesseract_path -> PATH -> Program Files default) so both
paths agree on which Tesseract binary is used. No business logic here —
just text extraction from PIL images or image files.
"""

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union

from loguru import logger

try:
    import pytesseract
    from PIL import Image
    OCR_LIBS_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on env
    OCR_LIBS_AVAILABLE = False

_DEFAULT_WINDOWS_PATH = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def resolve_tesseract_cmd(config_path: str = "./config/settings.json") -> Optional[str]:
    """Resolve the tesseract executable path.

    Order: config vision.tesseract_path -> shutil.which -> Program Files default.
    Returns None when nothing is found.
    """
    try:
        from core.config import load_config

        config = load_config(config_path)
    except Exception:
        config = {}

    configured = config.get("vision", {}).get("tesseract_path")
    if configured and Path(configured).exists():
        return configured

    located = shutil.which("tesseract")
    if located:
        return located

    if _DEFAULT_WINDOWS_PATH.exists():
        return str(_DEFAULT_WINDOWS_PATH)

    return None


class OCREngine:
    """Minimal Tesseract text-extraction wrapper."""

    def __init__(self, config_path: str = "./config/settings.json"):
        self.config_path = config_path
        self._cmd = None
        self.available = False
        if OCR_LIBS_AVAILABLE:
            self._cmd = resolve_tesseract_cmd(config_path)
            if self._cmd:
                pytesseract.pytesseract.tesseract_cmd = self._cmd
                self.available = self._check_version()

    def _check_version(self) -> bool:
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception as exc:
            logger.warning("Tesseract not usable at {}: {}", self._cmd, exc)
            return False

    def extract_text(
        self,
        image: Union["Image.Image", str, None] = None,
        lang: str = "eng",
    ) -> Dict[str, Any]:
        """Extract text from a PIL image or an image file path.

        Captures the screen first when no source is provided.
        """
        if not OCR_LIBS_AVAILABLE:
            return {"success": False, "error": "pytesseract/Pillow are not installed."}
        if not self.available:
            return {"success": False, "error": "Tesseract OCR is not available."}

        try:
            if image is None:
                from vision.screen_capture import ScreenCaptureService

                capture = ScreenCaptureService(self.config_path).capture(save=False)
                if not capture.get("success"):
                    return {"success": False, "error": capture.get("error")}
                image = Image.open(capture["file_path"]) if capture.get("file_path") else None
                if image is None:
                    # capture() without save returns no path; re-grab directly
                    from PIL import ImageGrab

                    image = ImageGrab.grab()
            elif isinstance(image, (str, Path)):
                image = Image.open(image)

            text = pytesseract.image_to_string(image, lang=lang)
            return {
                "success": True,
                "text": text,
                "char_count": len(text.strip()),
            }
        except Exception as exc:
            logger.error("OCR extraction failed: {}", str(exc))
            return {"success": False, "error": str(exc)}


if __name__ == "__main__":
    engine = OCREngine()
    print("available:", engine.available)
    result = engine.extract_text()
    print(result.get("text", result.get("error"))[:500])
