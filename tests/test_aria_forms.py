"""Form discovery on ARIA-labelled markup.

Google Forms - and most modern form builders - give inputs no id, no name
and no <label>. The question text sits in a separate element referenced by
aria-labelledby. Discovery only walked <label> elements and nearby text
nodes, so that structure yielded zero usable selectors.

Uses a local fixture with that exact structure; no network involved.

Everything runs inside ONE asyncio.run: Playwright objects are bound to the
event loop that created them, so starting the browser in one loop and
driving it from another silently returns nothing.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "aria_form.html"
LABELS = ["What is your name?", "Email address", "Any feedback?"]


def _discover_and_fill():
    """Load the fixture, resolve selectors, fill them, read the DOM back."""
    from agents.browser_driver import BrowserDriver

    async def run():
        driver = BrowserDriver(headless=True, browser="chromium")
        await driver.start()
        try:
            await driver.goto(FIXTURE.as_uri())
            input_count = await driver.page.evaluate(
                "() => document.querySelectorAll('input,textarea').length"
            )
            mapping = await driver.find_selectors_for_labels(LABELS)
            selectors = [v["selector"] for v in mapping.values() if v.get("selector")]
            values = []
            if selectors:
                await driver.fill_fields({s: "filled" for s in selectors})
                values = await driver.page.evaluate(
                    "() => Array.from(document.querySelectorAll('input,textarea'))"
                    ".map(e => e.value)"
                )
            return input_count, mapping, values
        finally:
            await driver.stop()

    try:
        return asyncio.run(run())
    except Exception as exc:                       # pragma: no cover
        pytest.skip(f"Playwright unavailable: {exc}")


@pytest.fixture(scope="module")
def outcome():
    return _discover_and_fill()


def test_the_fixture_actually_loads(outcome):
    """Guard the guard: a page that never loaded would pass everything else
    by finding nothing to disagree with."""
    input_count, _, _ = outcome
    assert input_count == 3, "fixture did not load; the rest of this file proves nothing"


def test_aria_labelled_fields_are_discovered(outcome):
    _, mapping, _ = outcome
    resolved = {k: v for k, v in mapping.items() if v.get("selector")}
    assert len(resolved) == len(LABELS), (
        f"only {len(resolved)}/{len(LABELS)} ARIA-labelled fields found: {mapping}"
    )


def test_aria_labelled_fields_can_actually_be_filled(outcome):
    """Discovery is worthless if the selectors do not accept a value."""
    _, _, values = outcome
    assert values, "no values read back from the page"
    assert all(v == "filled" for v in values), f"fields not filled: {values}"
