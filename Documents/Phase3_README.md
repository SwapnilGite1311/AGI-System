# Phase 3: Web Automation & Ollama Helpers

## What this phase includes

- Playwright-based browser automation via `AGI-System/agents/browser_driver.py`
- Automatic selector discovery for form labels
- Submit-button detection and robust submit handling
- Post-submit verification using OCR and page content checks
- `SystemAgent` helpers for Ollama health checks and startup
- Integration tests for form filling and Ollama helper behavior

## Configuration

Update `AGI-System/config/settings.json`:

```json
"web_automation": {
  "driver": "playwright",
  "driver_browser": "chromium",
  "browsers_path": "C:\\ms-playwright",
  "headless": true
}
```

## Playwright Setup

Install the Python package and Chromium browser binaries:

```powershell
& "C:\Users\Swapnil gite\AppData\Local\Programs\Python\Python313\python.exe" -m pip install playwright
$env:PLAYWRIGHT_BROWSERS_PATH="C:\ms-playwright"
& "C:\Users\Swapnil gite\AppData\Local\Programs\Python\Python313\python.exe" -m playwright install chromium
```

Optional: persist the browser binary location for future terminals:

```powershell
setx PLAYWRIGHT_BROWSERS_PATH "C:\ms-playwright"
```

## Running tests

From `AGI-System`:

```powershell
& "C:\Users\Swapnil gite\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests -rs
```

If Playwright is installed and supported, the integration test will run. If not, it is skipped.

## Notes

	`WebAgent` supports a confirmation flow: call `intelligent_form_fill(..., require_confirmation=True, submit=True)` to stage a submit and receive a `confirmation_token`; call `WebAgent.confirm_submission(token)` to execute the final submit.

## Debug & Matching Enhancements

- `web_automation.verbose_logging`: enable debug logs for selector mapping and fuzzy matches.
- Label synonyms and fuzzy matching are used to improve selector discovery.
- `SystemAgent.health_check_ollama()` verifies that the Ollama host responds.
