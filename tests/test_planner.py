from __future__ import annotations

import random

from skilllab.env import execute, make_world
from skilllab.planner import solve


def test_solve_plan_executes_and_reaches_goal():
    world = make_world(7, 3, random.Random(0), chords=2)
    result = solve(world, budget=200_000)
    assert result["solved"]
    assert execute(world, result["plan"])


def test_tiny_budget_can_fail_to_solve():
    world = make_world(9, 4, random.Random(0), chords=3)
    full = solve(world, budget=200_000)
    starved = solve(world, budget=3)
    assert full["solved"]
    assert not starved["solved"]
    assert starved["expansions"] <= 3


def test_expansions_counted_monotonically():
    rng = random.Random(0)
    easy = make_world(5, 1, rng)
    hard = make_world(9, 3, rng)
    assert solve(easy, budget=200_000)["expansions"] < \
        solve(hard, budget=200_000)["expansions"]
