"""
Web Agent - lightweight browser automation and page interaction helpers.
Uses the existing SystemAgent and VisionAgent to keep the first web layer
dependency-light and aligned with the current project stack.
"""

import asyncio
import json
import re
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional
from difflib import SequenceMatcher
import uuid
import time
from urllib.parse import quote_plus, urlparse

from loguru import logger

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # LearningAgent pulls in torch - keep it off startup
    from agents.learning_agent import LearningAgent
from agents.system_agent import SystemAgent
from agents.vision_agent import VisionAgent

from core.config import load_config


class WebAgent:
    """
    Handles browser-oriented tasks:
    - URL navigation
    - Search actions
    - Element finding through vision
    - Mouse and keyboard form interaction
    - OCR-based page text extraction
    """

    def __init__(
        self,
        config_path: str = "./config/settings.json",
        system_agent: Optional[SystemAgent] = None,
        vision_agent: Optional[VisionAgent] = None,
        learning_agent: Optional["LearningAgent"] = None,
    ):
        """Initialize the web agent."""

        self.config = load_config(config_path)
        self.system_agent = system_agent or SystemAgent(config_path)
        self.vision_agent = vision_agent or VisionAgent(config_path)
        if learning_agent is None:
            # Imported at point of use: this chain ends at torch, which
            # costs seconds and is not needed to browse the web.
            from agents.learning_agent import LearningAgent
            learning_agent = LearningAgent(config_path)
        self.learning_agent = learning_agent

        web_config = self.config.get("web_automation", {})
        self.default_browser = web_config.get("default_browser", "chrome")
        self.search_engine_url = web_config.get(
            "search_engine_url",
            "https://www.google.com/search?q={query}",
        )
        self.navigation_delay_seconds = float(web_config.get("navigation_delay_seconds", 2.0))
        self.verify_with_ocr = bool(web_config.get("verify_with_ocr", True))
        self.form_field_delay_seconds = float(web_config.get("form_field_delay_seconds", 0.1))
        self.form_submit_delay_seconds = float(web_config.get("form_submit_delay_seconds", 0.2))
        self.last_url: Optional[str] = None
        self.last_browser: Optional[str] = None
        self.selector_confidence_threshold = float(web_config.get("selector_confidence_threshold", 0.7))
        # Vertical gap from an OCR-located label to its input, in pixels.
        # A layout/DPI assumption, not a measurement - configurable so it
        # can be corrected rather than hardcoded at a magic 45.
        self.label_to_input_offset_px = int(web_config.get("label_to_input_offset_px", 45))
        self.verbose_logging = bool(web_config.get("verbose_logging", False))

        # Simple synonyms for label normalization
        self.label_synonyms = {
            "email": ["e-mail", "email address", "e-mail address", "mail"],
            "name": ["full name", "your name", "first name", "last name", "given name"],
            "phone": ["phone number", "mobile", "mobile number", "cell", "cellphone"],
            "company": ["organisation", "organization", "org", "company name", "employer"],
            "address": ["street", "location", "addr", "shipping address", "billing address"],
            "password": ["pass", "passwd", "pwd", "new password", "confirm password"],
        }

        # pending confirmations: token -> context
        self._pending_confirmations: Dict[str, Dict[str, Any]] = {}
        # Optional browser driver (Playwright) for DOM-level control
        driver_type = web_config.get("driver")
        self.browser_driver = None
        if driver_type == "playwright":
            try:
                from agents.browser_driver import BrowserDriver

                persistent_profile_dir = None
                if web_config.get("persistent_profile", False):
                    data_dir = self.config.get("paths", {}).get("data", "./data")
                    persistent_profile_dir = str(Path(data_dir) / "browser_profile")

                self.browser_driver = BrowserDriver(
                    headless=web_config.get("headless", True),
                    browser=web_config.get("driver_browser", "chromium"),
                    browsers_path=web_config.get("browsers_path"),
                    persistent_profile_dir=persistent_profile_dir,
                )
            except Exception as exc:
                logger.warning("Playwright driver unavailable: {}", str(exc))
                self.browser_driver = None

        logger.info("Web Agent initialized")

    async def process(self, command: str) -> Dict[str, Any]:
        """Small natural-language entry point for direct WebAgent use."""
        normalized = " ".join((command or "").strip().split())
        lowered = normalized.lower()
        if not normalized:
            return {"success": False, "error": "Empty web command"}

        url_match = re.search(r"(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9.-]+\.(?:com|in|org|net|io)(?:/[^\s]*)?)", normalized)
        target_url = url_match.group(1).strip(".,'\"") if url_match else None
        if target_url and not target_url.startswith(("http://", "https://")):
            target_url = f"https://{target_url}"

        search_match = re.search(r"(?:search(?:\s+for)?|look up|google)\s+['\"]?(?P<query>[^'\"]+)['\"]?$", normalized, re.IGNORECASE)
        fill_fields = self._extract_inline_fields(normalized)

        if target_url and fill_fields:
            navigation = await self.navigate_to_url(target_url)
            if not navigation.get("success"):
                return navigation
            result = await self.intelligent_form_fill(
                fill_fields,
                focus_first_field=True,
                submit="submit" in lowered or "send" in lowered,
                allow_keyboard_fallback=True,
            )
            result["navigated_url"] = target_url
            return result

        # "fill this form for me <url>" - a form request carrying no values.
        # Opening the page and reporting success was useless: nothing was
        # filled and the user was not told why. Load it, read the field
        # labels off the DOM, and ask for exactly what is missing.
        if target_url and re.search(r"\bfill\b.*\bform\b|\bform\b.*\bfill\b", lowered):
            navigation = await self.navigate_to_url(target_url)
            if not navigation.get("success"):
                return navigation
            labels = await self._discover_form_labels()
            if labels:
                return {
                    "success": False,
                    "needs_input": True,
                    "navigated_url": target_url,
                    "detected_fields": labels,
                    "message": (
                        "I opened the page and found these fields: "
                        + ", ".join(labels[:12])
                        + ". Tell me what to put in them, e.g. "
                        + f"\"{labels[0]}: your answer\"."
                    ),
                }
            return {
                "success": False,
                "needs_input": True,
                "navigated_url": target_url,
                "message": (
                    "I opened the page but could not read any form fields from it. "
                    "Tell me the values like \"name: Swapnil, email: me@example.com\" "
                    "and I will fill them in."
                ),
            }

        if target_url and search_match and "search" in lowered:
            query = search_match.group("query").strip()
            if query and target_url:
                return await self.search_site(query, site=target_url, browser_name=self.default_browser)

        if search_match:
            return await self.search_web(search_match.group("query").strip(), browser_name=self.default_browser)

        if target_url:
            return await self.navigate_to_url(target_url, browser_name=self.default_browser)

        return {"success": False, "error": "Could not understand web command", "command": command}

    async def _discover_form_labels(self) -> list:
        """Read the form's field labels from the live DOM.

        Uses the driver's existing label discovery so the user can be told
        what the page actually asks for instead of guessing.
        """
        if not self.browser_driver:
            return []
        try:
            candidates = await self.browser_driver.find_label_candidates()
        except Exception as exc:
            logger.debug("Form label discovery failed: {}", str(exc)[:80])
            return []

        labels = []
        for item in candidates or []:
            text = ""
            if isinstance(item, dict):
                text = str(item.get("label") or item.get("text") or item.get("name") or "")
            elif isinstance(item, str):
                text = item
            text = " ".join(text.split()).strip(" :*")
            if text and text.lower() not in {l.lower() for l in labels}:
                labels.append(text)
        return labels[:20]

    # Words that are sentence scaffolding, never field names.
    _FIELD_STOPWORDS = frozenset({
        "to", "for", "with", "form", "the", "a", "an", "at", "on", "in",
        "and", "then", "please", "go", "fill", "out", "this", "that", "my",
        "me", "using", "http", "https", "www", "url", "link", "page", "site",
    })

    def _extract_inline_fields(self, command: str) -> Dict[str, str]:
        """Extract simple name/value pairs from a form-fill command.

        The URL used to be swallowed as a field: "https://example.com/apply"
        matched the `key: value` pattern and produced
        {"fill this form for me https": "//example.com/apply"}, which was
        then typed into the page as if it were a real answer. Strip URLs
        before parsing, and reject scaffolding words as field names.
        """
        fields: Dict[str, str] = {}

        # Remove URLs first so their scheme colon cannot look like a pair.
        scrubbed = re.sub(r"https?://\S+|\bwww\.\S+", " ", command)

        quoted_pairs = re.findall(
            r"\b([A-Za-z][A-Za-z0-9 _-]{1,30})\s+['\"]([^'\"]+)['\"]", scrubbed
        )
        for key, value in quoted_pairs:
            key_clean = key.strip().split()[-1].lower()
            if key_clean and key_clean not in self._FIELD_STOPWORDS:
                fields[key_clean] = value.strip()

        explicit_pairs = re.findall(
            r"([A-Za-z][A-Za-z0-9 _-]{1,30})\s*(?:=|:)\s*([^,;]+)", scrubbed
        )
        for key, value in explicit_pairs:
            key_clean = key.strip().split()[-1].lower()
            value_clean = value.strip().strip("'\"")
            if key_clean and key_clean not in self._FIELD_STOPWORDS and value_clean:
                fields[key_clean] = value_clean
        return fields

    async def perform_browser_action(
        self,
        browser_name: Optional[str],
        action: str,
        target: str,
    ) -> Dict[str, Any]:
        """Perform a browser action such as navigation or search."""

        browser = browser_name or self.default_browser
        normalized_action = (action or "").lower().strip()

        if normalized_action == "search":
            return await self.search_web(target, browser_name=browser)

        if normalized_action == "navigate":
            return await self.navigate_to_url(target, browser_name=browser)

        if normalized_action == "site_search":
            return await self.search_site(target, browser_name=browser)

        return {
            "success": False,
            "error": f"Unsupported browser action: {action}",
            "browser": browser,
        }

    async def navigate_to_url(
        self,
        url: str,
        browser_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Open a URL in the requested browser, with explicit fallback reporting."""

        from core import progress
        progress.update("Opening the page")

        target_url = self._normalize_url(url)
        browser = browser_name or self.default_browser
        # Set when Playwright could not load the page. Everything below only
        # LAUNCHES a browser, which is not the same as having the document
        # under our control - callers that need the DOM have to be told.
        driver_error: Optional[str] = None

        # Prefer a real browser-driver when available for reliable DOM control
        if self.browser_driver:
            try:
                nav = await self.browser_driver.goto(target_url)
                if nav.get("success"):
                    navigation_result = {
                        "success": True,
                        "browser": "playwright",
                        "url": target_url,
                        "launch_mode": "driver",
                        "dom_available": True,
                        "message": f"Opened {target_url} via Playwright",
                    }
                    self.last_url = target_url
                    self.last_browser = browser
                    self._last_nav_dom_available = True
                    return navigation_result
                else:
                    logger.warning("Playwright navigation failed: {}", nav.get("error"))
                    driver_error = nav.get("error")
            except Exception as exc:
                logger.warning("Playwright goto exception: {}", str(exc))
                driver_error = str(exc)

        result = self.system_agent.open_application(browser, args=[target_url])
        launch_mode = "application"
        warning = None

        if not result.get("success"):
            try:
                webbrowser.open(target_url)
                result = {
                    "success": True,
                    "application": browser,
                    "path": "system-default-browser",
                }
                launch_mode = "fallback"
                warning = f"Requested browser '{browser}' was unavailable. Opened URL in the system default browser."
            except Exception as exc:
                logger.error("URL navigation failed: {}", str(exc))
                return {
                    "success": False,
                    "browser": browser,
                    "url": target_url,
                    "error": str(exc),
                }

        await asyncio.sleep(self.navigation_delay_seconds)

        navigation_result = {
            "success": True,
            "browser": browser,
            "url": target_url,
            "launch_mode": launch_mode,
            # A launched browser is not a page we can read or type into.
            # Callers that need the document must know the difference.
            "dom_available": False,
            "message": f"Opened {target_url} in {browser}",
        }

        if driver_error:
            navigation_result["driver_error"] = driver_error
            navigation_result["warning"] = (
                f"Opened {target_url} in {browser}, but could not take control of "
                f"the page ({driver_error}). Anything that needs to read or fill "
                "the page will not work here."
            )

        if result.get("pid") is not None:
            navigation_result["pid"] = result["pid"]
        if warning:
            navigation_result["warning"] = warning

        self.last_url = target_url
        self.last_browser = browser
        self._last_nav_dom_available = False

        return navigation_result

    async def search_web(
        self,
        query: str,
        browser_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a web search by opening the search URL directly."""

        browser = browser_name or self.default_browser
        search_url = self.search_engine_url.format(query=quote_plus(query))

        navigation_result = await self.navigate_to_url(search_url, browser_name=browser)
        navigation_result["query"] = query

        if self.verify_with_ocr:
            verification_text = self.vision_agent.extract_text_ocr()
            if verification_text:
                navigation_result["verification"] = self._summarize_verification(query, verification_text)
            else:
                navigation_result["verification_warning"] = "OCR verification unavailable for this search."

        navigation_result["message"] = f"Searched for '{query}' in {browser}"
        return navigation_result

    async def search_site(
        self,
        query: str,
        site: Optional[str] = None,
        browser_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search within a known site by opening its search URL directly."""

        site_name = (site or self._infer_site_from_query(query) or "").lower()
        clean_query = self._remove_site_words(query, site_name)
        if not site_name:
            return await self.search_web(query, browser_name=browser_name)

        search_url = self._build_site_search_url(site_name, clean_query)
        result = await self.navigate_to_url(search_url, browser_name=browser_name)
        result["site"] = site_name
        result["query"] = clean_query
        result["message"] = f"Searched for '{clean_query}' on {site_name}"
        return result

    CONFIRMATION_TTL_SECONDS = 300

    async def confirm_submission(self, token: str) -> Dict[str, Any]:
        """Confirm and execute a previously staged submit identified by `token`."""
        ctx = self._pending_confirmations.get(token)
        if not ctx:
            return {"success": False, "error": "Invalid or expired confirmation token."}

        if time.time() - ctx.get("created", 0) > self.CONFIRMATION_TTL_SECONDS:
            del self._pending_confirmations[token]
            return {
                "success": False,
                "error": "Confirmation token expired. Please stage the form again before confirming.",
            }

        field_map = ctx.get("field_map")
        submit_sel = ctx.get("submit_selector")
        form_name = ctx.get("form_name")

        if not field_map:
            return {"success": False, "error": "No staged fields to submit."}

        if self.browser_driver:
            try:
                # attempt click on submit selector or press Enter
                if submit_sel:
                    try:
                        await self.browser_driver.page.click(submit_sel)
                    except Exception:
                        await self.browser_driver.page.keyboard.press('Enter')
                else:
                    await self.browser_driver.page.keyboard.press('Enter')

                # simple verification
                await asyncio.sleep(1.0)
                page_content = await self.extract_text_from_page()
                text = page_content.get("text", "").lower()
                if "thank you" in text or "success" in text:
                    del self._pending_confirmations[token]
                    return {
                        "success": True,
                        "submitted": True,
                        "confirmation_token": token,
                        "form_name": form_name,
                        "verification": "ok",
                        "submission_verified": True,
                    }
                else:
                    del self._pending_confirmations[token]
                    return {
                        "success": True,
                        "submitted": True,
                        "confirmation_token": token,
                        "form_name": form_name,
                        "verification": "unknown",
                        "submission_verified": False,
                        # Same meaning as submission_verified, in the key the
                        # rest of the codebase uses: the click happened, the
                        # outcome could not be confirmed.
                        "verified": False,
                        "page_text": text[:200],
                    }
            except Exception as exc:
                return {"success": False, "error": str(exc)}

        return {"success": False, "error": "Browser driver unavailable to perform submission."}

    async def find_element(
        self,
        selector: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Find a page element.
        Selector-based DOM automation is reserved for a future browser-driver layer,
        so the current implementation uses the vision agent for described targets.
        """

        if description:
            result = await self.vision_agent.find_ui_element(description)
            result["strategy"] = "vision"
            return result

        if selector:
            return {
                "found": False,
                "selector": selector,
                "strategy": "selector-placeholder",
                "message": "DOM selectors are not yet wired to a browser driver.",
            }

        return {"found": False, "error": "No selector or description provided"}

    async def verify_dom_submission(self) -> Dict[str, Any]:
        """Verify a form submission by inspecting the live page text via the
        browser driver. Returns an honest verdict: verified / rejected /
        unverified (when the page cannot be read)."""
        try:
            page = self.browser_driver.page
            content_html = await page.content()
        except Exception as exc:
            return {
                "verified": False,
                "verdict": "unverified",
                "details": f"Could not read page content after submission: {exc}",
            }

        text = re.sub(r"<[^>]+>", " ", content_html or "").lower()
        # "confirm" and "required" removed: both are common false positives -
        # a page asking the user to "confirm your details" (i.e. NOT yet
        # submitted) read as a verified success, and routine "* required
        # fields" footer text on an otherwise-successful page read as a
        # failure.
        success_keywords = ["thank you", "success", "submitted", "received", "done", "complete"]
        error_keywords = ["error", "invalid", "failed", "incorrect"]

        has_success = any(kw in text for kw in success_keywords)
        has_error = any(kw in text for kw in error_keywords)

        if has_success and not has_error:
            return {
                "verified": True,
                "verdict": "verified",
                "details": "Submission verified via DOM page content (success keywords present).",
            }
        if has_error:
            return {
                "verified": False,
                "verdict": "rejected",
                "details": "Submission verification failed: error indicator keywords found on page.",
            }
        return {
            "verified": False,
            "verdict": "unknown",
            "details": "Submission performed; no clear success or error indicators found on page.",
        }

    def click_element(self, x: int, y: int) -> Dict[str, Any]:
        """Click a specific screen location."""

        return self.system_agent.click_mouse(x, y)

    def type_in_field(self, text: str, submit: bool = False, clear_first: bool = False) -> Dict[str, Any]:
        """Type into the active field, optionally clearing it first and submitting after."""

        if clear_first:
            clear_result = self.system_agent.press_hotkey("ctrl", "a")
            if not clear_result.get("success"):
                return clear_result

        typed = self.system_agent.type_text(text)
        if not typed.get("success"):
            return typed

        if submit:
            submit_result = self.submit_form()
            if not submit_result.get("success"):
                return submit_result

        return {"success": True, "text": text, "submitted": submit}

    def submit_form(self) -> Dict[str, Any]:
        """Submit the active form using Enter."""

        return self.system_agent.press_key("enter")

    async def extract_text_from_page(self) -> Dict[str, Any]:
        """Extract visible page text through OCR."""

        await asyncio.sleep(0)
        text = self.vision_agent.extract_text_ocr()
        return {
            "success": bool(text),
            "source": "ocr",
            "text": text,
        }

    def _normalize_label_text(self, label: str) -> str:
        """Normalize label text for comparison."""
        if not label:
            return ""
        normalized = label.strip().lower()
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _label_variants(self, label: str) -> List[str]:
        """Return a set of synonyms and variants for a label."""
        normalized = self._normalize_label_text(label)
        variants = {normalized}
        for canon, syns in self.label_synonyms.items():
            if normalized == canon or normalized in syns:
                variants.add(canon)
                variants.update(syns)
            elif normalized in canon:
                variants.add(canon)
                variants.update(syns)
        return list(variants)

    def _label_match_score(self, field_name: str, candidate_text: str) -> float:
        """Score how well a candidate text matches the desired field name."""
        normalized_field = self._normalize_label_text(field_name)
        normalized_candidate = self._normalize_label_text(candidate_text)
        if not normalized_field or not normalized_candidate:
            return 0.0

        best = SequenceMatcher(None, normalized_field, normalized_candidate).ratio()
        for variant in self._label_variants(field_name):
            if variant == normalized_field:
                continue
            score = SequenceMatcher(None, variant, normalized_candidate).ratio()
            best = max(best, score)

        # Prefer exact token containment when present
        if normalized_field in normalized_candidate or normalized_candidate in normalized_field:
            best = max(best, 0.95)

        return best

    async def analyze_form(self, form_name: Optional[str] = None) -> Dict[str, Any]:
        """Analyze the currently visible form using OCR text."""

        if not self.vision_agent.is_ocr_available():
            return {
                "success": False,
                "form_name": form_name,
                "error": "OCR is not available. Install or configure Tesseract to analyze visible forms.",
                "ocr_available": False,
            }

        visible_text = self.vision_agent.extract_text_ocr()
        signature = self._build_form_signature(visible_text, form_name)
        labels = self._extract_form_labels(visible_text)
        stored_pattern = self.learning_agent.recall_form_pattern(signature)

        return {
            "success": bool(visible_text),
            "form_name": form_name,
            "form_signature": signature,
            "visible_text": visible_text,
            "detected_labels": labels,
            "known_pattern": stored_pattern,
        }

    async def intelligent_form_fill(
        self,
        field_values: Dict[str, str],
        form_name: Optional[str] = None,
        submit: bool = False,
        focus_first_field: bool = False,
        selector_confidence_threshold: Optional[float] = None,
        fuzzy_match_threshold: float = 0.6,
        require_confirmation: bool = False,
        allow_keyboard_fallback: bool = True,
    ) -> Dict[str, Any]:
        """
        Fill a form using OCR analysis, stored patterns, and keyboard navigation.
        The current workflow assumes the browser is open and focus is on the page.
        """

        # If the last navigation only LAUNCHED a browser, there is no page
        # under our control. The keyboard fallback would still "succeed" by
        # typing into whatever window happens to be focused and counting the
        # keystrokes as filled fields - which is how filling a form on a page
        # that failed to load reported four fields filled.
        if getattr(self, "_last_nav_dom_available", None) is False:
            return {
                "success": False,
                "requires_user_attention": True,
                "error": (
                    "The page is not under my control - the last navigation only "
                    "opened a browser window. I will not type into whatever "
                    "happens to be focused. Reopen the page and try again."
                ),
                "fields_filled": [],
                "fill_method": "refused_no_dom",
            }

        from core import progress
        progress.update("Filling the form")

        analysis = await self.analyze_form(form_name=form_name)
        field_sequence = self._build_field_sequence(field_values, analysis if analysis.get("success") else {})
        executed_fields: List[Dict[str, str]] = []
        warnings: List[str] = []

        if not field_sequence:
            return {
                "success": False,
                "error": "No form fields were provided for filling.",
                "analysis": analysis,
            }
        # override threshold per-call if provided
        if selector_confidence_threshold is None:
            selector_confidence_threshold = self.selector_confidence_threshold

        selection_log: List[Dict[str, Any]] = []
        fallback_reasons: List[str] = []

        # If a browser driver is available, try selector-based filling first
        if self.browser_driver:
            try:
                # build label variants (include synonyms) to improve discovery
                label_variants = []
                variant_to_field = {}
                for f in field_sequence:
                    name = f["name"]
                    variants = [name]
                    for canon, syns in self.label_synonyms.items():
                        if name.lower() == canon or name.lower() in syns:
                            variants = [name, canon] + syns
                            break
                    # also include lowercase and stripped variants
                    extra = [v for v in [name.lower().strip()] if v not in variants]
                    variants.extend(extra)
                    for v in variants:
                        label_variants.append(v)
                        variant_to_field[v] = name

                mapping = await self.browser_driver.find_selectors_for_labels(label_variants)
                field_map = {}
                # choose best variant per original field
                for f in field_sequence:
                    name = f["name"]
                    best_sel = None
                    best_conf = 0.0
                    used_variant = None
                    for variant, orig in variant_to_field.items():
                        if orig != name:
                            continue
                        entry = mapping.get(variant) if mapping else None
                        if entry and entry.get("selector"):
                            conf = float(entry.get("confidence", 0.0))
                            label_score = self._label_match_score(name, variant)
                            overall_score = conf * 0.85 + label_score * 0.15
                            if overall_score > best_conf:
                                best_conf = overall_score
                                best_sel = entry.get("selector")
                                used_variant = variant
                    if best_sel and best_conf >= self.selector_confidence_threshold:
                        field_map[best_sel] = f["value"]
                        executed_fields.append({"name": name, "selector": best_sel, "variant": used_variant, "confidence": best_conf})
                        if self.verbose_logging:
                            logger.debug(
                                "Mapped field '%s' -> selector '%s' (variant=%s, combined_conf=%.2f, label_score=%.2f)",
                                name,
                                best_sel,
                                used_variant,
                                best_conf,
                                self._label_match_score(name, used_variant),
                            )

                submit_sel = None
                try:
                    submit_sel = await self.browser_driver.find_submit_selector()
                except Exception:
                    submit_sel = None

                if field_map:
                    if not allow_keyboard_fallback:
                        expected_fields = {field["name"] for field in field_sequence}
                        mapped_fields = {field.get("name") for field in executed_fields}
                        missing_fields = sorted(expected_fields - mapped_fields)
                        if missing_fields:
                            return {
                                "success": False,
                                "partial_success": True,
                                "requires_user_attention": True,
                                "error": "Only some requested form fields were confidently mapped.",
                                "fields_filled": executed_fields,
                                "missing_fields": missing_fields,
                                "detected_labels": analysis.get("detected_labels", []),
                                "selection_log": selection_log,
                                "fallback_reasons": fallback_reasons,
                                "fill_method": "dom_selector_required",
                            }
                    # If confirmation is required, fill fields but do not submit; store pending token
                    if require_confirmation and submit:
                        # fill without submitting
                        fill_result = await self.browser_driver.fill_fields(field_map, submit_selector=None)
                        token = str(uuid.uuid4())
                        self._pending_confirmations[token] = {
                            "field_map": field_map,
                            "submit_selector": submit_sel,
                            "form_name": form_name,
                            "created": time.time(),
                        }
                        return {
                            "success": True,
                            "requires_confirmation": True,
                            "confirmation_token": token,
                            "fields_filled": executed_fields,
                        }
                    else:
                        fill_result = await self.browser_driver.fill_fields(field_map, submit_selector=None)
                    if not fill_result.get("success"):
                        # fall through to keyboard-based filling
                        pass
                    else:
                        submitted = False
                        if submit and submit_sel:
                            try:
                                await self.browser_driver.page.click(submit_sel)
                                submitted = True
                            except Exception:
                                try:
                                    await self.browser_driver.page.keyboard.press('Enter')
                                    submitted = True
                                except Exception:
                                    pass
                        elif submit:
                            try:
                                await self.browser_driver.page.keyboard.press('Enter')
                                submitted = True
                            except Exception:
                                pass
                        submission_verified = False
                        verification_details = "Not submitted or verification skipped"
                        if submitted:
                            await asyncio.sleep(1.0)
                            dom_check = await self.verify_dom_submission()
                            submission_verified = dom_check["verified"]
                            verification_details = dom_check["details"]
                        # record direct selections
                        for ef in executed_fields:
                            selection_log.append({"field": ef.get("name"), "method": "direct", "selector": ef.get("selector"), "confidence": ef.get("confidence")})
                        
                        # Only report success if we filled all expected fields via DOM
                        expected_fields = {field["name"] for field in field_sequence}
                        mapped_fields = {field.get("name") for field in executed_fields}
                        all_fields_mapped = expected_fields == mapped_fields
                        
                        return {
                            "success": all_fields_mapped,
                            "partial_success": bool(executed_fields) and not all_fields_mapped,
                            "requires_user_attention": not all_fields_mapped,
                            "form_name": form_name,
                            "fields_filled": executed_fields,
                            "missing_fields": sorted(expected_fields - mapped_fields) if not all_fields_mapped else [],
                            "fill_method": "dom_selector",
                            "submitted": submitted,
                            "submission_verified": submission_verified,
                            "verification_details": verification_details,
                            "confidence_level": "high" if all_fields_mapped else "medium",
                        }
            except Exception:
                # If any driver-based step fails, continue with fallback method
                pass

            # If some fields weren't mapped by confidence, try fuzzy matching against page label candidates
            if self.browser_driver:
                try:
                    candidates = await self.browser_driver.find_label_candidates()
                except Exception:
                    candidates = []

                for f in field_sequence:
                    name = f["name"]
                    if any(name == ef.get("name") for ef in executed_fields):
                        continue
                    best = (None, 0.0)
                    for c in candidates:
                        text = (c.get("text") or "").strip()
                        if not text:
                            continue
                        score = self._label_match_score(name, text)
                        if score > best[1]:
                            best = (c, score)
                    if best[0] and best[1] >= fuzzy_match_threshold:
                        sel = best[0].get("selector")
                        if sel:
                            try:
                                fill_result = await self.browser_driver.fill_fields({sel: f["value"]})
                                if fill_result.get("success"):
                                    executed_fields.append({"name": name, "selector": sel})
                                    selection_log.append({"field": name, "method": "fuzzy", "selector": sel, "score": best[1]})
                                    continue
                            except Exception:
                                fallback_reasons.append(f"fuzzy_fill_failed:{name}")
                    else:
                        fallback_reasons.append(f"no_candidate_confident:{name}")

            if not allow_keyboard_fallback:
                expected_fields = {field["name"] for field in field_sequence}
                mapped_fields = {field.get("name") for field in executed_fields}
                missing_fields = sorted(expected_fields - mapped_fields)
                if missing_fields:
                    return {
                        "success": False,
                        "partial_success": bool(executed_fields),
                        "requires_user_attention": True,
                        "error": "Could not confidently map all requested form fields.",
                        "fields_filled": executed_fields,
                        "missing_fields": missing_fields,
                        "detected_labels": analysis.get("detected_labels", []),
                        "selection_log": selection_log,
                        "fallback_reasons": fallback_reasons,
                        "fill_method": "dom_selector_required",
                    }

        if not analysis.get("success"):
            warnings.append(
                analysis.get("error", "Could not analyze the visible form before filling. Falling back to sequential typing.")
            )

        # The keyboard fallback types into whatever window currently holds OS
        # focus - it has no way to confirm it is aimed at the intended form.
        # Refuse outright when the values are sensitive, or when we could not
        # locate the first field on screen and would be typing blind after a
        # bare Tab. Silently typing a password into whatever happens to be
        # focused is not an acceptable failure mode.
        sensitive_fields = [
            field["name"] for field in field_sequence
            if any(marker in field["name"].lower()
                   for marker in ("password", "passwd", "pwd", "pin", "cvv", "card", "secret", "token", "ssn"))
        ]
        if sensitive_fields:
            return {
                "success": False,
                "requires_user_attention": True,
                "error": (
                    "Refusing to type sensitive values (" + ", ".join(sensitive_fields) + ") "
                    "without confirmed field targeting. This fallback types into whatever "
                    "window has focus, so it cannot guarantee where the text lands. "
                    "Please fill these fields yourself, or use a page the browser driver "
                    "can address directly."
                ),
                "fields_filled": executed_fields,
                "missing_fields": sensitive_fields,
                "fill_method": "refused_sensitive_keyboard_fallback",
            }

        if focus_first_field and field_sequence:
            first_field_name = field_sequence[0]["name"]
            target_label = first_field_name
            detected_labels = analysis.get("detected_labels", [])
            for label in detected_labels:
                if first_field_name.lower() in label.lower() or label.lower() in first_field_name.lower():
                    target_label = label
                    break

            coords = self.vision_agent.find_text_coordinates(target_label)
            if not coords:
                return {
                    "success": False,
                    "requires_user_attention": True,
                    "error": (
                        f"Could not locate the '{first_field_name}' field on screen, so I "
                        "cannot confirm where typing would go. Stopping instead of typing "
                        "blind into the focused window."
                    ),
                    "fields_filled": executed_fields,
                    "detected_labels": detected_labels,
                    "fill_method": "refused_unlocated_field",
                }

            x, y = coords
            # The +45 offset assumes a label-above-input layout at a specific
            # DPI/zoom; it is a guess, so a failed click is a hard stop rather
            # than a Tab-and-hope.
            click_result = self.click_element(x, y + self.label_to_input_offset_px)
            if not click_result.get("success"):
                return {
                    "success": False,
                    "requires_user_attention": True,
                    "error": (
                        f"Could not focus the '{first_field_name}' field. Stopping rather "
                        "than typing into an unconfirmed target."
                    ),
                    "fields_filled": executed_fields,
                    "fill_method": "refused_unfocused_field",
                }
            await asyncio.sleep(self.form_field_delay_seconds)


        for index, field in enumerate(field_sequence):
            typed = self.type_in_field(field["value"], submit=False, clear_first=index == 0)
            if not typed.get("success"):
                return {
                    "success": False,
                    "error": f"Failed while filling '{field['name']}'",
                    "analysis": analysis,
                    "completed_fields": executed_fields,
                }

            executed_fields.append(field)

            if index < len(field_sequence) - 1:
                tab_result = self.system_agent.press_key("tab")
                if not tab_result.get("success"):
                    return {
                        "success": False,
                        "error": "Failed to move to the next form field.",
                        "analysis": analysis,
                        "completed_fields": executed_fields,
                    }
                await asyncio.sleep(self.form_field_delay_seconds)

        submission_verified = False
        verification_details = "Not submitted or verification skipped"

        if submit:
            await asyncio.sleep(self.form_submit_delay_seconds)
            submit_result = self.submit_form()
            if not submit_result.get("success"):
                return {
                    "success": False,
                    "error": "Form fields were entered, but submit failed.",
                    "analysis": analysis,
                    "completed_fields": executed_fields,
                }
            
            # Post-submission verification check using OCR (Priority 2, Task 4)
            if self.vision_agent.is_ocr_available():
                await asyncio.sleep(2.0)
                page_content = await self.extract_text_from_page()
                page_text = page_content.get("text", "").lower()

                success_keywords = ["thank you", "success", "submitted", "received", "done", "confirm", "complete"]
                error_keywords = ["error", "invalid", "required", "failed", "incorrect"]

                has_success = any(kw in page_text for kw in success_keywords)
                has_error = any(kw in page_text for kw in error_keywords)

                if has_success and not has_error:
                    submission_verified = True
                    verification_details = "Submission verified successfully via success keywords."
                elif has_error:
                    submission_verified = False
                    verification_details = "Submission verification failed. Error indicator keywords found in page."
                else:
                    submission_verified = True
                    verification_details = "Form submitted; no clear success or error indicators detected."
            else:
                submission_verified = True
                verification_details = "Form submitted, but OCR verification was unavailable."
                warnings.append("OCR verification unavailable after submission.")

        self.learning_agent.remember_form_pattern(
            analysis.get("form_signature", self._build_form_signature("", form_name)),
            [field["name"] for field in field_sequence],
            metadata={"form_name": form_name, "detected_labels": analysis.get("detected_labels", [])},
        )

        # Enhanced success validation for keyboard fallback
        expected_fields = {field["name"] for field in field_sequence}
        filled_fields = {field.get("name") for field in executed_fields}
        all_fields_filled = expected_fields == filled_fields
        
        success = all_fields_filled
        if submit and not submission_verified:
            success = False
        
        result = {
            "success": success,
            "partial_success": bool(executed_fields) and not all_fields_filled,
            "requires_user_attention": not all_fields_filled or (submit and not submission_verified),
            "form_name": form_name,
            "form_signature": analysis.get("form_signature", self._build_form_signature("", form_name)),
            "fields_filled": executed_fields,
            "missing_fields": sorted(expected_fields - filled_fields) if not all_fields_filled else [],
            "detected_labels": analysis.get("detected_labels", []),
            "submitted": submit,
            "submission_verified": submission_verified,
            "verification_details": verification_details,
            "warnings": warnings,
            "selection_log": selection_log,
            "fallback_reasons": fallback_reasons,
            "fill_method": "keyboard_fallback" if not self.browser_driver or not selection_log else "mixed",
            "confidence_level": "low" if not all_fields_filled else "medium",
        }

        return result

    def _normalize_url(self, url: str) -> str:
        """Ensure URLs include a scheme."""

        cleaned = url.strip()
        if not cleaned:
            return self.search_engine_url.format(query="")

        # Any real scheme is left alone. Checking only http/https turned
        # "file:///C:/..." into "https://file///C:/..." - a hostname called
        # "file" that will never resolve.
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", cleaned):
            return cleaned
        # Schemes without a "//" authority: mailto:, about:, data:, tel:
        if re.match(r"^(?:mailto|about|data|tel|chrome|edge|view-source):", cleaned):
            return cleaned
        return f"https://{cleaned}"

    def _infer_site_from_query(self, query: str) -> Optional[str]:
        lowered = (query or "").lower()
        for site in ["amazon", "flipkart", "youtube", "google", "bing"]:
            if site in lowered:
                return site
        if self.last_url:
            domain = urlparse(self.last_url).netloc.lower()
            for site in ["amazon", "flipkart", "youtube", "google", "bing"]:
                if site in domain:
                    return site
        return None

    def _remove_site_words(self, query: str, site: str) -> str:
        cleaned = (query or "").strip()
        if site:
            for phrase in [f"on {site}", f"in {site}", f"{site} for", site]:
                cleaned = cleaned.replace(phrase, "", 1).strip(" ,")
        return cleaned or query

    def _build_site_search_url(self, site: str, query: str) -> str:
        encoded = quote_plus(query)
        if site == "amazon":
            return f"https://www.amazon.in/s?k={encoded}"
        if site == "flipkart":
            return f"https://www.flipkart.com/search?q={encoded}"
        if site == "youtube":
            return f"https://www.youtube.com/results?search_query={encoded}"
        if site == "bing":
            return f"https://www.bing.com/search?q={encoded}"
        return self.search_engine_url.format(query=encoded)

    def _summarize_verification(self, query: str, page_text: str) -> Dict[str, Any]:
        """Return a simple OCR verification summary for browser actions."""

        query_words = [word for word in query.lower().split() if len(word) > 2]
        visible_words = page_text.lower()
        matched_words = [word for word in query_words if word in visible_words]

        return {
            "matched_words": matched_words,
            "match_ratio": round(len(matched_words) / len(query_words), 2) if query_words else 0.0,
        }

    def _build_form_signature(self, visible_text: str, form_name: Optional[str]) -> str:
        basis = (form_name or "").lower().strip()
        if not basis:
            lines = [line.strip().lower() for line in visible_text.splitlines() if line.strip()]
            basis = "|".join(lines[:5])
        return basis[:200] or "generic-form"

    def _extract_form_labels(self, visible_text: str) -> List[str]:
        labels = []
        for line in visible_text.splitlines():
            cleaned = line.strip().rstrip(":")
            if cleaned and len(cleaned.split()) <= 4:
                labels.append(cleaned)
        return labels[:12]

    def _build_field_sequence(
        self,
        field_values: Dict[str, str],
        analysis: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        stored_pattern = analysis.get("known_pattern") or {}
        preferred_order = stored_pattern.get("field_order", [])
        remaining = {key.strip().lower(): value for key, value in field_values.items()}
        sequence: List[Dict[str, str]] = []

        for field_name in preferred_order:
            normalized = field_name.strip().lower()
            if normalized in remaining:
                sequence.append({"name": field_name, "value": remaining.pop(normalized)})

        for key, value in field_values.items():
            normalized = key.strip().lower()
            if normalized in remaining:
                sequence.append({"name": key, "value": remaining.pop(normalized)})

        return sequence
