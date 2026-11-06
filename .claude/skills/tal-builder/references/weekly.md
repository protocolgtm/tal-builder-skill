# Running the refresh every week

`/tal-refresh` does, in order: take new rows from `tal/inbox/` (new customers become seeds, companies to avoid become anti-seeds), look them up, re-test the envelope if the seeds or anti-seeds changed (and skip pulls if it no longer passes), re-pull lookalikes and every slice marked `"weekly": true` in `slices.json` (pages younger than `pull_max_age_days` are reused), score, merge, export `tal/out/tal.csv` and `tal/out/tal-target.csv`, and list the companies waiting for a read.

Typical weekly cost with two seed groups and one weekly trigger slice: 5 to 40 credits. Set the cap you are comfortable with in the scheduled command.

## Getting new customers in

Anything that can write a CSV can feed it: an export from your CRM of deals closed this week, a form, or you by hand. Append rows to `tal/inbox/new-customers.csv`:

```
domain,group,note
newcustomer.com,core,closed 2026-11-12
```

`group` is optional (default `new-customers`; move them to a proper group with `/tal-seed`). Rows already on file are skipped, so the file can simply grow. The same goes for `tal/inbox/new-anti-seeds.csv` (`domain,note`) for companies you lost, churned or should not have targeted.

## Option 1: a Claude Code scheduled task or routine

Ask Claude Code to schedule `/tal-refresh --unattended --max-credits 30` weekly. Unattended runs do not stop to ask about the inbox; they note that it was empty and continue, and they do the model read of new companies.

## Option 2: cron or launchd, with the model read

```
# Mondays 07:20
20 7 * * 1 cd /path/to/project && claude -p "/tal-refresh --unattended --max-credits 30" >> tal/refresh.log 2>&1
```

`claude -p` needs Claude Code installed and logged in on that machine, and the project's tool permissions must allow `python3` for the run to finish unattended.

## Option 3: no model, just the pipeline

```
20 7 * * 1 cd /path/to/project && python3 .claude/skills/tal-builder/scripts/tal.py refresh --max-credits 30 >> tal/refresh.log 2>&1
```

New companies land as `to read`; run `/tal-refresh` by hand later to read them.
