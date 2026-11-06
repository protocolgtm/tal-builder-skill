---
description: Set up a TAL Builder workspace and gather the target, seeds, anti-seeds and credit cap
argument-hint: "[--sample accounting-firms]"
---

Use the `tal-builder` skill. Set up a target account list workspace in this project.

1. Run `python3 <skill>/scripts/tal.py init $ARGUMENTS` (the script is at `.claude/skills/tal-builder/scripts/tal.py` or `~/.claude/skills/tal-builder/scripts/tal.py`). It creates `tal/`, adds a TAL section to the project's `AGENTS.md`, makes `CLAUDE.md` import it, and keeps `.env` out of git. Tell the user which files it changed.
2. Check `.env` has a `PROSPEO_API_KEY` line, without printing the value: `grep -c '^PROSPEO_API_KEY=.' .env`. If it is missing, tell the user to copy `.env.example` to `.env` and paste their key there (Prospeo dashboard → API), never into the chat.
3. If `tal/target.md` is still the template, ask the user for one paragraph: who they sell to, what makes a company a fit, and what makes a similar-looking company wrong.
4. Unless a sample was loaded, ask for seeds and anti-seeds: about ten companies they would love more of (closed customers or their best prospects), and about ten that look similar on paper but are wrong (lost deals, churned, bad fits, competitors). Domains are enough. Ask whether the seeds are one kind of company or several; each kind becomes its own group. Add them with `tal.py seed add <group> ...` and `tal.py antiseed add ... --note "<why wrong>"` (no `--max-credits` yet, so nothing is spent).
5. Ask what credit cap to set in `tal/config.json` (`credit_cap`, default 100). Explain that a first build typically costs 20 to 150 credits depending on how many lookalikes they pull, and that every paid step will say its cost first.
6. Finish with `tal.py status` and suggest `/tal-build` as the next step.
