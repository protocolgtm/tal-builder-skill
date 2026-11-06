---
name: tal-builder
description: Build and keep a target account list (TAL) current from seeds (your best customers or prospects) and anti-seeds (companies that look similar and are wrong), using Prospeo's company search and lookalikes. Use when the user wants to build, grow, refresh, re-score or export a target account list or TAM, add or remove seed or anti-seed companies, or schedule a weekly TAL refresh.
---

# TAL Builder

You turn a short list of companies the user knows are right, and a short list they know are wrong, into one scored, read and de-duplicated list of companies to sell to, and you keep it current every week. Prospeo supplies the company data. You supply the judgment: you read the seeds and anti-seeds side by side, propose how to find more like the seeds, test that proposal against both lists, and read the top of the result.

Everything runs through `scripts/tal.py` in this skill folder (Python 3.10+, standard library only). Find it at `.claude/skills/tal-builder/scripts/tal.py` in the project, or `~/.claude/skills/tal-builder/scripts/tal.py` for a user-level install. Below, `tal` means `python3 <that path>`. The workspace is `./tal` unless `--dir` or `TAL_DIR` says otherwise.

## Rules that protect the user's money and data

- **Credits are the user's money.** Every command that can call Prospeo needs `--max-credits N`; without it nothing paid is called. Say the most it can cost before you run it, and get the user's yes for anything above what they already approved. `--dry-run` spends nothing. One search page (25 companies) costs 1 credit; a page with no results and a page already fetched are free. `config.json` → `credit_cap` is the workspace ceiling; raising it is the user's decision, never yours.
- **The key stays secret.** `PROSPEO_API_KEY` lives in `.env` (git-ignored). Never print it, echo it, write it elsewhere or ask for it in chat. If it is missing, tell the user to add it to `.env` and stop.
- **Stop on any Prospeo error** other than "no results". `tal.py` already stops; report the error code and do not retry with different filters until you have read `references/prospeo-filters.md`.
- **Nothing is deleted.** A company that stops fitting gets a status and a reason. Removing a seed marks what only it found as `stale`.
- **The score orders; the read judges.** Never call a company a target from its score alone.

## The method (what `/tal-build` walks through)

1. **Target paragraph.** `tal/target.md`: who the user sells to, what makes a company a fit, what makes a look-alike wrong. Ask for it if it is the template text.
2. **Seeds and anti-seeds.** Ten of each is enough to start. Seeds go in named groups of one kind of company (`core`, `agencies`): lookalikes extend the kind of company they are given, and two kinds in one search blur each other. Record for each seed whether the user named it or you suggested it; get your suggestions confirmed before they steer lookalikes. Anti-seeds matter as much as seeds: a filter that keeps every fit is useless if it keeps every miss too.
3. **Look them up** (`tal lookup --max-credits 1`, 1 credit per 25 domains). Root domains only. From then on match on Prospeo's `company_id`, never the domain: Prospeo's domain for a company is sometimes not the one you have.
4. **Read the records side by side** (`tal controls`, free). Before designing any filter. Look for fields that separate seeds from anti-seeds, and for fields that look useful but are empty on the seeds. Write `tal/analysis.md`: which filters separate them and why, which seeds belong in separate groups, what the envelope should be, which signals should score, what should exclude outright, and what you are unsure of. Show the user a short version.
5. **Envelope: the hard filters every fit passes.** Write `tal/envelope.json` (`{"filters": {...}}` in Prospeo's shape; see `references/prospeo-filters.md`). Test it: `tal test envelope --max-credits 2`. It must keep at least 80% of seeds and no anti-seeds (`config.json` sets both). A seed the envelope drops may mean the envelope is wrong, not the seed; say which and why. Some anti-seeds look exactly like fits to every filter (an exam-prep publisher labelled Accounting, at the right size): list their domains under `"rubric_handles"` in `envelope.json`, add a rubric exclusion that catches them, and `tal score` will warn if one still reaches the target tiers. Do not use this to wave through an anti-seed a filter could remove. Test candidate filters one at a time on the controls (`tal test '<json>'`) rather than guessing. Then size it once, open: `tal size envelope --max-credits 1`. That number is the market, not a list.
6. **Signals, not gates.** A filter that sounds like quality (sales-led, has a pricing page, revenue band) usually drops real fits when used as a gate. Put those in `tal/rubric.json` as scored signals; put only true deal-breakers in `exclude` (for a services seller, the first is "it sells what we sell"). Ask the user what would make a company of this kind wrong, and gate on the answer. `tal signals` (free) shows how often each fires on seeds, anti-seeds and pulled companies; a signal no more common among seeds than in the pull carries little information. See `references/scoring.md`.
7. **Pull.** Lookalikes first, they are the cheapest good companies: `tal lookalikes` (count, 1 credit per ten seeds), then `tal lookalikes GROUP --pull --max-credits N`. Then any extra slices in `tal/slices.json` (the envelope cut by a high-lift signal, a hiring trigger) with `tal pull NAME --max-credits N`. Size before you pull; one search returns at most 25,000 companies. Downloading a whole category with no seeds is the expensive way in: ask for seeds of that kind first.
8. **Score** (`tal score`, free). Check the seeds and anti-seeds it prints: if both land in the top tiers, the score only orders companies, which is fine, because the read judges.
9. **Read** every company in the target tiers. `tal read-queue` writes batches; for each batch, read each description against `target.md` and write `batch-NNN.verdicts.jsonl`, one line per company: `{"i": 0, "verdict": "keep|drop|check", "reason": "one line"}`. Drop for what the record cannot show: owned by a larger company, sells to the wrong buyer, not really in the country. Mark `check`, not `drop`, when the reason comes from your memory rather than the text, and settle checks from the company's site or a search. `tal read-merge` refuses a file with a missing or repeated index. Use subagents for large reads, one batch each.
10. **Merge and export** (`tal merge`, `tal export`, `tal export --status target`). Statuses: target, to read, check, reserve (tier C), low score, stale, dropped, outside (fails a gate, with which), not found, seed, anti-seed.

## Keeping it current

`/tal-refresh` runs weekly. New closed customers go in `tal/inbox/new-customers.csv` (`domain,group,note`), new companies to avoid in `tal/inbox/new-anti-seeds.csv`. Check `tal inbox` first: if there is no new input since the last refresh and someone is there to ask, ask whether there are new customers or companies to avoid before spending anything. Scheduling options are in `references/weekly.md`.

## Lessons from the run this skill came from

One B2B services firm used this method on its own market: 17 known fits and 8 known misses, an envelope that kept 12 of the fits and none of the misses and sized the market at 79,860 companies, and about 800 credits to a scored list of 7,331 and a target of 3,382 after every company inside the envelope was read. What it learned is in `references/lessons.md`. Read it before step 5.
