"""
Vision Agent - computer vision and screen understanding.
"""

import io
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# pytesseract pulls in pandas - over a second of import - and OCR is not
# needed to start the system. Resolved on first use instead.
_pytesseract = None


def _ocr():
    """The pytesseract module, imported on first use."""
    global _pytesseract
    if _pytesseract is None:
        import pytesseract as _module
        _pytesseract = _module
    return _pytesseract

from PIL import Image, ImageGrab
from loguru import logger
from ollama import AsyncClient

from core.config import load_config


class VisionAgent:
    """
    Handles all visual perception:
    - Screenshots
    - OCR (text extraction)
    - UI element detection
    - Visual understanding with LLaVA
    """

    def __init__(self, config_path: str = "./config/settings.json"):
        self.config = load_config(config_path)
        self.ollama = AsyncClient(host=self.config["ollama"]["host"])
        self.vision_model = self.config["llm_council"]["vision"]["model"]

        tesseract_path = self.config.get("vision", {}).get("tesseract_path")
        if tesseract_path:
            _ocr().pytesseract.tesseract_cmd = tesseract_path
        else:
            located = shutil.which("tesseract")
            if located:
                _ocr().pytesseract.tesseract_cmd = located
            else:
                # Last-resort default Windows install location.
                default_windows_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
                if default_windows_path.exists():
                    _ocr().pytesseract.tesseract_cmd = str(default_windows_path)

        self.ocr_available = self._check_ocr_availability()

        self.screenshots_dir = Path(self.config["paths"]["data"]) / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        if self.ocr_available:
            logger.info("Vision Agent initialized")
        else:
            logger.warning("Vision Agent initialized without OCR support")

    def _check_ocr_availability(self) -> bool:
        """Check whether Tesseract OCR is available."""

        try:
            _ocr().get_tesseract_version()
            return True
        except Exception as exc:
            logger.warning("Tesseract OCR unavailable: {}", str(exc))
            return False

    def is_ocr_available(self) -> bool:
        """Return whether OCR is available."""

        return self.ocr_available

    def capture_screen(self, save: bool = True) -> Optional[Image.Image]:
        """Capture the current screen."""

        try:
            screenshot = ImageGrab.grab()

            if save:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = self.screenshots_dir / f"screen_{timestamp}.png"
                screenshot.save(filepath)
                logger.debug("Screenshot saved: {}", filepath)

            return screenshot

        except Exception as exc:
            logger.error("Screenshot failed: {}", str(exc))
            return None

    def extract_text_ocr(self, image: Optional[Image.Image] = None) -> str:
        """Extract text from an image or a fresh screenshot."""

        if image is None:
            image = self.capture_screen(save=False)

        if image is None:
            return ""

        if not self.ocr_available:
            logger.warning("OCR requested but Tesseract is not available")
            return ""

        try:
            text = _ocr().image_to_string(image)
            logger.debug("OCR extracted {} characters", len(text))
            return text.strip()

        except Exception as exc:
            logger.error("OCR failed: {}", str(exc))
            return ""

    def find_text_coordinates(self, target_text: str, image: Optional[Image.Image] = None) -> Optional[tuple[int, int]]:
        """Find the X, Y coordinates of a given text on the screen."""
        if image is None:
            image = self.capture_screen(save=False)
        if image is None or not self.ocr_available:
            return None

        try:
            data = _ocr().image_to_data(
                image, output_type=_ocr().Output.DICT)
            n_boxes = len(data['text'])

            target_words = [w.lower().strip(":,.-") for w in target_text.split() if w.strip(":,.-")]
            if not target_words:
                return None

            for i in range(n_boxes):
                word_clean = data['text'][i].lower().strip(":,.-")
                if word_clean == target_words[0]:
                    # Match subsequent words
                    match = True
                    for j in range(1, len(target_words)):
                        if i + j >= n_boxes or data['text'][i+j].lower().strip(":,.-") != target_words[j]:
                            match = False
                            break
                    if match:
                        left = data['left'][i]
                        top = data['top'][i]
                        width = sum(data['width'][i:i+len(target_words)])
                        height = max(data['height'][i:i+len(target_words)])

                        center_x = left + width // 2
                        center_y = top + height // 2
                        logger.info("Found text '{}' at screen coordinates ({}, {})", target_text, center_x, center_y)
                        return (center_x, center_y)
        except Exception as exc:
            logger.error("Failed to find text coordinates: {}", str(exc))
        return None

    async def understand_screen(self, question: str = None) -> Dict[str, Any]:
        """Use the vision model to understand the current screen."""

        logger.info("Analyzing screen with vision model...")

        screenshot = self.capture_screen(save=True)
        if screenshot is None:
            return {"error": "Failed to capture screen"}

        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format="PNG")
        img_bytes = img_byte_arr.getvalue()

        if question is None:
            question = (
                "Describe what you see on this screen. Identify the application, "
                "major UI elements, what the user appears to be doing, and any "
                "important visible information."
            )

        try:
            response = await self.ollama.generate(
                model=self.vision_model,
                prompt=question,
                images=[img_bytes],
                keep_alive=0,
            )

            return {
                "description": response["response"],
                "timestamp": datetime.now().isoformat(),
                "model": self.vision_model,
            }

        except Exception as exc:
            logger.error("Vision understanding failed: {}", str(exc))

            # llava:7b needs ~4.7 GB and this machine has 4 GB of VRAM, so
            # the runner dies with GGML_ASSERT(buffer) failed and the whole
            # feature returned an error. OCR reads the same screen using a
            # fraction of the memory - degraded, but genuinely useful, and
            # far better than telling the user the request failed.
            try:
                text = (self.extract_text_ocr() or "").strip()
            except Exception:
                text = ""

            if text:
                logger.info("Vision model unavailable; answered from OCR instead.")
                return {
                    "description": text[:4000],
                    "source": "ocr_fallback",
                    "degraded": True,
                    "note": (
                        "The image model would not fit in this GPU's memory, "
                        "so this is the text read off the screen rather than a "
                        "visual description."
                    ),
                    "timestamp": datetime.now().isoformat(),
                }

            return {"error": str(exc)}

    async def find_ui_element(self, element_description: str) -> Dict[str, Any]:
        """Find a UI element on screen using the vision model."""

        logger.info("Searching for: {}", element_description)

        screenshot = self.capture_screen(save=False)
        if screenshot is None:
            return {"found": False, "error": "Screenshot failed"}

        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format="PNG")
        img_bytes = img_byte_arr.getvalue()

        prompt = f"""Look at this screen and find: "{element_description}"

If you find it, describe:
1. What it looks like
2. Approximate location (top-left, center, bottom-right, etc.)
3. What type of element it is (button, text field, link, etc.)
4. Any text visible on or near it

Respond in JSON format:
{{
    "found": true/false,
    "type": "button/textfield/link/etc",
    "location": "description of where it is",
    "description": "what it looks like",
    "nearby_text": "any text around it"
}}

Respond ONLY with JSON."""

        try:
            response = await self.ollama.generate(
                model=self.vision_model,
                prompt=prompt,
                images=[img_bytes],
                keep_alive=0,
            )

            result = self._parse_json(response["response"])
            return result

        except Exception as exc:
            logger.error("Element search failed: {}", str(exc))
            return {"found": False, "error": str(exc)}

    async def detect_changes(self, previous_image: Image.Image) -> Dict[str, Any]:
        """Detect visual changes between two screenshots."""

        current = self.capture_screen(save=False)
        if current is None:
            return {"error": "Screenshot failed"}

        try:
            from PIL import ImageChops

            if previous_image.size != current.size:
                previous_image = previous_image.resize(current.size)

            diff = ImageChops.difference(previous_image, current)
            if diff.getbbox():
                return {
                    "changed": True,
                    "change_area": diff.getbbox(),
                    "timestamp": datetime.now().isoformat(),
                }
            return {"changed": False}

        except Exception as exc:
            logger.error("Change detection failed: {}", str(exc))
            return {"error": str(exc)}

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Parse JSON out of an LLM response."""

        cleaned = text.strip().replace("```json", "").replace("```", "").strip()

        if "{" in cleaned and "}" in cleaned:
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            cleaned = cleaned[start:end]

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {"raw_response": text, "parse_error": "JSON decode failed"}

    def get_screen_dimensions(self) -> Dict[str, int]:
        """Get current screen resolution."""

        screenshot = self.capture_screen(save=False)
        if screenshot:
            width, height = screenshot.size
            return {"width": width, "height": height}
        return {"width": 0, "height": 0}


async def test_vision_agent():
    vision = VisionAgent()

    print("\n=== TEST 1: Capture Screen ===")
    screenshot = vision.capture_screen(save=True)
    print(f"Captured: {screenshot.size if screenshot else 'Failed'}")

    print("\n=== TEST 2: OCR ===")
    text = vision.extract_text_ocr(screenshot)
    print(f"Extracted text (first 200 chars):\n{text[:200]}")

    print("\n=== TEST 3: Understand Screen ===")
    understanding = await vision.understand_screen()
    print(json.dumps(understanding, indent=2))

    print("\n=== TEST 4: Screen Dimensions ===")
    dims = vision.get_screen_dimensions()
    print(f"Screen: {dims['width']}x{dims['height']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_vision_agent())
