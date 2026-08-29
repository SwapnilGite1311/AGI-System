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
from openpyxl import Workbook
from loguru import logger


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
        logger.success("Created Word document: {}", target)
        return {"success": True, "path": str(target), "sections": len(sections)}
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
        logger.success("Created spreadsheet: {}", target)
        return {"success": True, "path": str(target), "rows": len(rows)}
    except Exception as exc:
        logger.error("Spreadsheet creation failed: {}", str(exc))
        return {"success": False, "error": str(exc)}
