"""The study: does a self-evolving skill library make planning cheaper and better?

One agent walks a growing curriculum of keyworlds. On every episode it (1) plans with
whatever skills it has learned so far, (2) verifies the plan with the exact simulator,
and (3) distils new generalised skills from the verified trajectory into the library.
The ablation is *reuse-on vs reuse-off*: the same tasks, the same planner, only whether
the accumulated library is offered to the search differs.

Two honest metrics, always reported together:

* **planning cost** — states expanded by breadth-first search at unbounded budget
  (every task is solvable, so this isolates *how expensive* search is). This is the
  quantity a skill library is supposed to shrink, and the primary result.
* **budgeted solve-rate** — fraction solved within a fixed expansion budget, where the
  cheaper search converts into tasks the searchless agent simply runs out of time on.

Soundness is a first-class measurement, not an assumption: every reuse plan is replayed
through the exact simulator and any invalid plan is counted (it must stay at zero,
because skills only ever *shortcut* search, never replace its verification).
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

from .env import World, execute, make_world
from .planner import solve
from .skills import SkillLibrary, extract

SEEDS = (0, 1, 2)
N_TASKS = 32
BUDGET = 70           # ~median unguided search cost: a fair "solve in time" bar
BIG = 2_000_000       # effectively unbounded: measures raw search cost
MAX_WINDOW = 3


@dataclass(frozen=True)
class TaskRow:
    index: int
    rooms: int
    doors: int
    cold_cost: int
    reuse_cost: int
    cold_solved: bool
    reuse_solved: bool
    reuse_valid: bool
    libsize: int


def curriculum(seed: int) -> list[World]:
    """A ramping stream: rooms, locked doors and shortcut corridors all grow with
    position, so later episodes are genuinely harder and the library has more to prove.
    """
    rng = random.Random(seed)
    worlds = []
    for i in range(N_TASKS):
        rooms = min(6 + i // 3, 11)
        doors = min(2 + i // 6, rooms - 4)
        chords = min(2 + i // 5, rooms - 4)
        worlds.append(make_world(rooms, max(1, doors), rng, chords=max(0, chords)))
    return worlds


def run_seed(seed: int) -> list[TaskRow]:
    library = SkillLibrary()
    rows: list[TaskRow] = []
    for i, world in enumerate(curriculum(seed)):
        cold = solve(world, budget=BIG)
        reuse = solve(world, budget=BIG, skills=library)
        reuse_valid = reuse["solved"] and execute(world, reuse["plan"])
        cold_b = solve(world, budget=BUDGET)
        reuse_b = solve(world, budget=BUDGET, skills=library)

        for skill in extract(reuse["plan"] or cold["plan"], world,
                             max_window=MAX_WINDOW):
            library.add(skill)

        rows.append(TaskRow(
            index=i, rooms=len(world.rooms), doors=len(world.doors),
            cold_cost=cold["expansions"], reuse_cost=reuse["expansions"],
            cold_solved=cold_b["solved"], reuse_solved=reuse_b["solved"],
            reuse_valid=reuse_valid, libsize=len(library),
        ))
    return rows


def _mean(xs):
    return statistics.fmean(xs) if xs else 0.0


def aggregate(per_seed: list[list[TaskRow]]) -> dict:
    n = N_TASKS
    cold_cost = [_mean([r.cold_cost for r in rows]) for rows in per_seed]
    reuse_cost = [_mean([r.reuse_cost for r in rows]) for rows in per_seed]
    mean_cold = _mean(cold_cost)
    mean_reuse = _mean(reuse_cost)

    def rate(field):
        vals = []
        for rows in per_seed:
            vals.extend(1.0 if getattr(r, field) else 0.0 for r in rows)
        return _mean(vals)

    # per-difficulty cost: bucket by door count
    buckets: dict = {}
    for rows in per_seed:
        for r in rows:
            buckets.setdefault(r.doors, []).append((r.cold_cost, r.reuse_cost,
                                                    r.cold_solved, r.reuse_solved))
    difficulty = []
    for d in sorted(buckets):
        pairs = buckets[d]
        difficulty.append({
            "doors": d,
            "n": len(pairs),
            "cold_cost": round(_mean([p[0] for p in pairs]), 1),
            "reuse_cost": round(_mean([p[1] for p in pairs]), 1),
            "cold_sr": round(_mean([1.0 * p[2] for p in pairs]), 3),
            "reuse_sr": round(_mean([1.0 * p[3] for p in pairs]), 3),
        })

    # learning curve: mean cumulative library size and cost by task position
    curve = []
    for i in range(n):
        curve.append({
            "index": i,
            "rooms": per_seed[0][i].rooms,
            "doors": per_seed[0][i].doors,
            "cold_cost": round(_mean([rows[i].cold_cost for rows in per_seed]), 1),
            "reuse_cost": round(_mean([rows[i].reuse_cost for rows in per_seed]), 1),
            "libsize": round(_mean([rows[i].libsize for rows in per_seed]), 1),
        })

    invalid = sum(0 if r.reuse_valid else 1 for rows in per_seed for r in rows)
    total = sum(len(rows) for rows in per_seed)

    return {
        "mean_cold_cost": round(mean_cold, 1),
        "mean_reuse_cost": round(mean_reuse, 1),
        "cost_reduction_pct": round(100.0 * (1 - mean_reuse / mean_cold), 1)
        if mean_cold else 0.0,
        "cold_solve_rate": round(rate("cold_solved"), 3),
        "reuse_solve_rate": round(rate("reuse_solved"), 3),
        "final_libsize": round(_mean([rows[-1].libsize for rows in per_seed]), 1),
        "reuse_invalid_plans": invalid,
        "episodes": total,
        "difficulty": difficulty,
        "curve": curve,
    }


def build_results(per_seed, runtime: float) -> dict:
    return {
        "config": {
            "seeds": list(SEEDS),
            "n_tasks": N_TASKS,
            "budget": BUDGET,
            "max_window": MAX_WINDOW,
        },
        "summary": aggregate(per_seed),
        "runtime_sec": round(runtime, 1),
    }
