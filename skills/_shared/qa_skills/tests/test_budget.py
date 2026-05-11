"""budget tests — estimation, splitting, batch_state, resume."""

from __future__ import annotations

from pathlib import Path

import pytest

from qa_skills.budget import (
    AVG_SECONDS_PER_FILE,
    MAX_PARALLEL_BATCHES_PER_CATEGORY,
    SAFETY_FACTOR,
    batch_id,
    chunked,
    estimate_fit,
    is_completed,
    load_batch_state,
    mark_completed,
    pending_batches,
    save_batch_state,
    split_into_batches,
    summarize_prior_batches,
)


# ---------- A5: estimate_fit / split_into_batches ----------


def test_estimate_fit_100_files_600s():
    fits, batches = estimate_fit(100, 600)
    expected_fits = int(600 * SAFETY_FACTOR / AVG_SECONDS_PER_FILE)  # 9
    assert fits == expected_fits
    assert batches == (100 + expected_fits - 1) // expected_fits


def test_estimate_fit_small_batch_fits_one():
    fits, batches = estimate_fit(5, 600)
    assert fits >= 1
    assert batches == 1


def test_estimate_fit_zero_files_zero_batches():
    fits, batches = estimate_fit(0, 600)
    assert fits == 1
    assert batches == 0


def test_estimate_fit_floor_to_one_on_tiny_timeout():
    """Even with sub-second timeout, must round up to >=1 file per batch."""
    fits, _ = estimate_fit(10, 1)
    assert fits == 1


def test_split_into_batches_round_robin():
    files = list(range(20))
    out = split_into_batches(files, 7)
    assert [len(b) for b in out] == [7, 7, 6]
    flat = [x for b in out for x in b]
    assert flat == files


def test_split_into_batches_rejects_zero_size():
    with pytest.raises(ValueError):
        split_into_batches([1, 2, 3], 0)


# ---------- A5.b: batch_state persistence ----------


def test_batch_id_zero_padded():
    assert batch_id("api", 12) == "api:012"
    assert batch_id("unit", 0) == "unit:000"


def test_load_batch_state_returns_empty_when_missing(tmp_path: Path):
    assert load_batch_state(tmp_path) == {}


def test_load_batch_state_returns_empty_when_corrupt(tmp_path: Path):
    (tmp_path / "batch_state.json").write_text("{ not json", encoding="utf-8")
    assert load_batch_state(tmp_path) == {}


def test_mark_completed_then_save_then_load_roundtrip(tmp_path: Path):
    state = {}
    mark_completed(state, batch_id("api", 0), ["tests/api/auth/test_login.py"])
    save_batch_state(tmp_path, state)
    reloaded = load_batch_state(tmp_path)
    assert reloaded == state
    assert is_completed(reloaded, "api:000") is True
    assert is_completed(reloaded, "api:001") is False


def test_pending_batches_resumes_from_first_incomplete(tmp_path: Path):
    state = {}
    # Pretend batches 0..4 done; 5..11 still pending.
    for i in range(5):
        mark_completed(state, batch_id("unit", i), [f"tests/unit/m{i}/test_m{i}.py"])
    save_batch_state(tmp_path, state)

    loaded = load_batch_state(tmp_path)
    batches = [[f"path_{i}"] for i in range(12)]
    todo = pending_batches(loaded, "unit", batches)
    assert [i for i, _ in todo] == [5, 6, 7, 8, 9, 10, 11]


def test_summarize_prior_batches_filters_by_category(tmp_path: Path):
    state = {}
    mark_completed(state, batch_id("api", 0), ["tests/api/auth/test_login.py"])
    mark_completed(state, batch_id("unit", 0), ["tests/unit/svc/test_svc.py"])
    mark_completed(state, batch_id("unit", 1), ["tests/unit/db/test_db.py"])
    out = summarize_prior_batches(state, "unit")
    ids = [e["batch_id"] for e in out]
    assert ids == ["unit:000", "unit:001"]
    assert all("paths" in e for e in out)


def test_summarize_prior_batches_empty_on_no_match(tmp_path: Path):
    assert summarize_prior_batches({}, "api") == []


def test_chunked_emits_expected_window_size():
    assert list(chunked(range(10), MAX_PARALLEL_BATCHES_PER_CATEGORY)) == [
        [0, 1, 2], [3, 4, 5], [6, 7, 8], [9]
    ]


def test_chunked_rejects_zero_size():
    with pytest.raises(ValueError):
        list(chunked([1, 2, 3], 0))
