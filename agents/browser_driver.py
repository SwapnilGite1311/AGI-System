"""
Lightweight Playwright-based browser driver wrapper.
Provides async helpers for navigation and form interaction.
Falls back gracefully if Playwright isn't installed.
"""
import os
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
except Exception:  # pragma: no cover - optional dependency
    async_playwright = None


class BrowserDriver:
    def __init__(
        self,
        headless: bool = True,
        browser: str = "chromium",
        browsers_path: Optional[str] = None,
        persistent_profile_dir: Optional[str] = None,
    ):
        self.headless = headless
        self.browser_name = browser
        self.browsers_path = browsers_path
        # When set, launches a real Chromium profile directory VEGA owns
        # (not the user's actual personal Chrome profile - avoids lock
        # conflicts if their own browser is open, and keeps automated
        # actions out of their personal history/cookies) instead of an
        # ephemeral context. The user logs into whatever sites they want
        # VEGA to act on once, inside that profile; it persists across
        # restarts since it's real profile-directory state on disk.
        self.persistent_profile_dir = persistent_profile_dir
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def start(self):
        if async_playwright is None:
            raise RuntimeError("playwright is not installed")

        if self._playwright:
            return

        self._configure_browsers_path()

        self._playwright = await async_playwright().start()
        browser_ctor = getattr(self._playwright, self.browser_name, None)
        if not browser_ctor:
            browser_ctor = self._playwright.chromium

        if self.persistent_profile_dir:
            Path(self.persistent_profile_dir).mkdir(parents=True, exist_ok=True)
            # launch_persistent_context returns the BrowserContext directly -
            # there is no separate Browser object in this mode.
            self._context = await browser_ctor.launch_persistent_context(
                self.persistent_profile_dir, headless=self.headless,
            )
            self._browser = None
            logger.info(
                "Playwright persistent profile started: {} (dir={})",
                self.browser_name, self.persistent_profile_dir,
            )
        else:
            self._browser = await browser_ctor.launch(headless=self.headless)
            self._context = await self._browser.new_context()
            logger.info("Playwright browser started: {} (headless={})", self.browser_name, self.headless)

        # A persistent context launches with one blank tab already open in
        # Chromium - reuse it instead of opening a second blank tab.
        self.page = self._context.pages[0] if self._context.pages else await self._context.new_page()

    def _configure_browsers_path(self):
        """Use a configured/global Playwright browser cache when available."""

        if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
            return

        candidates = [self.browsers_path, r"C:\ms-playwright"]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = candidate
                logger.info("Using Playwright browser cache: {}", candidate)
                return

    async def stop(self):
        try:
            if self.page:
                await self.page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as exc:
            logger.warning("Error stopping browser driver: {}", str(exc))
        finally:
            self._playwright = None
            self._browser = None
            self._context = None
            self.page = None

    async def goto(self, url: str, timeout: int = 30000) -> Dict[str, object]:
        if not self.page:
            await self.start()
        try:
            resp = await self.page.goto(url, timeout=timeout)
            status = resp.status if resp else None
            return {"success": True, "status": status, "url": url}
        except Exception as exc:
            return {"success": False, "error": str(exc), "url": url}

    async def _read_back(self, selector: str) -> Optional[str]:
        """What the field actually holds now.

        Covers the three shapes a "field" takes: input/textarea (value),
        select (the selected value), and contenteditable (text content).
        Returns None when it cannot be read, which is itself a failure to
        verify rather than a pass.
        """
        try:
            return await self.page.input_value(selector, timeout=2000)
        except Exception:
            pass
        try:
            return await self.page.eval_on_selector(
                selector,
                "el => el.value !== undefined && el.value !== null"
                " ? el.value : (el.textContent || '')",
            )
        except Exception:
            return None

    async def fill_fields(self, field_map: Dict[str, str], submit_selector: Optional[str] = None) -> Dict[str, object]:
        """Fill fields using selector keys in field_map.

        Keys may be CSS selectors or Playwright XPath selectors prefixed with 'xpath='.
        Optionally click `submit_selector` after filling. Performs simple retries
        and returns page state for verification.
        """
        if not self.page:
            await self.start()

        filled = []
        try:
            for selector, value in field_map.items():
                attempt = 0
                last_exc = None
                while attempt < 2:
                    try:
                        # Playwright accepts CSS selectors and 'xpath=..' selectors
                        await self.page.fill(selector, value)
                        landed = await self._read_back(selector)
                        if landed != value:
                            raise RuntimeError(
                                f"value did not stick (field holds {landed!r})")
                        filled.append({"selector": selector, "value": value,
                                       "verified": True})
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        try:
                            await self.page.click(selector)
                            await self.page.type(selector, value)
                            landed = await self._read_back(selector)
                            if landed != value:
                                raise RuntimeError(
                                    f"value did not stick (field holds {landed!r})")
                            filled.append({"selector": selector, "value": value,
                                           "verified": True})
                            last_exc = None
                            break
                        except Exception as exc2:
                            last_exc = exc2
                    attempt += 1

                if last_exc:
                    # Report what DID land. A half-filled form is a real
                    # state the user has to know about - returning only the
                    # error left them thinking nothing had been typed.
                    return {
                        "success": False,
                        "error": f"Failed to fill {selector}: {str(last_exc)}",
                        "filled": filled,
                        "failed_selector": selector,
                        "partial": bool(filled),
                    }

            if submit_selector:
                try:
                    await self.page.click(submit_selector)
                except Exception:
                    # try pressing Enter as fallback
                    try:
                        await self.page.keyboard.press("Enter")
                    except Exception:
                        return {"success": False, "error": f"Failed to activate submit selector {submit_selector}"}

            # Wait briefly for navigation/network activity
            try:
                await self.page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass

            content = await self.page.content()
            return {
                "success": True,
                "filled": filled,
                # Every entry in `filled` was read back and matched. Without
                # this, "filled" meant "fill() did not raise", which is a
                # much weaker claim than it appears.
                "verified": all(f.get("verified") for f in filled),
                "page_content": content,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def find_submit_selector(self, candidates: Optional[list] = None) -> Optional[str]:
        """Try to find a submit button or input on the page and return a selector.

        Returns a CSS selector or an 'xpath=' selector string, or None if not found.
        """
        if not self.page:
            await self.start()

        js = r"""
        () => {
            function normalize(s){return (s||'').toString().trim().toLowerCase();}
            const candidateTexts = ['submit','send','create','sign up','register','continue','next','confirm'];
            const inputs = Array.from(document.querySelectorAll('input[type="submit"], input[type="button"], button'));
            for (let el of inputs) {
                const txt = normalize(el.innerText || el.value || el.getAttribute('aria-label'));
                if (!txt) continue;
                for (let cand of candidateTexts) {
                    if (txt.includes(cand)) {
                        if (el.id) return '#' + el.id;
                        if (el.name) return '[name="' + el.name + '"]';
                        // build xpath
                        function getXPath(el){
                            if (el.id) return 'id("'+el.id+'")';
                            var xpath = '';
                            for (; el && el.nodeType==1; el=el.parentNode){
                                var idx = 1; var sib = el.previousSibling;
                                for (; sib; sib = sib.previousSibling) if(sib.nodeType===1 && sib.nodeName===el.nodeName) idx++;
                                xpath = '/' + el.nodeName.toLowerCase() + '['+idx+']' + xpath;
                            }
                            return xpath;
                        }
                        return 'xpath=' + getXPath(el);
                    }
                }
            }

            // fallback: any input[type=submit]
            const submit = document.querySelector('input[type="submit"]');
            if (submit) {
                if (submit.id) return '#' + submit.id;
                if (submit.name) return '[name="' + submit.name + '"]';
                function getXPath(el){
                    if (el.id) return 'id("'+el.id+'")';
                    var xpath = '';
                    for (; el && el.nodeType==1; el=el.parentNode){
                        var idx = 1; var sib = el.previousSibling;
                        for (; sib; sib = sib.previousSibling) if(sib.nodeType===1 && sib.nodeName===el.nodeName) idx++;
                        xpath = '/' + el.nodeName.toLowerCase() + '['+idx+']' + xpath;
                    }
                    return xpath;
                }
                return 'xpath=' + getXPath(submit);
            }

            return null;
        }
        """

        try:
            sel = await self.page.evaluate(js)
            return sel
        except Exception:
            return None

    async def find_selectors_for_labels(self, labels: list) -> dict:
        """Return a mapping label -> {selector, confidence} for visible inputs.

        Labels should be short strings like 'name', 'email', 'company'.
        Returns {label: {selector: str|None, confidence: float}}
        """
        if not self.page:
            await self.start()

        js = r"""
        (labels) => {
            function getXPathForElement(el) {
                if (el.id) return 'id("' + el.id + '")';
                var xpath = '';
                for (; el && el.nodeType == 1; el = el.parentNode) {
                    var idx = 1;
                    var sib = el.previousSibling;
                    for (; sib; sib = sib.previousSibling) {
                        if (sib.nodeType === 1 && sib.nodeName === el.nodeName) idx++;
                    }
                    var tagName = el.nodeName.toLowerCase();
                    xpath = '/' + tagName + '[' + idx + ']' + xpath;
                }
                return xpath;
            }

            function normalize(s) { return (s||'').toString().trim().toLowerCase(); }

            const results = {};
            labels.forEach(label => { results[label] = {selector: null, confidence: 0.0}; });

            labels = labels.map(l => l.toString().trim());

            // 1) Try <label> elements
            const labelEls = Array.from(document.querySelectorAll('label'));
            for (let lbl of labels) {
                const lblLower = lbl.toLowerCase();
                for (let l of labelEls) {
                    if (normalize(l.innerText).includes(lblLower)) {
                        if (l.htmlFor) {
                            results[lbl] = {selector: '#' + l.htmlFor, confidence: 0.95};
                            break;
                        }
                        const input = l.querySelector('input,textarea,select');
                        if (input) {
                            if (input.id) { results[lbl] = {selector: '#' + input.id, confidence: 0.92}; break; }
                            if (input.name) { results[lbl] = {selector: '[name="' + input.name + '"]', confidence: 0.9}; break; }
                            results[lbl] = {selector: 'xpath=' + getXPathForElement(input), confidence: 0.6}; break;
                        }
                    }
                }
            }

            // 2) Search visible text nodes and nearby inputs
            const textNodes = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
            while(walker.nextNode()) {
                textNodes.push(walker.currentNode);
            }

            // ---- ARIA first -------------------------------------------
            // Google Forms (and most modern form builders) put the question
            // text in a separate element and point at it with
            // aria-labelledby; the inputs carry no id, name or <label>. The
            // text-node walk below cannot see that relationship, so a real
            // Google Form yielded zero selectors.
            const ariaInputs = Array.from(
                document.querySelectorAll('input,textarea,select')
            );
            function ariaTextFor(el) {
                const direct = (el.getAttribute('aria-label') || '').trim();
                if (direct) return direct;
                const ref = el.getAttribute('aria-labelledby');
                if (!ref) return '';
                const parts = [];
                for (const id of ref.split(/\s+/)) {
                    const node = document.getElementById(id);
                    if (node) parts.push((node.innerText || node.textContent || '').trim());
                }
                return parts.filter(Boolean).join(' ').trim();
            }
            function selectorFor(el, base) {
                if (el.id) return {selector: '#' + el.id, confidence: base};
                if (el.name) return {selector: '[name="' + el.name + '"]', confidence: base - 0.05};
                return {selector: 'xpath=' + getXPathForElement(el), confidence: base - 0.15};
            }
            for (let lbl of labels) {
                if (results[lbl] && results[lbl].selector) continue;
                const want = lbl.toLowerCase().replace(/[^a-z0-9 ]/g, '').trim();
                if (!want) continue;
                for (let el of ariaInputs) {
                    const got = ariaTextFor(el).toLowerCase().replace(/[^a-z0-9 ]/g, '').trim();
                    if (!got) continue;
                    if (got === want || got.includes(want) || want.includes(got)) {
                        results[lbl] = selectorFor(el, 0.9);
                        break;
                    }
                }
            }

            for (let lbl of labels) {
                if (results[lbl] && results[lbl].selector) continue;
                const lower = lbl.toLowerCase();
                for (let t of textNodes) {
                    if (!t.nodeValue) continue;
                    if (t.nodeValue.toLowerCase().includes(lower)) {
                        let el = t.parentElement;
                        // look for descendant inputs
                        let input = el.querySelector && el.querySelector('input,textarea,select');
                        if (input) {
                            if (input.id) { results[lbl] = {selector: '#' + input.id, confidence: 0.9}; break; }
                            if (input.name) { results[lbl] = {selector: '[name="' + input.name + '"]', confidence: 0.85}; break; }
                            results[lbl] = {selector: 'xpath=' + getXPathForElement(input), confidence: 0.6}; break;
                        }
                        // next sibling
                        let sib = el.nextElementSibling;
                        if (sib) {
                            if (sib.matches && sib.matches('input,textarea,select')) {
                                if (sib.id) { results[lbl] = {selector: '#' + sib.id, confidence: 0.9}; break; }
                                if (sib.name) { results[lbl] = {selector: '[name="' + sib.name + '"]', confidence: 0.85}; break; }
                                results[lbl] = {selector: 'xpath=' + getXPathForElement(sib), confidence: 0.6}; break;
                            }
                            let inner = sib.querySelector && sib.querySelector('input,textarea,select');
                            if (inner) {
                                if (inner.id) { results[lbl] = {selector: '#' + inner.id, confidence: 0.9}; break; }
                                if (inner.name) { results[lbl] = {selector: '[name="' + inner.name + '"]', confidence: 0.85}; break; }
                                results[lbl] = {selector: 'xpath=' + getXPathForElement(inner), confidence: 0.6}; break;
                            }
                        }
                    }
                }
            }

            return results;
        }
        """

        try:
            mapping = await self.page.evaluate(js, labels)
            out = {}
            for label in labels:
                val = mapping.get(label)
                if isinstance(val, dict) and val.get("selector"):
                    out[label] = {"selector": val.get("selector"), "confidence": float(val.get("confidence") or 0.0)}
                else:
                    out[label] = {"selector": None, "confidence": 0.0}
            return out
        except Exception:
            return {label: {"selector": None, "confidence": 0.0} for label in labels}

    async def evaluate(self, script: str):
        if not self.page:
            await self.start()
        return await self.page.evaluate(script)

    async def find_label_candidates(self) -> list:
        """Return a list of candidate labels and their nearby input selectors.

        Returns list of {text: str, selector: str|null}
        """
        if not self.page:
            await self.start()

        js = r"""
        () => {
            function getXPath(el){
                if (el.id) return 'id("'+el.id+'")';
                var xpath = '';
                for (; el && el.nodeType==1; el=el.parentNode){
                    var idx = 1; var sib = el.previousSibling;
                    for (; sib; sib = sib.previousSibling) if(sib.nodeType===1 && sib.nodeName===el.nodeName) idx++;
                    xpath = '/' + el.nodeName.toLowerCase() + '['+idx+']' + xpath;
                }
                return xpath;
            }
            const results = [];
            const labelEls = Array.from(document.querySelectorAll('label'));
            for (let l of labelEls) {
                const txt = (l.innerText || '').trim();
                let sel = null;
                if (l.htmlFor) sel = '#' + l.htmlFor;
                else {
                    const input = l.querySelector && l.querySelector('input,textarea,select');
                    if (input) {
                        if (input.id) sel = '#' + input.id;
                        else if (input.name) sel = '[name="'+input.name+'"]';
                        else sel = 'xpath=' + getXPath(input);
                    }
                }
                results.push({text: txt, selector: sel});
            }

            // Also look for visible text nodes near inputs
            const inputs = Array.from(document.querySelectorAll('input,textarea,select'));
            for (let inp of inputs) {
                let txt = (inp.getAttribute('aria-label') || inp.getAttribute('placeholder') || '').trim();

                // aria-labelledby: the label lives in a separate element that
                // is not a <label> at all. Google Forms builds every question
                // this way, so discovery found zero fields on one and every
                // selector came back null.
                if (!txt) {
                    const ref = inp.getAttribute('aria-labelledby');
                    if (ref) {
                        const parts = [];
                        for (const id of ref.split(/\s+/)) {
                            const node = document.getElementById(id);
                            if (node) parts.push((node.innerText || node.textContent || '').trim());
                        }
                        txt = parts.filter(Boolean).join(' ').trim();
                    }
                }

                // Last resort: the nearest preceding heading-ish text inside
                // the same question block.
                if (!txt) {
                    const block = inp.closest('[role="listitem"], .freebirdFormviewerViewItemsItemItem, li, fieldset, .form-group');
                    if (block) {
                        const head = block.querySelector('[role="heading"], legend, h1, h2, h3, h4, label');
                        if (head) txt = (head.innerText || '').trim();
                    }
                }

                if (!txt) {
                    const prev = inp.previousElementSibling;
                    if (prev && (prev.tagName||'').toLowerCase() === 'label') txt = (prev.innerText||'').trim();
                }
                if (!txt) continue;
                let sel = null;
                if (inp.id) sel = '#' + inp.id;
                else if (inp.name) sel = '[name="'+inp.name+'"]';
                else sel = 'xpath=' + getXPath(inp);
                results.push({text: txt, selector: sel});
            }

            return results;
        }
        """

        try:
            data = await self.page.evaluate(js)
            return data
        except Exception:
            return []
