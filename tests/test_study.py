from __future__ import annotations

from skilllab.study import aggregate, build_results, curriculum, run_seed


def test_curriculum_is_deterministic():
    a = curriculum(0)
    b = curriculum(0)
    assert [len(w.rooms) for w in a] == [len(w.rooms) for w in b]
    assert [len(w.doors) for w in a] == [len(w.doors) for w in b]


def test_run_seed_reuse_plans_are_all_valid():
    rows = run_seed(0)
    assert all(r.reuse_valid for r in rows), "a reuse plan must verify in the simulator"
    assert rows[-1].libsize >= 5, "the library should accumulate several skills"


def test_summary_reports_cost_reduction_and_soundness():
    per_seed = [run_seed(s) for s in (0, 1)]
    results = build_results(per_seed, runtime=0.0, seeds=(0, 1))
    s = results["summary"]
    assert s["reuse_invalid_plans"] == 0
    assert s["mean_reuse_cost"] <= s["mean_cold_cost"]
    assert s["reuse_solve_rate"] >= s["cold_solve_rate"] - 1e-9
    # difficulty buckets must be present and ordered
    doors = [row["doors"] for row in aggregate(per_seed)["difficulty"]]
    assert doors == sorted(doors)
