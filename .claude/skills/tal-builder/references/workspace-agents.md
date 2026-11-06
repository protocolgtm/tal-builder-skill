<!-- tal-builder:start -->
## Target account list (TAL Builder)

This project keeps a target account list with the `tal-builder` skill. Workspace: `tal/`. Script: `python3 .claude/skills/tal-builder/scripts/tal.py` (or `~/.claude/skills/tal-builder/scripts/tal.py`); `--help` lists commands.

What an agent working here should do:

- **A deal closes or a strong prospect replies:** append the company to `tal/inbox/new-customers.csv` (`domain,group,note`), or run `/tal-seed add <group> <domain>`. Seeds are how the list grows; keep each group to one kind of company.
- **A company turns out wrong** (churned, a competitor, the wrong buyer): append it to `tal/inbox/new-anti-seeds.csv` (`domain,note`), or run `/tal-antiseed add <domain>`.
- **Need the list:** `tal/out/tal-target.csv` (targets only) or `tal/out/tal.csv` (every company, with status and reason). Run `/tal-export` if it is stale.
- **Weekly:** `/tal-refresh`. It asks for new customers and anti-seeds when the inbox has nothing new.

Rules:

- Prospeo credits are the owner's money. Any paid command needs `--max-credits`; say the cost first; never raise `credit_cap` in `tal/config.json` without the owner's yes.
- `PROSPEO_API_KEY` lives in `.env`. Never print it, copy it or ask for it in chat. If it is missing, say so and stop.
- Never delete rows from `tal/list.json`, `tal/reads.jsonl` or `tal/data/`. Companies change status; they are not removed.
- Do not edit `tal/envelope.json` or `tal/rubric.json` without re-testing (`tal.py test envelope`, `tal.py score`) and telling the owner what changed.
<!-- tal-builder:end -->
