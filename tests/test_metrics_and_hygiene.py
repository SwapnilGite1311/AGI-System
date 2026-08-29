"""Metrics reporting and data hygiene.

Both exist because the live stores had accumulated test-run residue: 1,026
tasks of which 27 were distinct, 156 "team members" that were four people
repeated, 573 projects mostly named some form of "Test Project". Every
analytic was computed over that.

The metrics surface must never invent a figure it cannot compute - that is
the exact failure already removed from the analytics module.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import data_hygiene, metrics  # noqa: E402


# --------------------------------------------------------------------------
# Data hygiene
# --------------------------------------------------------------------------

@pytest.fixture
def dirty(tmp_path):
    (tmp_path / "business_tasks.json").write_text(json.dumps({"tasks": [
        {"id": "1", "title": "Real work", "status": "pending"},
        {"id": "2", "title": "Test Task", "status": "pending"},
        {"id": "3", "title": "Real work", "status": "pending"},   # duplicate
        {"id": "4", "title": "", "status": "pending"},            # unlabelled
    ]}), encoding="utf-8")
    (tmp_path / "team_members.json").write_text(json.dumps([
        {"id": "a", "name": "Priya", "email": "priya@corp.io", "role": "dev"},
        {"id": "b", "name": "John Doe", "email": "john_b7f93939@example.com", "role": "dev"},
        {"id": "c", "name": "John Doe", "email": "john_5cd65ec5@example.com", "role": "dev"},
    ]), encoding="utf-8")
    (tmp_path / "projects.json").write_text(json.dumps([
        {"id": "p1", "name": "Launch"},
        {"id": "p2", "name": "Test Project"},
    ]), encoding="utf-8")
    return tmp_path


def test_analyse_changes_nothing_on_disk(dirty):
    before = (dirty / "business_tasks.json").read_bytes()
    data_hygiene.analyse(dirty)
    assert (dirty / "business_tasks.json").read_bytes() == before


def test_junk_and_duplicates_are_identified(dirty):
    report = data_hygiene.analyse(dirty)
    tasks = report["files"]["business_tasks.json"]
    assert tasks["before"] == 4
    assert tasks["after"] == 1, "only the one genuine distinct task should survive"
    assert tasks["junk_removed"] >= 1
    assert tasks["duplicates_removed"] >= 1


def test_randomised_test_emails_are_recognised_as_fixtures(dirty):
    """39 copies of "John Doe" survived dedup because each had a unique
    generated address (john_b7f93939@example.com)."""
    report = data_hygiene.analyse(dirty)
    team = report["files"]["team_members.json"]
    assert team["after"] == 1, "generated-email duplicates were not detected"


def test_a_real_person_is_never_removed(dirty):
    data_hygiene.clean(dirty, dry_run=False)
    remaining = json.loads((dirty / "team_members.json").read_text(encoding="utf-8"))
    assert [m["name"] for m in remaining] == ["Priya"]


def test_clean_writes_a_backup_before_touching_anything(dirty):
    report = data_hygiene.clean(dirty, dry_run=False)
    backup = Path(report["backup"])
    assert backup.is_dir()
    restored = json.loads((backup / "business_tasks.json").read_text(encoding="utf-8"))
    assert len(restored["tasks"]) == 4, "backup does not hold the original records"


def test_dry_run_is_the_default(dirty):
    before = (dirty / "projects.json").read_bytes()
    report = data_hygiene.clean(dirty)
    assert report["dry_run"] is True
    assert (dirty / "projects.json").read_bytes() == before


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def test_metrics_never_fabricate_missing_figures(tmp_path):
    """An empty data directory must yield None, not a plausible number."""
    report = metrics.collect(tmp_path)
    assert report["workload"] == {"tasks": None, "projects": None, "team_members": None}
    # No journal exists, so routing/reliability must be absent rather than zeroed.
    assert "routing" not in report or report["routing"]["commands_recorded"] == 0


def test_metrics_report_the_real_host():
    report = metrics.collect(Path("data"))
    host = report["host"]
    assert host["platform"]
    assert host["python"]


def test_metrics_render_without_a_datastore(tmp_path):
    """render_text must not crash on a partial report."""
    text = metrics.render_text(metrics.collect(tmp_path))
    assert "VEGA" in text
    assert "no data leaves this machine" in text


def test_real_metrics_are_internally_consistent():
    report = metrics.collect(Path("data"))
    reliability = report.get("reliability")
    if reliability and reliability.get("attempted"):
        assert reliability["succeeded"] <= reliability["attempted"]
        assert 0.0 <= reliability["success_rate"] <= 1.0

    routing = report.get("routing")
    if routing and routing.get("commands_recorded"):
        assert sum(routing["by_tier"].values()) == routing["commands_recorded"]
        assert 0.0 <= routing["model_free_share"] <= 1.0

    memory = report.get("memory")
    if memory and memory.get("episodes"):
        assert memory["embedded"] <= memory["episodes"]
