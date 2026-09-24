from __future__ import annotations

import random

from skilllab.env import (
    applicable_actions,
    execute,
    goal_reached,
    initial_state,
    make_task_stream,
    make_world,
    static_facts,
    step,
)


def test_make_world_is_solvable_and_verifyable():
    rng = random.Random(1)
    for _ in range(10):
        world = make_world(7, 3, rng, chords=2)
        assert world.goal == len(world.rooms) - 1
        # every key sits in a room that exists and at/before its door
        for door in world.doors:
            room = world.key_rooms[door.key]
            assert 0 <= room <= min(door.edge)


def test_task_stream_worlds_are_all_solvable_by_bfs():
    from skilllab.planner import solve

    for world in make_task_stream(8, seed=5):
        result = solve(world, budget=2_000_000)
        assert result["solved"]
        assert execute(world, result["plan"])


def test_execute_rejects_invalid_plan():
    rng = random.Random(2)
    world = make_world(6, 2, rng)
    # try to teleport straight into the goal without crossing the doors
    bogus = [("move", 0, world.goal)]
    assert not execute(world, bogus)


def test_step_and_goal_literals_consistent():
    world = make_world(5, 1, random.Random(3))
    state = initial_state(world)
    assert not goal_reached(world, state)
    actions = applicable_actions(world, state)
    assert all(a[0] in {"move", "pickup", "unlock"} for a in actions)
    if actions:
        assert goal_reached(world, state) == goal_reached(world, step(state, actions[0]))


def test_static_facts_are_bidirectional():
    world = make_world(6, 2, random.Random(4))
    facts = static_facts(world)
    for door in world.doors:
        a, b = door.edge
        lo, hi = (a, b) if a <= b else (b, a)
        assert ("door", door.key, lo, hi) in facts
        assert ("door", door.key, hi, lo) in facts
