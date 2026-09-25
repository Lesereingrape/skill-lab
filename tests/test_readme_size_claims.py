"""The prose outside the generated block still has to describe the current artifact.

`test_readme_matches_results.py` pins the block between the RESULTS markers
byte for byte, so the unguarded remainder is the paragraph *after* it: the note
that explains why the curve was republished quotes the old figures against the
new ones ("11.8% (now 13.3%)"), and the Quickstart promises a 3-seed study. If a
future republication moves those numbers again, the sentence silently becomes
false - and a stale "now" is worse than a stale mean, because it claims to have
been checked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "results" / "skills.json").read_text(encoding="utf-8"))
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
SUMMARY = DATA["summary"]


def _prose() -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    return readme.split(START, 1)[0] + readme.split(END, 1)[1]


def _current(pattern: str) -> str:
    m = re.search(pattern, _prose(), re.DOTALL)
    assert m, f"the README no longer says {pattern!r}; update this guard with it"
    return m.group(1)


def test_the_republication_note_quotes_the_published_figures():
    assert _current(r"cost cut of \*\*[\d.]+%\*\*\s*\(now ([\d.]+)%\)") == str(
        SUMMARY["cost_reduction_pct"])
    solve = r"solve-rate of \*\*[\d.]+\*\*\s*\(now ([\d.]+)"
    assert _current(solve) == f"{SUMMARY['reuse_solve_rate']:.3f}"
    lib = r"library of\s*\*\*[\d.]+\*\*\s*skills \(now ([\d.]+)\)"
    assert _current(lib) == str(SUMMARY["final_libsize"])


def test_the_republication_note_keeps_the_old_figures_historical():
    """The superseded numbers are history, not a bug: they must differ from now."""
    old = _current(r"cost cut of \*\*([\d.]+)%\*\*")
    assert float(old) != SUMMARY["cost_reduction_pct"], (
        "the note claims the republish moved the headline but quotes the current value")


def test_the_quickstart_seed_count_matches_the_study():
    m = re.search(r"full (\d+)-seed study", _prose())
    assert m, "the Quickstart no longer states the seed count"
    assert int(m.group(1)) == len(DATA["config"]["seeds"]), m.group(0)
