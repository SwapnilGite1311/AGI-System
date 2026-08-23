"""Task #5 regression tests: honest submission_verified in WebAgent DOM path.

Covers:
- verified=True when post-submit page shows success keywords
- verified=False when error keywords present
- verified=False (unverified) when page content cannot be read
"""
import asyncio

from agents.web_agent import WebAgent


class StubSystemAgent:
    def press_key(self, key):
        return {"success": True}


class StubVisionAgent:
    def is_ocr_available(self):
        return False

    def extract_text_ocr(self, image=None):
        return ""


class DummyLearningAgent:
    def remember_form_pattern(self, *args, **kwargs):
        pass


class StubKeyboard:
    async def press(self, key):
        pass


class StubPage:
    def __init__(self, content_text=None, fail_content=False):
        self.clicks = []
        self._content_text = content_text or ""
        self._fail_content = fail_content
        self.keyboard = StubKeyboard()

    async def click(self, selector):
        self.clicks.append(selector)

    async def content(self):
        if self._fail_content:
            raise RuntimeError("page closed")
        return f"<html><body>{self._content_text}</body></html>"


class StubDriver:
    def __init__(self, page):
        self.page = page

    async def find_selectors_for_labels(self, labels):
        return {
            label: {"selector": f"#{label.lower()}", "confidence": 0.95}
            for label in labels
        }

    async def find_submit_selector(self):
        return "#submit"

    async def fill_fields(self, field_map, submit_selector=None):
        if submit_selector:
            await self.page.click(submit_selector)
        return {"success": True, "filled": list(field_map.keys())}

    async def find_label_candidates(self):
        return []


def _run(content_text=None, fail_content=False):
    agent = WebAgent(
        config_path="./config/settings.json",
        system_agent=StubSystemAgent(),
        vision_agent=StubVisionAgent(),
        learning_agent=DummyLearningAgent(),
    )
    agent.browser_driver = StubDriver(StubPage(content_text, fail_content))
    agent.form_submit_delay_seconds = 0
    return asyncio.run(
        agent.intelligent_form_fill(
            {"Name": "Swapnil", "Email": "swapnil@example.com"},
            submit=True,
        )
    )


def test_dom_submission_verified_true_on_success_page():
    result = _run(content_text="Thank you! Your form was received.")
    assert result["submitted"] is True
    assert result["submission_verified"] is True
    assert "verified" in result["verification_details"].lower()


def test_dom_submission_not_verified_when_error_keywords():
    result = _run(content_text="Error: email field invalid")
    assert result["submitted"] is True
    assert result["submission_verified"] is False
    assert "error" in result["verification_details"].lower()


def test_dom_submission_honest_unverified_when_content_unreadable():
    result = _run(fail_content=True)
    assert result["submitted"] is True
    assert result["submission_verified"] is False
    assert "could not read page content" in result["verification_details"].lower()


def test_no_submission_reports_unverified():
    agent = WebAgent(
        config_path="./config/settings.json",
        system_agent=StubSystemAgent(),
        vision_agent=StubVisionAgent(),
        learning_agent=DummyLearningAgent(),
    )
    agent.browser_driver = StubDriver(StubPage("Thank you"))
    result = asyncio.run(
        agent.intelligent_form_fill({"Name": "Swapnil"}, submit=False)
    )
    assert result["submitted"] is False
    assert result["submission_verified"] is False
