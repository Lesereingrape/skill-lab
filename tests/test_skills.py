from __future__ import annotations

import random

from skilllab.env import execute, initial_state, make_world, static_facts
from skilllab.planner import solve
from skilllab.skills import SkillLibrary, applicable, extract, grounded_macros


def test_extracted_skills_are_grounded_only_when_valid():
    world = make_world(8, 3, random.Random(0))
    plan = solve(world, budget=200_000)["plan"]
    skills = extract(plan, world)
    assert skills, "a solved multi-door plan should yield at least one skill"
    facts = static_facts(world)
    # Every grounded macro is a multi-step shortcut of primitive actions.
    state = initial_state(world)
    for macro in grounded_macros(skills, state.literals, facts):
        assert len(macro) >= 2
        assert all(a[0] in {"move", "pickup", "unlock"} for a in macro)


def test_skill_library_dedups_by_signature():
    world = make_world(8, 3, random.Random(0))
    plan = solve(world, budget=200_000)["plan"]
    a = SkillLibrary()
    b = SkillLibrary()
    for s in extract(plan, world):
        a.add(s)
        a.add(s)  # same skill twice
    for s in extract(plan, world):
        b.add(s)
    assert len(a) == len(b)


def test_learned_skills_transfer_and_shorten_search_on_a_new_world():
    train = make_world(8, 3, random.Random(0))
    lib = SkillLibrary()
    for s in extract(solve(train, budget=200_000)["plan"], train):
        lib.add(s)
    assert len(lib) >= 2

    test_world = make_world(9, 4, random.Random(11))
    cold = solve(test_world, budget=200_000)
    reuse = solve(test_world, budget=200_000, skills=lib)
    assert reuse["solved"] and execute(test_world, reuse["plan"])
    assert reuse["expansions"] <= cold["expansions"]


def test_applicable_grounds_door_pass_only_when_holding_the_key():
    world = make_world(6, 2, random.Random(4))
    plan = solve(world, budget=200_000)["plan"]
    door_pass = next(
        (s for s in extract(plan, world)
         if s.body[0][0] == "unlock" and s.body[-1][0] == "move"),
        None,
    )
    assert door_pass is not None
    # At the initial state the robot holds nothing, so the door-pass cannot ground.
    state = initial_state(world)
    assert applicable(door_pass, state.literals, static_facts(world)) is None
