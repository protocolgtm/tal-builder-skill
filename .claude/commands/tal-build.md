---
description: Build the target account list from seeds and anti-seeds - analyse, test the envelope, pull, score, read, export
argument-hint: "[--max-credits N]"
---

Use the `tal-builder` skill and follow its method, steps 1 to 10, with `python3 <skill>/scripts/tal.py`. Read `references/lessons.md` and `references/prospeo-filters.md` before designing filters.

Spending: the user's approved budget for this build is `$ARGUMENTS` if it gives `--max-credits`; otherwise ask for one before the first paid call. Before every paid step, say what it is for and the most it can cost, and keep a running total. Prefer `--dry-run` first when unsure. Never raise `credit_cap`.

Checkpoints where you stop and show the user before going on:

1. If `tal/target.md`, the seeds or the anti-seeds are missing, run `/tal-init` first.
2. After `tal.py lookup`: which seeds and anti-seeds resolved, and which did not.
3. After reading the records (`tal.py controls`): your analysis in `tal/analysis.md`, summarised in a few lines: the proposed envelope, seed groups, signals and exclusions, and what you are unsure of.
4. After `tal.py test envelope`: seeds kept, anti-seeds kept, and for each dropped seed whether the filter or the seed is wrong. Revise and re-test until it passes; then `tal.py size envelope` for the market size.
5. Before pulling: the lookalike counts per group and the cost to pull each, and any extra slices you propose (with their size). Get a yes on the total.
6. After `tal.py score`: the tier counts, how seeds and anti-seeds score, and ten sample rows from tier A.
7. The read: every company in the target tiers, in batches (`tal.py read-queue`, then a verdict file per batch, then `tal.py read-merge`). For more than about 200 companies, give each batch to a subagent with `target.md`, the batch file and the verdict rules from the skill, and check its file merges cleanly.
8. Finish with `tal.py merge`, `tal.py export`, `tal.py export --status target`, and report: market size, companies pulled, target count, credits spent, and where the CSVs are.
