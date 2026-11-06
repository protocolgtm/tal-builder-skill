---
description: Export the target account list to CSV
argument-hint: "[--status target ...] [--out path.csv]"
---

Use the `tal-builder` skill. Run `python3 <skill>/scripts/tal.py merge`, then `tal.py export $ARGUMENTS`. With no arguments, also run `tal.py export --status target`. Both are free. Report the row counts by status and the file paths.

The CSV has one row per company, de-duplicated by domain. Columns: domain, name, status, status_reason, tier, score, score_reasons, industry, employees, founded, state, country, linkedin_url, sources, first_seen, status_since, previous_status, company_id. If `list.json` does not exist yet, say that `/tal-build` comes first.
