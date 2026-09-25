"""Regression: the published curve must not depend on PYTHONHASHSEED.

``Skill.preconditions`` used to be a ``frozenset``. Iterating it yields hash order, so
``applicable()`` returned whichever of several equally valid groundings happened to come
first, and ``signature()`` renamed its variables positionally over that same order. The
library therefore grew differently, and the number of BFS expansions differed, between
two runs of the *same seed* in two different processes: the committed curve was only
reproducible by accident of the interpreter's hash seed.

Precondition templates are now canonically ordered and literal candidates are sorted
once per state. This test runs a slice of the study in two subprocesses with different
hash seeds and requires byte-identical output, which is the smallest check that actually
reproduces the failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: A short slice: enough episodes for the library to grow and start to matter.
_SLICE = """
import json
from skilllab.planner import solve
from skilllab.skills import SkillLibrary, extract
from skilllab.study import BIG, MAX_WINDOW, curriculum

rows = []
for seed in (0, 1):
    library = SkillLibrary()
    for world in curriculum(seed)[:10]:
        cold = solve(world, budget=BIG)
        reuse = solve(world, budget=BIG, skills=library)
        for skill in extract(reuse["plan"] or cold["plan"], world,
                             max_window=MAX_WINDOW):
            library.add(skill)
        rows.append([cold["expansions"], reuse["expansions"], len(library),
                     [s.signature()[1] for s in library.skills][-3:]])
print(json.dumps(rows, default=str))
"""


def _run(hash_seed: str) -> list:
    env = dict(os.environ, PYTHONHASHSEED=hash_seed,
               PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-c", _SLICE], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=600, check=True)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_curve_is_hash_seed_independent():
    a = _run("0")
    b = _run("123456789")
    assert a == b, (
        "the same seeds produced different expansion counts in processes with "
        "different hash seeds — set iteration order is leaking into the study again")
