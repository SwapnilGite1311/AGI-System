"""
Real document and spreadsheet generation.

Fills a gap the original audit called out directly: VEGA's "reports" were
plain .txt dumps of raw scraped step descriptions, and a stray
strategic_planning_summary.docx in the repo turned out to be a 34-byte text
file with the wrong extension - there was no real document generation at
all. This uses python-docx/openpyxl to produce actual Word documents and
Excel spreadsheets.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from docx import Document
from openpyxl import Workbook, load_workbook
from loguru import logger


def _verify_written(target: Path, reopen) -> Optional[str]:
    """Confirm a written document is actually usable.

    Returns None when the file is fine, or a description of what is wrong.
    Saving raises on most failures, but not all of them: a zero-byte file
    or one that cannot be re-opened is a real outcome that used to be
    reported as success.
    """
    try:
        if not target.exists():
            return f"{target} was reported written but is not on disk"
        size = target.stat().st_size
        if size == 0:
            return f"{target} was written but is empty"
    except OSError as exc:
        return f"{target} could not be inspected after writing: {exc}"

    try:
        reopen(str(target))
    except Exception as exc:
        return (f"{target} was written but cannot be re-opened "
                f"({type(exc).__name__}: {exc})")
    return None


def create_word_document(
    path: str,
    title: str,
    sections: List[Union[str, Dict[str, str]]],
) -> Dict[str, Any]:
    """Create a real .docx file with a title and a list of sections.

    Each section is either a plain paragraph string, or
    {"heading": "...", "body": "..."} for a heading + paragraph.
    """
    try:
        target = Path(path)
        if target.suffix.lower() != ".docx":
            target = target.with_suffix(".docx")
        target.parent.mkdir(parents=True, exist_ok=True)

        document = Document()
        document.add_heading(title or "Document", level=1)

        for section in sections:
            if isinstance(section, dict):
                heading = section.get("heading")
                body = section.get("body", "")
                if heading:
                    document.add_heading(str(heading), level=2)
                if body:
                    document.add_paragraph(str(body))
            else:
                document.add_paragraph(str(section))

        document.save(str(target))

        problem = _verify_written(target, Document)
        if problem:
            logger.error("Word document verification failed: {}", problem)
            return {"success": False, "error": problem, "path": str(target)}

        logger.success("Created Word document: {}", target)
        return {
            "success": True,
            "path": str(target),
            "sections": len(sections),
            "size": target.stat().st_size,
            "verified": True,
        }
    except Exception as exc:
        logger.error("Word document creation failed: {}", str(exc))
        return {"success": False, "error": str(exc)}


def create_spreadsheet(
    path: str,
    sheet_name: str,
    rows: List[List[Any]],
    header: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a real .xlsx file. `rows` is a list of row value-lists;
    `header`, if given, becomes a bold-ish first row."""
    try:
        target = Path(path)
        if target.suffix.lower() != ".xlsx":
            target = target.with_suffix(".xlsx")
        target.parent.mkdir(parents=True, exist_ok=True)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = (sheet_name or "Sheet1")[:31]  # Excel's own sheet-name length limit

        if header:
            sheet.append(header)
        for row in rows:
            sheet.append(row)

        workbook.save(str(target))

        problem = _verify_written(target, load_workbook)
        if problem:
            logger.error("Spreadsheet verification failed: {}", problem)
            return {"success": False, "error": problem, "path": str(target)}

        logger.success("Created spreadsheet: {}", target)
        return {
            "success": True,
            "path": str(target),
            "rows": len(rows),
            "size": target.stat().st_size,
            "verified": True,
        }
    except Exception as exc:
        logger.error("Spreadsheet creation failed: {}", str(exc))
        return {"success": False, "error": str(exc)}
