from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skilllab.study import SEEDS, build_results, run_seed


def main() -> None:
    started = time.time()
    per_seed = [run_seed(seed) for seed in SEEDS]
    results = build_results(per_seed, runtime=time.time() - started)
    out = Path(__file__).resolve().parents[1] / "results" / "skills.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8", newline="\n")
    s = results["summary"]
    print(f"wrote {out}")
    print(f"cost {s['mean_cold_cost']} -> {s['mean_reuse_cost']} "
          f"({s['cost_reduction_pct']}% less), "
          f"solve {s['cold_solve_rate']} -> {s['reuse_solve_rate']}, "
          f"invalid reuse plans {s['reuse_invalid_plans']}, "
          f"final libsize {s['final_libsize']}, runtime={results['runtime_sec']}s")


if __name__ == "__main__":
    main()
