"""Bounded breadth-first planner over the keyworld, with an honest cost metric.

Planning is search over :class:`~skilllab.env.State`. ``solve`` returns whether the
goal is reachable, the winning plan, and how many states were *expanded* before
finding it — that expansion count is the agent's planning cost and the quantity a
skill library is supposed to shrink. ``budget`` caps expansions so a task can be
"not solved in time" rather than always solved given unbounded search; that is what
makes reuse measurably useful instead of merely faster.

A learned skill is offered at each state as a single multi-step action whose
preconditions are already satisfied, so it shortcuts the search tree. Plans are
always expanded back into primitive actions, so every returned plan is executable
and verified regardless of whether a skill was used.
"""

from __future__ import annotations

from collections import deque

from .env import (
    State,
    World,
    applicable_actions,
    goal_reached,
    initial_state,
    is_applicable,
    static_facts,
    step,
)
from .skills import grounded_macros


def _apply(world: World, state: State, actions):
    for a in actions:
        if not is_applicable(world, state, a):
            return None
        state = step(state, a)
    return state


def solve(world: World, *, budget: int = 30000, skills=None) -> dict:
    """Breadth-first search to the goal, optionally guided by a skill library.

    ``skills`` may be a :class:`~skilllab.skills.SkillLibrary` or any iterable of
    :class:`~skilllab.skills.Skill`. Grounded skill bodies are tried before primitive
    actions so the goal is discovered at a shallower frontier depth, which is exactly
    the expansion saving the library is meant to deliver.
    """
    start = initial_state(world)
    if goal_reached(world, start):
        return {"solved": True, "plan": [], "expansions": 0}

    facts = static_facts(world)
    library = list(skills) if skills else None
    q = deque([(start, [])])
    seen = {start}
    expansions = 0
    while q:
        if expansions >= budget:
            return {"solved": False, "plan": None, "expansions": expansions}
        state, path = q.popleft()
        expansions += 1

        seqs = grounded_macros(library, state.literals, facts) if library else []
        seqs += [(a,) for a in applicable_actions(world, state)]
        for seq in seqs:
            ns = _apply(world, state, list(seq))
            if ns is None or ns in seen:
                continue
            npath = path + list(seq)
            if goal_reached(world, ns):
                return {"solved": True, "plan": npath, "expansions": expansions}
            seen.add(ns)
            q.append((ns, npath))
    return {"solved": False, "plan": None, "expansions": expansions}
