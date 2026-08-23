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
    def __init__(self, headless: bool = True, browser: str = "chromium", browsers_path: Optional[str] = None):
        self.headless = headless
        self.browser_name = browser
        self.browsers_path = browsers_path
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

        self._browser = await browser_ctor.launch(headless=self.headless)
        self._context = await self._browser.new_context()
        self.page = await self._context.new_page()
        logger.info("Playwright browser started: {} (headless={})", self.browser_name, self.headless)

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
                        filled.append({"selector": selector, "value": value})
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        try:
                            await self.page.click(selector)
                            await self.page.type(selector, value)
                            filled.append({"selector": selector, "value": value})
                            last_exc = None
                            break
                        except Exception as exc2:
                            last_exc = exc2
                    attempt += 1

                if last_exc:
                    return {"success": False, "error": f"Failed to fill {selector}: {str(last_exc)}"}

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
            return {"success": True, "filled": filled, "page_content": content}
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
