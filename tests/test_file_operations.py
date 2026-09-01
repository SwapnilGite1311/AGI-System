"""File operation tests.

agents/file_agent.py sat at 16% coverage while owning every destructive
operation in the system - delete, move, batch-rename, and the organize/undo
pair. The safety guard had tests; the operations it guards did not. These
exercise the real methods against real files in a temp tree.

Nothing here touches a path outside pytest's tmp_path.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.file_agent import FileAgent  # noqa: E402


CONFIG = str(Path(__file__).resolve().parents[1] / "config" / "settings.json")


@pytest.fixture
def agent():
    return FileAgent(CONFIG)


@pytest.fixture
def tree(tmp_path):
    """A small realistic folder: mixed types, a duplicate pair, a nested dir."""
    (tmp_path / "notes.txt").write_text("hello world", encoding="utf-8")
    (tmp_path / "report.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff fake jpeg")
    (tmp_path / "script.py").write_text("print('hi')", encoding="utf-8")
    # exact duplicate content, different name
    (tmp_path / "copy_of_notes.txt").write_text("hello world", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "inner.txt").write_text("inner", encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# create / delete
# --------------------------------------------------------------------------

def test_create_and_delete_file_round_trip(agent, tmp_path):
    target = tmp_path / "made.txt"
    created = agent.create_file(str(target), "some content")
    assert created["success"] is True
    assert target.read_text(encoding="utf-8") == "some content"
    assert created["size"] == len("some content")

    deleted = agent.delete_file(str(target))
    assert deleted["success"] is True
    assert not target.exists()


def test_delete_file_refuses_a_directory(agent, tmp_path):
    folder = tmp_path / "adir"
    folder.mkdir()
    result = agent.delete_file(str(folder))
    assert result["success"] is False
    assert folder.exists(), "a directory must survive delete_file"


def test_delete_folder_requires_recursive_when_not_empty(agent, tmp_path):
    folder = tmp_path / "full"
    folder.mkdir()
    (folder / "child.txt").write_text("x", encoding="utf-8")

    guarded = agent.delete_folder(str(folder), recursive=False)
    assert guarded["success"] is False
    assert folder.exists(), "non-empty folder deleted without recursive=True"

    forced = agent.delete_folder(str(folder), recursive=True)
    assert forced["success"] is True
    assert not folder.exists()


def test_destructive_ops_refuse_paths_outside_the_allowed_roots(agent):
    """The guard must actually block, not just be present."""
    outside = Path("C:/Windows/System32") if sys.platform == "win32" else Path("/etc")
    result = agent.delete_folder(str(outside), recursive=True)
    assert result["success"] is False
    assert "refusing" in result["error"].lower()
    assert outside.exists(), "guard let a system directory through"


# --------------------------------------------------------------------------
# move / copy
# --------------------------------------------------------------------------

def test_move_file_relocates_and_creates_parents(agent, tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("payload", encoding="utf-8")
    dst = tmp_path / "deep" / "sub" / "moved.txt"

    result = agent.move_file(str(src), str(dst))
    assert result["success"] is True
    assert dst.read_text(encoding="utf-8") == "payload"
    assert not src.exists(), "source should be gone after a move"


def test_copy_file_leaves_the_original(agent, tmp_path):
    src = tmp_path / "orig.txt"
    src.write_text("payload", encoding="utf-8")
    dst = tmp_path / "copy.txt"

    result = agent.copy_file(str(src), str(dst))
    assert result["success"] is True
    assert src.exists(), "copy must not remove the source"
    assert dst.read_text(encoding="utf-8") == "payload"


# --------------------------------------------------------------------------
# organize + undo  (the highest-risk pair: an un-undoable organize is
# effectively data loss spread across a folder)
# --------------------------------------------------------------------------

def test_organize_then_restore_returns_every_file_to_its_original_place(agent, tree):
    before = {p.name: p.read_bytes() for p in tree.iterdir() if p.is_file()}
    assert before, "fixture produced no files"

    organized = agent.organize_folder(str(tree))
    assert organized["success"] is True, organized.get("error")

    # Files moved into category subfolders - none left loose at the top.
    still_loose = [p.name for p in tree.iterdir() if p.is_file()]
    assert not still_loose, f"organize left files unsorted: {still_loose}"

    manifest_id = organized.get("manifest_id") or organized.get("undo_id")
    restored = agent.restore_organization(manifest_id)
    assert restored["success"] is True, restored.get("error")

    after = {p.name: p.read_bytes() for p in tree.iterdir() if p.is_file()}
    assert after == before, "undo did not restore the original layout byte-for-byte"


def test_restore_with_unknown_manifest_fails_cleanly(agent):
    result = agent.restore_organization("no-such-manifest-id")
    assert result["success"] is False
    assert result.get("error")


# --------------------------------------------------------------------------
# search / analysis
# --------------------------------------------------------------------------

def test_search_files_matches_on_name(agent, tree):
    # Signature is (folderpath, query) - folder first.
    results = agent.search_files(str(tree), "notes")
    names = {r["name"] for r in results}
    assert "notes.txt" in names
    assert all("match_type" in r for r in results)


def test_search_files_can_match_on_content(agent, tree):
    results = agent.search_files(str(tree), "hello world", search_content=True)
    assert any(r.get("match_type") == "content" for r in results), \
        "content search found nothing despite a known match"


def test_find_duplicate_files_pairs_identical_content(agent, tree):
    result = agent.find_duplicate_files(str(tree))
    assert result["success"] is True
    # `duplicates` is a dict keyed by content hash -> {size_bytes, files[]}.
    assert result["duplicates_found"] >= 1
    flattened = " ".join(
        f for group in result["duplicates"].values() for f in group["files"]
    )
    assert "notes.txt" in flattened and "copy_of_notes.txt" in flattened, \
        "the known duplicate pair was not reported"


def test_analyze_disk_usage_reports_a_real_total(agent, tree):
    result = agent.analyze_disk_usage(str(tree))
    assert result["success"] is True
    total = (result.get("total_size") or result.get("total_size_bytes")
             or result.get("total_bytes") or 0)
    on_disk = sum(p.stat().st_size for p in tree.rglob("*") if p.is_file())
    assert total > 0
    assert abs(total - on_disk) <= on_disk * 0.05, "reported size is not the real size"


def test_list_files_reports_files_and_folders(agent, tree):
    listed = agent.list_files(str(tree))
    names = {item["name"] for item in listed}
    assert "notes.txt" in names and "nested" in names
    nested = next(i for i in listed if i["name"] == "nested")
    assert nested["is_folder"] is True and nested["is_file"] is False


def test_get_file_info_returns_real_metadata(agent, tree):
    info = agent.get_file_info(str(tree / "notes.txt"))
    assert info["success"] is True
    assert info["size_bytes"] == len("hello world")
    assert info["name"] == "notes.txt"
    assert info.get("modified")


# --------------------------------------------------------------------------
# batch rename / backup
# --------------------------------------------------------------------------

def test_batch_rename_only_touches_matching_files(agent, tmp_path):
    (tmp_path / "draft_one.txt").write_text("1", encoding="utf-8")
    (tmp_path / "draft_two.txt").write_text("2", encoding="utf-8")
    (tmp_path / "keep.md").write_text("3", encoding="utf-8")

    result = agent.batch_rename_files(str(tmp_path), "draft", "final", extension=".txt")
    assert result["success"] is True

    names = {p.name for p in tmp_path.iterdir()}
    assert "final_one.txt" in names and "final_two.txt" in names
    assert "keep.md" in names, "a non-matching file was renamed"
    assert "draft_one.txt" not in names


def test_backup_folder_copies_everything(agent, tree):
    result = agent.backup_folder(str(tree), backup_name="probe_backup")
    assert result["success"] is True, result.get("error")
    backup_path = Path(result.get("backup_path") or result.get("path"))
    try:
        assert backup_path.exists()
        assert (backup_path / "notes.txt").read_text(encoding="utf-8") == "hello world"
        assert (backup_path / "nested" / "inner.txt").exists(), "nested content not backed up"
    finally:
        import shutil
        shutil.rmtree(backup_path, ignore_errors=True)
