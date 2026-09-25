from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skilllab.study import SEEDS, build_results, run_seed


def main(out: str | Path | None = None) -> None:
    started = time.time()
    per_seed = [run_seed(seed) for seed in SEEDS]
    results = build_results(per_seed, runtime=time.time() - started)
    # Default to the committed artifact; a scratch --out is how the rerun claim in
    # the README gets checked without overwriting the file it describes.
    dest = (Path(out) if out is not None
            else Path(__file__).resolve().parents[1] / "results" / "skills.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(results, indent=2), encoding="utf-8", newline="\n")
    s = results["summary"]
    print(f"wrote {dest}")
    print(f"cost {s['mean_cold_cost']} -> {s['mean_reuse_cost']} "
          f"({s['cost_reduction_pct']}% less), "
          f"solve {s['cold_solve_rate']} -> {s['reuse_solve_rate']}, "
          f"invalid reuse plans {s['reuse_invalid_plans']}, "
          f"final libsize {s['final_libsize']}, runtime={results['runtime_sec']}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="run_study")
    parser.add_argument("--out", default=None,
                        help="where to write the artifact; point it at a scratch path "
                             "to rerun and diff against the committed one")
    main(out=parser.parse_args().out)
