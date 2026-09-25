"""The committed skill artifact must recompute from its own per-seed rows.

The README block is generated from ``results/skills.json``, so an inconsistent JSON is
an inconsistent README with CI green. This recomputes ``summary`` from ``per_seed`` with
the study's own ``aggregate`` and requires it to come out identical — including the
soundness counter, which is the one number a reader most needs to trust.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from skilllab.study import BUDGET, N_TASKS, aggregate

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "results" / "skills.json").read_text(encoding="utf-8"))


def _rows():
    out = []
    for seed in DATA["config"]["seeds"]:
        rows = [SimpleNamespace(**cell) for cell in DATA["per_seed"][str(seed)]]
        assert [r.index for r in rows] == list(range(N_TASKS)), (
            f"seed {seed} does not hold one row per curriculum task")
        out.append(rows)
    return out


def test_summary_recomputes_from_the_published_per_seed_rows():
    recomputed = aggregate(_rows())
    assert recomputed == DATA["summary"], (
        "the published means are not the mean of the published per-seed rows")


def test_every_reuse_plan_verified():
    """The study's soundness claim is 'skills shortcut search, they never lie'."""
    assert DATA["summary"]["reuse_invalid_plans"] == 0
    assert all(r.reuse_valid for rows in _rows() for r in rows), (
        "a reuse plan failed simulator verification; the artifact must not publish "
        "speedups that are not real")


def test_costs_are_integers_and_the_budget_is_the_published_one():
    assert DATA["config"]["budget"] == BUDGET
    for rows in _rows():
        for r in rows:
            assert isinstance(r.cold_cost, int) and isinstance(r.reuse_cost, int)
            assert r.cold_cost >= 0 and r.reuse_cost >= 0


def test_environment_is_recorded():
    env = DATA["environment"]
    assert env["python"] and env["platform"] and env["device"]
