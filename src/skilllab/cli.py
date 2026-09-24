"""Tiny CLI: ``skilllab demo`` runs one seeded curriculum and prints the reuse gain.

The full, committed numbers come from ``experiments/run_study.py``; this is just a
quick, self-contained smoke run so you can watch the library learn live.
"""

from __future__ import annotations

import argparse

from .env import execute
from .planner import solve
from .skills import SkillLibrary, extract
from .study import BUDGET, curriculum, run_seed


def demo(seed: int) -> None:
    rows = run_seed(seed)
    cold = sum(r.cold_cost for r in rows) / len(rows)
    reuse = sum(r.reuse_cost for r in rows) / len(rows)
    csr = sum(r.cold_solved for r in rows) / len(rows)
    rsr = sum(r.reuse_solved for r in rows) / len(rows)
    print(f"seed {seed}: mean expansions {cold:.1f} -> {reuse:.1f} "
          f"({100 * (1 - reuse / cold):.0f}% less), "
          f"solve@{BUDGET} {csr:.2f} -> {rsr:.2f}, "
          f"final library {rows[-1].libsize} skills")


def transfer(seed: int) -> None:
    """Learn on the curriculum, then reuse the frozen library on fresh worlds."""
    library = SkillLibrary()
    for world in curriculum(seed):
        result = solve(world, budget=2_000_000, skills=library)
        for skill in extract(result["plan"], world):
            library.add(skill)
    rng_worlds = curriculum(seed + 999)
    saved = wins = 0
    for world in rng_worlds:
        cold = solve(world, budget=2_000_000)
        reuse = solve(world, budget=2_000_000, skills=library)
        assert not reuse["solved"] or execute(world, reuse["plan"])
        if reuse["expansions"] < cold["expansions"]:
            saved += cold["expansions"] - reuse["expansions"]
            wins += 1
    print(f"transfer to unseen worlds: cheaper on {wins}/{len(rng_worlds)} episodes, "
          f"{saved} total expansions saved with {len(library)} learned skills")


def main() -> None:
    ap = argparse.ArgumentParser(prog="skilllab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="one seeded curriculum, live reuse gain")
    d.add_argument("--seed", type=int, default=0)
    t = sub.add_parser("transfer", help="learn on train stream, reuse on unseen one")
    t.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    if args.cmd == "demo":
        demo(args.seed)
    elif args.cmd == "transfer":
        transfer(args.seed)


if __name__ == "__main__":
    main()
