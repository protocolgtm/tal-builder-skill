---
description: Add or remove anti-seeds (companies that look similar and are wrong)
argument-hint: "add <domain...> | remove <domain...> | list"
---

Use the `tal-builder` skill. Arguments: `$ARGUMENTS`.

- **add <domains>:** ask why each is wrong if the user has not said (lost, churned, competitor, wrong buyer, too big). The reason is what makes an anti-seed useful. Run `python3 <skill>/scripts/tal.py antiseed add <domains> --note "<why>" --max-credits 3`. That costs at most 3 credits for the lookup and the envelope re-test; say so first. If the envelope now keeps an anti-seed, read that company's record (`tal.py controls`) next to the seeds. Propose either an envelope change, tested before you use it, or an `exclude` rule in `rubric.json` that catches it without catching any seed. Check this with `tal.py signals`. Then run `tal.py score` and `tal.py merge` and report what changed.
- **remove <domains>:** `tal.py antiseed remove <domains> --note "<reason>"`.
- **list** or no arguments: `tal.py antiseed list`.
