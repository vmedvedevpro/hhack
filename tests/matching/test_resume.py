from __future__ import annotations

from pathlib import Path

import pytest

from hhack.config import Settings
from hhack.matching.resume import load_resumes, resumes_cache_dir


def _settings(cache_dir: str | None) -> Settings:
    # Construct Settings without reading .env so the test is hermetic.
    return Settings.model_construct(resumes_cache_dir=cache_dir)


def test_load_resumes_reads_every_md_sorted(tmp_path: Path):
    (tmp_path / "abc123.md").write_text("# resume abc\nbody", encoding="utf-8")
    (tmp_path / "xyz789.md").write_text("# resume xyz\nbody", encoding="utf-8")
    # Non-md files are ignored.
    (tmp_path / "ignore.txt").write_text("nope", encoding="utf-8")

    resumes = load_resumes(_settings(str(tmp_path)))

    assert [r.id for r in resumes] == ["abc123", "xyz789"]
    assert resumes[0].content.startswith("# resume abc")
    assert resumes[1].path == tmp_path / "xyz789.md"


def test_load_resumes_fails_when_dir_missing(tmp_path: Path):
    with pytest.raises(RuntimeError, match="does not exist"):
        load_resumes(_settings(str(tmp_path / "nope")))


def test_load_resumes_fails_when_dir_empty(tmp_path: Path):
    with pytest.raises(RuntimeError, match="No resumes found"):
        load_resumes(_settings(str(tmp_path)))


def test_load_resumes_fails_on_empty_file(tmp_path: Path):
    (tmp_path / "empty.md").write_text("   \n  \n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="empty"):
        load_resumes(_settings(str(tmp_path)))


def test_resumes_cache_dir_falls_back_to_default(tmp_path: Path):
    settings = _settings(None)
    assert resumes_cache_dir(settings) == Path("resumes/cache")
