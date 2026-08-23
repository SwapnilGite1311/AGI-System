import os
import asyncio
import pytest

from agents import browser_driver as bd

# Skip this integration test if Playwright is not installed in the environment.
if getattr(bd, 'async_playwright', None) is None:
    pytest.skip("Playwright is not installed in this environment; skipping integration test.", allow_module_level=True)

from agents.browser_driver import BrowserDriver


def test_form_fill_integration():
    async def run_test():
        driver = BrowserDriver(headless=True)
        await driver.start()

        path = os.path.join(os.path.dirname(__file__), "fixtures", "simple_form.html")
        file_url = "file:///" + path.replace("\\", "/")

        nav = await driver.goto(file_url)
        assert nav.get("success"), f"Navigation failed: {nav}"

        mapping = await driver.find_selectors_for_labels(["Name", "Email", "Message"])
        assert mapping and any(v.get("selector") for v in mapping.values()), f"No selectors discovered: {mapping}"

        field_map = {}
        for label, entry in mapping.items():
            selector = entry.get("selector") if entry else None
            if not selector:
                continue
            lname = label.lower()
            if "name" in lname:
                field_map[selector] = "Alice"
            elif "email" in lname:
                field_map[selector] = "alice@example.com"
            else:
                field_map[selector] = "Hello"

        submit_sel = await driver.find_submit_selector()
        result = await driver.fill_fields(field_map, submit_selector=submit_sel)
        assert result.get("success"), f"Fill failed: {result}"

        content = result.get("page_content", "").lower()
        assert "thank you" in content, f"Submission not verified, page content: {content[:200]}"

        await driver.stop()

    asyncio.run(run_test())
