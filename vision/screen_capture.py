"""Screen capture service for ASC (task #20).

Clean wrapper around PIL's ImageGrab. Captures the primary display,
saves PNGs under data/screenshots/, and returns the file path plus
metadata so callers never need to touch Pillow directly.
"""

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from core.config import load_config

try:
    from PIL import ImageGrab, Image
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on env
    PIL_AVAILABLE = False


class ScreenCaptureService:
    """Capture and persist screenshots of the primary display."""

    def __init__(self, config_path: str = "./config/settings.json"):
        self.config = load_config(config_path)
        self.screenshots_dir = (
            Path(self.config.get("paths", {}).get("data", "./data")) / "screenshots"
        )
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    @property
    def available(self) -> bool:
        return PIL_AVAILABLE

    def capture(self, save: bool = True) -> Dict[str, Any]:
        """Capture the screen.

        Returns a dict with success, file_path, width/height, timestamp,
        monitor info on success; success=False + error otherwise.
        """
        if not PIL_AVAILABLE:
            return {"success": False, "error": "Pillow is not installed."}

        try:
            image: "Image.Image" = ImageGrab.grab()
        except Exception as exc:
            logger.error("Screen capture failed: {}", str(exc))
            return {"success": False, "error": str(exc)}

        timestamp = datetime.now()
        result: Dict[str, Any] = {
            "success": True,
            "width": image.width,
            "height": image.height,
            "timestamp": timestamp.isoformat(timespec="seconds"),
            "platform": platform.system(),
        }

        if save:
            filepath = (
                self.screenshots_dir
                / f"screen_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.png"
            )
            try:
                image.save(filepath)
                result["file_path"] = str(filepath.resolve())
                logger.debug("Screenshot saved: {}", filepath)
            except Exception as exc:
                logger.error("Failed to save screenshot: {}", str(exc))
                result["save_error"] = str(exc)

        return result

    def capture_to_path(self, filepath: str) -> Dict[str, Any]:
        """Capture and save to an explicit path."""
        if not PIL_AVAILABLE:
            return {"success": False, "error": "Pillow is not installed."}
        try:
            image = ImageGrab.grab()
            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path)
            return {
                "success": True,
                "file_path": str(path.resolve()),
                "width": image.width,
                "height": image.height,
            }
        except Exception as exc:
            logger.error("Screen capture failed: {}", str(exc))
            return {"success": False, "error": str(exc)}

    def latest_screenshot(self) -> Optional[Path]:
        """Return the most recently saved screenshot path, if any."""
        files = sorted(
            self.screenshots_dir.glob("screen_*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return files[0] if files else None


if __name__ == "__main__":
    svc = ScreenCaptureService()
    print(svc.capture())
