# UI Detector - Scoping Document (Task #22)

Status: SCOPING ONLY - implementation deferred until tasks #20/#21 land.
Author: Team Lead | Date: 2026-08-23

## Problem
ASC automates browsers reliably (DOM via Playwright) but is blind inside
native/desktop applications (Excel, Tally, legacy ERP clients, anything without
a DOM). `vision/ui_detector.py` was reserved for this; it is currently empty.

## What "UI detection" must achieve
Given a live window or screenshot:
1. Locate interactive elements (buttons, fields, menus) as clickable targets
2. Read their labels/state (enabled, selected)
3. Expose them to the planner as actions ("click 'Save'", "type into 'Invoice No'")

## Candidate approaches

### A. Windows UI Automation API (pywinauto / uiautomation)
- Semantic tree of every control: name, type, coordinates, state
- No vision/ML needed; works on WinForms/WPF/Qt/most modern apps
- Fails on: canvas-rendered UIs (games, remote desktop), elevated-admin windows
- Effort: ~2-3 day spike; large win

### B. OCR anchor boxes (pytesseract image_to_data)
- Screenshot -> word bounding boxes -> match label text -> click center
- Works everywhere text is visible, including VDI/canvas
- Brittle for icons/unlabeled controls; DPI-scaling sensitive
- Effort: ~2 days; complements A

### C. Template matching (OpenCV)
- Icon/button image matching; only viable for fixed-UI repeated workflows
- High maintenance; NOT recommended except narrow cases

## Recommendation
Hybrid, priority order: **A primary, B fallback**.
A gives semantic reliability where available; B covers the rest.
C skipped.

## Integration points
- `agents/web_agent.py` keyboard+OCR fallback path consumes detector output
- Planner gains new action `ui_click` / `ui_type` routed through SystemAgent
- VisionAgent screenshots feed B when A has no tree access

## Risks
| Risk | Mitigation |
|---|---|
| DPI scaling offsets clicks | use per-monitor DPI-aware coordinates from API, not pixels |
| Elevated (admin) windows unreadable | detect + report honestly, request elevation flow |
| Dynamic/animated content | re-query tree per action, never cache coordinates long |

## Suggested milestones
1. M1 (spike): enumerate controls of Notepad + Excel via pywinauto; print tree
2. M2: `ui_click`/`ui_type` actions end-to-end in main.py plan executor
3. M3: OCR fallback for one canvas app; intent-matrix entries added
