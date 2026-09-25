"""Reusable, *generalised* skills distilled from solved episodes.

A skill is a small first-order pattern: a set of precondition literal templates and
a body of action templates. Variables are tokens beginning with ``?`` (e.g. ``?a``);
matching grounds them against the concrete literals true in a state, plus the world's
static structure facts (which key opens which corridor, which corridors are open),
and the grounded body is offered to the planner as one multi-step shortcut.

The library grows by accumulating *distinct* templates. Extraction slides a short
window over a verified plan, keeps the windows that are executable and productive,
reads off the preconditions each window actually needs, and abstracts the concrete
rooms/keys to variables. A signature computed from the resulting template shape dedups
instances that are really the same procedure (the same "walk two corridors" pattern
learned in different rooms collapses to one skill). This is the loop Voyager runs —
solve an episode, propose new macros from its trajectory, keep what generalises.

Soundness does not rely on any skill being correct. The planner only *attempts* a
grounded body through :func:`skilllab.planner._apply`, which aborts the moment an
action is inapplicable, and every returned plan is re-verified by
:func:`skilllab.env.execute`. A stale or over-permissive template simply fails to
fire — it can never make the agent produce a wrong plan. That is what lets the
library grow purely from experience with no hand-written skill list.
"""

from __future__ import annotations

from dataclasses import dataclass

from .env import World, initial_state, static_facts, step


def is_var(token) -> bool:
    return isinstance(token, str) and token.startswith("?")


def _abstractable(token) -> bool:
    """Room integers and key names (``k0``, ``k1``, ...) become variables."""
    if isinstance(token, int):
        return True
    return (isinstance(token, str) and len(token) > 1 and token[0] == "k"
            and token[1:].isdigit())


@dataclass(frozen=True)
class Skill:
    name: str
    # Literal templates in a canonical order. They *look* like a set, and were one,
    # but a frozenset iterates in hash order: the first binding :func:`applicable`
    # returns and the positional variable renaming in :meth:`signature` then depend
    # on PYTHONHASHSEED, which makes the learned library — and every published
    # expansion count — differ between two runs of the same seed.
    preconditions: tuple
    body: tuple  # action templates; every var must appear in a precondition

    def signature(self) -> tuple:
        """Structural identity: action shape + precondition predicate names, with
        variables renamed positionally. Two concrete windows that differ only by room
        number share a signature and therefore one slot in the library.
        """
        ids: dict = {}

        def canon(tok):
            if not is_var(tok):
                return tok
            if tok not in ids:
                ids[tok] = len(ids)
            return f"#{ids[tok]}"

        body_shape = tuple(tuple(canon(t) for t in a) for a in self.body)
        pre_shape = tuple(tuple(canon(t) for t in p) for p in self.preconditions)
        return (body_shape, pre_shape)


def _match(lit_template, lit, binding):
    if len(lit_template) != len(lit):
        return None
    out = dict(binding)
    for t, g in zip(lit_template, lit, strict=False):
        if is_var(t):
            prev = out.get(t)
            if prev is not None and prev != g:
                return None
            out[t] = g
        elif t != g:
            return None
    return out


def _ground(template, binding):
    return tuple(binding.get(tok, tok) if is_var(tok) else tok for tok in template)


def applicable(skill: Skill, state_literals: frozenset, facts: frozenset = frozenset()):
    """Ground ``skill`` body against a state; return the first valid action tuple.

    ``facts`` are the world's static structure literals (which key opens which
    corridor, which corridors are open), matched alongside the state's fluents so a
    skill can bind the far side of a door before the robot has crossed it.
    """
    return _first_grounding(skill, sorted(state_literals | facts, key=repr))


def _first_grounding(skill: Skill, avail: list):
    """``avail`` must arrive in canonical order, and which of several equally valid
    groundings wins decides which plan the library later proposes — so the caller
    sorts once per state instead of once per skill.
    """
    bindings = [{}]
    for template in skill.preconditions:
        nxt = []
        for b in bindings:
            for lit in avail:
                m = _match(template, lit, b)
                if m is not None:
                    nxt.append(m)
        bindings = nxt
        if not bindings:
            return None
    for b in bindings:
        if all(v in b for tpl in skill.body for v in tpl if is_var(v)):
            return tuple(_ground(a, b) for a in skill.body)
    return None


def grounded_macros(skills, state_literals, facts: frozenset = frozenset()):
    """All multi-step shortcuts usable right now, as grounded primitive-action tuples."""
    avail = sorted(state_literals | facts, key=repr)
    seen = set()
    out = []
    for s in skills:
        body = _first_grounding(s, avail)
        if body and body not in seen:
            seen.add(body)
            out.append(body)
    return out


class SkillLibrary:
    """A deduplicated, insertion-ordered set of learned skills."""

    def __init__(self):
        self._skills: list[Skill] = []
        self._sigs: set = set()

    def add(self, skill: Skill) -> bool:
        if skill is None:
            return False
        sig = skill.signature()
        if sig in self._sigs:
            return False
        self._sigs.add(sig)
        self._skills.append(skill)
        return True

    @property
    def skills(self):
        return list(self._skills)

    def __iter__(self):
        return iter(self._skills)

    def __len__(self):
        return len(self._skills)

    def macros(self, state_literals, facts: frozenset = frozenset()):
        return grounded_macros(self._skills, state_literals, facts)


# --- extraction ---------------------------------------------------------------

def _robot_room(literals):
    for lit in literals:
        if lit[0] == "at" and lit[1] == "robot":
            return lit[2]
    return None


def _edge(a, b):
    return (a, b) if a <= b else (b, a)


def _derive_preconditions(window, state_before, facts):
    """Read off the concrete preconditions this window genuinely needs, or None.

    Only the window's *start* state is a precondition; positions the moves reach are
    produced inside the window and so are linked by shared variables rather than
    asserted separately. Walks the window from ``state_before`` recording, per action,
    the ground literals that enable it — the robot's starting room, an open corridor
    for a move, a key's location for a pickup, and a door+key fact for an unlock.
    Returns ``None`` (discarding the window) when a step leans on something a short,
    general macro cannot re-establish — most tellingly crossing a corridor that was
    unlocked *earlier* in the plan, which would otherwise bake a stale precondition in.
    """
    pres: set = set()
    s = state_before
    start_room = _robot_room(s.literals)
    pres.add(("at", "robot", start_room))
    cur = start_room
    unlocked_here: set = set()
    for a in window:
        kind = a[0]
        if kind == "move":
            _, x, y = a
            if x != cur:
                return None  # not walkable from where the robot actually is
            if ("open", x, y) in facts:
                pass
            elif _edge(x, y) in unlocked_here:
                pass  # opened by an earlier unlock *in this window* (a door pass)
            else:
                return None  # a locked corridor, or one opened before the window
            cur = y
        elif kind == "pickup":
            _, k = a
            loc = next((lit for lit in s.literals
                        if lit[0] == "at" and lit[1] == k), None)
            if loc is None or loc[2] != cur:
                return None  # key not here
            pres.add(loc)
        elif kind == "unlock":
            _, k, x, y = a
            if ("holding", k) not in s.literals:
                return None
            door_fact = ("door", k, *_edge(x, y))
            if door_fact not in facts:
                return None
            pres.add(("holding", k))
            pres.add(door_fact)
            unlocked_here.add(_edge(x, y))
        else:
            return None
        s = step(s, a)
    return frozenset(pres)


def _to_templates(pres, window):
    """Abstract concrete rooms/keys to shared variables across preconditions + body."""
    mapping: dict = {}

    def var(tok):
        if not _abstractable(tok):
            return tok
        if tok not in mapping:
            mapping[tok] = "?" + str(tok)
        return mapping[tok]

    def map_lit(lit):
        return (lit[0], *(var(t) for t in lit[1:]))

    # sorted, not a frozenset: see the Skill.preconditions comment
    return (tuple(sorted((map_lit(p) for p in pres), key=repr)),
            tuple(map_lit(a) for a in window))


def _window_productive(window, state_before):
    """A macro must be at least 2 actions and change the state (reach, hold, unlock)."""
    if len(window) < 2:
        return False
    s = state_before
    gained = set()
    for a in window:
        s2 = step(s, a)
        gained.update(s2.literals - s.literals)
        s = s2
    return bool(gained)


def extract(plan, world: World, max_window: int = 3):
    """Slide a short window over a verified plan, generalising each valid one to a skill.

    Windows of length 2..``max_window`` are considered. A window is kept only if it is
    executable from the state at its start, is productive, and every variable in its
    body is pinned by a precondition (so it grounds deterministically when replayed in
    a new world). Rooms and keys are then abstracted to variables.
    """
    facts = static_facts(world)
    states = [initial_state(world)]
    for a in plan:
        states.append(step(states[-1], a))

    out: list[Skill] = []
    n = len(plan)
    for i in range(n):
        s0 = states[i]
        for w in range(2, min(max_window, n - i) + 1):
            window = tuple(plan[i:i + w])
            if not _window_productive(window, s0):
                continue
            pres = _derive_preconditions(window, s0, facts)
            if pres is None:
                continue
            abs_pre, abs_body = _to_templates(pres, window)
            body_vars = {t for a in abs_body for t in a if is_var(t)}
            pre_vars = {t for p in abs_pre for t in p if is_var(t)}
            if not body_vars <= pre_vars:
                continue
            out.append(Skill(name=f"learned_{abs_body[0][0]}_{len(abs_body)}",
                             preconditions=abs_pre, body=abs_body))
    return out
