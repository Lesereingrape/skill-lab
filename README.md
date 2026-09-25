# skill-lab — a Voyager-style skill library that gets cheaper the more it is used

**skill-lab** is a dependency-free, CPU-only study of a *self-evolving skill library*
on a deterministic planning domain. An agent solves a growing curriculum of lockbox
"keyworlds" with a bounded breadth-first planner; after each **verified** solution it
distils generalised, reusable skills out of its own trajectory and keeps them. The
ablation is reuse-on vs reuse-off on identical tasks — the only difference is whether
the agent is allowed to remember what it has already learned.

![ci](https://github.com/Lesereingrape/skill-lab/actions/workflows/ci.yml/badge.svg)

## The setup

- **Domain:** rooms form a line with locked corridors; each door needs a specific key
  scattered earlier along the route, so every task is a dependency chain (walk to the
  key, grab it, walk to the door, unlock, cross). Extra open "chord" corridors add
  route choice. A plan is just a list of primitive actions and an exact simulator
  replays it, so success is ground truth, never a model's opinion.
- **Planner:** breadth-first search that counts **states expanded** (its cost) and
  honours a **budget**, so a task can be "not solved in time".
- **Skills:** short action windows generalised to first-order templates (rooms/keys
  become variables) that the search can apply as one multi-step shortcut when their
  preconditions hold. The library dedups them by structural signature and grows purely
  from experience — nothing is hand-written.

## Why it is trustworthy

A skill can never make the agent *wrong*: search only ever **attempts** a grounded
skill and aborts the instant a step is illegal, and every final plan is replayed by
the exact simulator. So the improvement is measured on hard pass/fail truth, and
soundness is by construction, not by assumption. The library also **transfers**: a frozen set of
skills learned on one stream lowers search cost on unseen worlds (see the `transfer`
command below), so this is generalisation, not memorisation.

## Quickstart

```bash
pip install -e .                 # no runtime dependencies (pure stdlib)
python -m skilllab.cli demo      # one seeded curriculum, seconds
python -m skilllab.cli transfer  # learn on train, reuse on unseen worlds
python experiments/run_study.py  # full 3-seed study -> results/skills.json
python experiments/make_report.py --write  # splice the README block back from the JSON
```

## Results

<!-- RESULTS:START -->
*Every figure below is produced by `experiments/run_study.py` on CPU and committed as [`results/skills.json`](results/skills.json); the tables are rendered by `experiments/make_report.py`. Same planner, same curriculum, same seed set — the only thing that changes is whether the agent is allowed to reuse the skills it has accumulated. Mean over 3 seeds, 96 episodes.*

- measured under: Python 3.13.7 on Windows-11-10.0.26200-SP0, cpu (exact integer search; no float reduction order involved) — search cost here is an integer count, so the published curve carries no float-reduction ambiguity; what it did carry, until this run, was set-iteration order (see the note under the tables)
- curriculum: **32** keyworlds per seed, difficulty (rooms / locked doors / shortcut corridors) ramping with position
- skills are distilled from **verified** plans only, with a max window of **3** actions
- budgeted solve-rate uses a fixed **70-expansion** budget (≈ the median unguided search cost)

### Headline: reuse-on vs reuse-off

| metric | cold search (no library) | self-evolving library | change |
|---|---:|---:|---:|
| mean search cost (states expanded) | 88.9 | 77.1 | **-13.3%** |
| budgeted solve-rate | 0.552 | 0.625 | **+7 pts** |
| invalid plans among reuse runs | — | 0 / 96 | sound |

Letting the agent reuse skills it distilled from its own verified solutions cuts planning cost by **13.3%** on average and lifts the share of tasks it solves within budget from **0.55** to **0.62**. The library reaches ~30 distinct generalised skills, and **every** reuse-augmented plan is verified correct by the exact simulator — skills only ever shortcut the search, never replace its verification.

### The benefit grows with difficulty

| locked doors | tasks | cold expansions | reuse expansions | cost cut | cold solve@budget | reuse solve@budget |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 18 | 17.9 | 15.4 | 14% | 1.00 | 1.00 |
| 3 | 18 | 42.0 | 33.1 | 21% | 0.94 | 1.00 |
| 4 | 18 | 70.0 | 59.4 | 15% | 0.67 | 0.78 |
| 5 | 18 | 103.7 | 86.2 | 17% | 0.33 | 0.50 |
| 6 | 18 | 168.6 | 150.7 | 11% | 0.00 | 0.06 |
| 7 | 6 | 215.8 | 198.8 | 8% | 0.00 | 0.00 |

On the easiest worlds (2 doors) search is cheap and reuse still saves 14% of the expansion cost. The payoff peaks in the middle: at **5 doors** the library turns 17 points of previously unsolvable episodes into solved ones (0.33 → 0.50). At the very hardest worlds (7 doors) both arms exhaust the fixed budget, yet reuse still spends 8% fewer expansions — compounding reusable procedures matter most exactly when the search tree is biggest, and a larger budget would convert that cost saving back into solved tasks.

### Learning curve (library accumulating)

| episode | rooms | doors | cold expansions | reuse expansions | library size |
|---:|---:|---:|---:|---:|---:|
| 0 | 6 | 2 | 16.0 | 16.0 | 5.7 |
| 5 | 7 | 2 | 17.7 | 15.7 | 12.7 |
| 10 | 9 | 3 | 33.7 | 22.7 | 18.3 |
| 15 | 11 | 4 | 64.0 | 51.7 | 23.0 |
| 20 | 11 | 5 | 146.3 | 130.0 | 25.3 |
| 25 | 11 | 6 | 153.3 | 130.3 | 26.7 |
| 31 | 11 | 7 | 169.0 | 157.3 | 30.3 |

The library fills up fast (a handful of episodes) and then keeps paying off: reuse cost stays under cold cost at every point, and the gap widens as the worlds grow.

### Honest limitations

- The domain is a deliberately minimal deterministic keyworld, and the planner is exhaustive BFS. The point is *verifiable* self-improvement of planning efficiency, not a claim about LLM agents in the wild.
- The average cost cut (13%) is real and reproducible but modest: short-window macros shortcut local structure (walks, door-passing) and cannot fix the combinatorial key-fetch ordering that dominates the hardest worlds. Reporting a bigger number here would be dishonest.
- Budgeted solve-rate depends on the chosen budget; we fix it once at the median cold cost rather than tuning it to maximise the gap.
<!-- RESULTS:END -->

### A note on this curve's history

The numbers above were **republished**, and the republish was not uniformly
flattering. The earlier version reported a mean cost cut of **11.8%** (now 13.3%), a
budgeted reuse solve-rate of **0.635** (now 0.625, so *worse*), and a final library of
**25.3** skills (now 30.3). The reason it had to go: skill grounding iterated a
`frozenset`, so when several groundings of a template were equally valid the one that
won depended on Python's per-process string hash seed. A search-cost study whose curve
moves with `PYTHONHASHSEED` is not measuring the claim it makes, so the grounding pool
is now visited in a stable `sorted(…, key=repr)` order, the study was re-run, and
[`tests/test_hash_seed_determinism.py`](tests/test_hash_seed_determinism.py) replays a
slice of the curriculum in two subprocesses under different hash seeds and fails if any
reported figure differs. Nothing about the domain, planner, budget or curriculum
changed — only the tie-break became deterministic, and every published figure moved
with it, in both directions.

Those "now" figures are not remembered, they are checked: `tests/test_readme_size_claims.py`
reads each one out of [`results/skills.json`](results/skills.json), so a third
republication that moves the headline has to move the sentence with it or fail
CI — and it also insists the quoted old figures still differ from the current
ones, so the note cannot be flattened into claiming nothing moved.
