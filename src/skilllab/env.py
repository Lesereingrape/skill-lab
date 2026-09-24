"""A deterministic 'keyworld' STRIPS domain with an exact simulator.

Rooms form a small graph; some corridors are locked doors that only a specific
key (lying in some room) opens. The robot starts in room ``0`` and must reach the
goal room. Because a locked corridor cannot be crossed before its key is picked
up, every non-trivial task forces a *dependency chain* — walk to the key, grab it,
walk to the door, unlock, walk through — which is exactly the structure where a
growing library of reusable multi-step skills pays off.

The whole point is verifiability: a plan is just a list of primitive actions, the
simulator executes it for free, and success is a ground literal ``('at', robot,
goal)``. Nothing is graded by a model's opinion, so the self-evolution curves in
``study.py`` are measured on hard pass/fail truth.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

START = 0


@dataclass(frozen=True)
class Door:
    edge: tuple  # (room_a, room_b)
    key: str


@dataclass(frozen=True)
class World:
    rooms: tuple
    goal: int
    open_edges: tuple
    doors: tuple  # tuple[Door]
    key_rooms: dict  # key_id -> room


@dataclass(frozen=True)
class State:
    literals: frozenset

    def has(self, lit) -> bool:
        return lit in self.literals

    def replace(self, add=(), delete=()) -> State:
        s = set(self.literals)
        s.difference_update(delete)
        s.update(add)
        return State(frozenset(s))


def initial_state(world: World) -> State:
    lits = {("at", "robot", world.rooms[START])}
    for k, room in world.key_rooms.items():
        lits.add(("at", k, room))
    return State(frozenset(lits))


def _room_at(state: State):
    for lit in state.literals:
        if lit[0] == "at" and lit[1] == "robot":
            return lit[2]
    return None


def _holding(state: State):
    return {lit[1] for lit in state.literals if lit[0] == "holding"}


def goal_reached(world: World, state: State) -> bool:
    return ("at", "robot", world.goal) in state.literals


def applicable_actions(world: World, state: State) -> list[tuple]:
    room = _room_at(state)
    holding = _holding(state)
    unlocked = {lit[1] for lit in state.literals if lit[0] == "unlocked"}
    actions: list[tuple] = []

    for a, b in world.open_edges:
        if room == a:
            actions.append(("move", a, b))
        elif room == b:
            actions.append(("move", b, a))

    for door in world.doors:
        a, b = door.edge
        if _edge(a, b) in unlocked:
            if room == a:
                actions.append(("move", a, b))
            elif room == b:
                actions.append(("move", b, a))
        elif room in (a, b) and door.key in holding:
            actions.append(("unlock", door.key, a, b))

    for k, kroom in world.key_rooms.items():
        if room == kroom and ("at", k, room) in state.literals:
            actions.append(("pickup", k))

    return actions


def is_applicable(world: World, state: State, action: tuple) -> bool:
    """Membership test tolerant of ``unlock`` edge orientation.

    A skill may spell the corridor either way round; both orientations denote the same
    legal action, so fold the endpoints before comparing against the applicable set.
    """
    opts = applicable_actions(world, state)
    if action in opts:
        return True
    if action[0] == "unlock":
        _, k, a, b = action
        return ("unlock", k, *_edge(a, b)) in opts
    return False


def step(state: State, action: tuple) -> State:
    kind = action[0]
    room = _room_at(state)
    if kind == "move":
        _, a, b = action
        return state.replace(add={("at", "robot", b)}, delete={("at", "robot", a)})
    if kind == "pickup":
        _, k = action
        return state.replace(add={("holding", k)}, delete={("at", k, room)})
    if kind == "unlock":
        _, k, a, b = action
        return state.replace(add={("unlocked", _edge(a, b))})
    raise ValueError(f"unknown action {action}")


def execute(world: World, plan: list[tuple]) -> bool:
    """Deterministic simulator: replay a plan, return True iff the goal is reached."""
    state = initial_state(world)
    for action in plan:
        if not is_applicable(world, state, action):
            return False
        state = step(state, action)
    return goal_reached(world, state)


def _edge(a: int, b: int) -> tuple:
    return (a, b) if a < b else (b, a)


def canon_action(action: tuple) -> tuple:
    """Normalise a door edge so an ``unlock`` is orientation-independent.

    A corridor ``(a, b)`` is stored canonically, but a learned skill may name its
    endpoints either way round. Folding ``unlock`` to a single orientation lets the
    simulator accept a plan that reaches the same legal state by either spelling.
    """
    if action[0] == "unlock":
        _, k, a, b = action
        a, b = _edge(a, b)
        return ("unlock", k, a, b)
    return action


def static_facts(world: World) -> frozenset:
    """Structure literals true in every state: which key unlocks which corridor,
    and which corridors are always open.

    Door edges are recorded in *both* directions so a skill can bind the robot's
    current room as the source and the far room as the destination without
    orientation logic. Open edges too, so a generalised "walk through an open
    corridor" pattern can be grounded by structure rather than by the door key.
    """
    facts = set()
    for d in world.doors:
        a, b = d.edge
        facts.add(("door", d.key, a, b))
        facts.add(("door", d.key, b, a))
    for a, b in world.open_edges:
        facts.add(("open", a, b))
        facts.add(("open", b, a))
    return frozenset(facts)


def _segments(n_rooms: int, open_edges: list[tuple]) -> list[list[int]]:
    """Rooms partitioned into door-free connected runs (so a locked door stays a
    bridge that must be opened — no chord can route around it)."""
    adj: dict = {r: set() for r in range(n_rooms)}
    for a, b in open_edges:
        adj[a].add(b)
        adj[b].add(a)
    seen: set = set()
    segs = []
    for r in range(n_rooms):
        if r in seen:
            continue
        stack, comp = [r], []
        seen.add(r)
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        segs.append(sorted(comp))
    return segs


def make_world(n_rooms: int, n_doors: int, rng: random.Random,
               chords: int = 0) -> World:
    """A backbone line of rooms with ``n_doors`` locked corridors to the goal.

    Each locked door's key is scattered in a door-free segment at or before the door,
    so the task is always solvable (you can walk back to fetch it). ``chords`` extra
    open corridors are then added *within* segments — a random shortcut that does not
    span any locked door — so reaching a key or a doorway admits several routes and
    the search tree branches. That extra structure is what a growing library of
    reusable route skills can prune.
    """
    rooms = tuple(range(n_rooms))
    goal = n_rooms - 1
    backbone = [_edge(i, i + 1) for i in range(n_rooms - 1)]
    locked = rng.sample(backbone, min(n_doors, len(backbone)))
    doors: list[Door] = []
    key_rooms: dict = {}
    for idx, e in enumerate(locked):
        key = f"k{idx}"
        key_rooms[key] = rng.randint(START, min(e))
        doors.append(Door(edge=e, key=key))
    door_edges = {d.edge for d in doors}
    open_edges = [e for e in backbone if e not in door_edges]

    if chords:
        existing = {frozenset(e) for e in open_edges}
        candidates = []
        for seg in _segments(n_rooms, open_edges):
            for i in range(len(seg)):
                for j in range(i + 2, len(seg)):  # non-adjacent => a real shortcut
                    candidates.append(_edge(seg[i], seg[j]))
        candidates = [c for c in candidates if frozenset(c) not in existing]
        for c in rng.sample(candidates, min(chords, len(candidates))):
            open_edges.append(c)

    return World(rooms=rooms, goal=goal, open_edges=tuple(open_edges),
                 doors=tuple(doors), key_rooms=key_rooms)


def make_task_stream(n: int, seed: int):
    rng = random.Random(seed)
    worlds = []
    for i in range(n):
        rooms = 5 + (i % 5)                 # difficulty cycles 5..9 rooms
        doors = min(1 + (i // 5), rooms - 1)  # then more locks per 5 tasks
        chords = min(2 + (i // 8), rooms - 3)  # extra shortcuts grow with length
        worlds.append(make_world(rooms, doors, rng, chords=max(0, chords)))
    return worlds
