---
description: Weekly refresh - take new customers and anti-seeds, re-pull, re-score, read what is new, export
argument-hint: "[--max-credits N] [--unattended]"
---

Use the `tal-builder` skill (`references/weekly.md`). Arguments: `$ARGUMENTS`.

1. **Check for fresh input first.** Run `python3 <skill>/scripts/tal.py inbox`.
   - If `needs_input` is true and `--unattended` was **not** given, ask the user before spending anything: "Any customers closed or strong prospects since <last_refresh>? Any companies that turned out wrong?" Add what they name to `tal/inbox/new-customers.csv` (`domain,group,note`) or `tal/inbox/new-anti-seeds.csv` (`domain,note`). If they say there is nothing new, go on.
   - If `--unattended` was given, do not ask. Note in the report that no new input was found.
2. **Budget.** Use `--max-credits` from the arguments. Without one, ask for it (interactive), or stop and say a cap is needed (unattended). Run `tal.py refresh --dry-run` first and say how many paid pages it would request.
3. Run `tal.py refresh --max-credits N`. If it reports that the envelope no longer passes, stop and show which seed falls outside or which anti-seed passes. Propose a fix, but do not apply it unattended.
4. **Read what is new.** If companies are waiting (`to read`), run `tal.py read-queue`, read each batch against `tal/target.md`, write the verdict files, then run `tal.py read-merge`, `tal.py merge` and `tal.py export` twice: once for everything, once with `--status target`. Use subagents for many batches.
5. **Report:** new seeds and anti-seeds, credits spent, companies added, companies whose status changed (from `list.json` → `previous_status`), the target count, and the CSV paths.
