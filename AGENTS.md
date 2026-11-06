# tal-builder

A public Claude Code skill (`tal-builder`) and seven slash commands that build and refresh a target account list from seeds and anti-seeds with Prospeo's company search. People install it into their own projects with `install.sh`; it runs on their machine with their Prospeo key and their credits. Everything that touches Prospeo, money or data is in one standard-library script, `.claude/skills/tal-builder/scripts/tal.py`; the method and judgment are in `SKILL.md`.

## Access

- Offline work (tests, docs, the script's free commands) needs nothing.
- A live check needs a Prospeo key in the environment as `PROSPEO_API_KEY` (or in a `.env` beside the workspace). It is the maintainer's paid account: do not run any command with `--max-credits` unless the maintainer gave you a credit number for this session. If there is no key, say so and stop; never ask for it in chat and never look for it in other files.

## Run it

- `python3 .claude/skills/tal-builder/scripts/tal.py --help` lists commands. `--dir` picks the workspace (default `./tal`).
- A throwaway workspace: `python3 .claude/skills/tal-builder/scripts/tal.py --dir .live-test/tal init --sample accounting-firms`. `.live-test/` and `tal/` are gitignored; never commit a workspace.
- Paid commands without `--max-credits`, or with `--dry-run`, print what they would call and spend nothing.

## Verify, with evidence

1. `python3 -m unittest discover -s tests` (offline; a fake Prospeo serves synthetic companies). Any change to `tal.py` behaviour updates or adds a test in the same commit. Python 3.9 must still pass (`/usr/bin/python3` on macOS).
2. Real path, only with a credit number from the maintainer: in a `.live-test` workspace, `lookup --max-credits 1`, `test envelope --max-credits 2`, then `status` shows credits spent against the cap. Paste the output.
3. `./install.sh "$(mktemp -d)"` installs the skill and 7 commands.
4. Report what you implemented, tested, and observed live as separate facts.

## Where things live

- `.claude/skills/tal-builder/SKILL.md`: the method. `references/`: Prospeo filter shapes, rubric format, lessons and numbers, weekly scheduling, and the AGENTS block `tal init` writes into a user's project.
- `examples/accounting-firms/`: the shipped sample; `worked/` is one capped live run of it.
- `docs/operations.md`: Prospeo costs, caching and errors. `docs/decisions.md`: why it is built this way. `docs/agent-evals.md`: fresh-session checks for these instructions.

## Rules that are not obvious from the code

- **No real lists.** Never commit customer, prospect or seed lists, Prospeo responses, receipts or exports. The sample's companies are public search results labelled as illustrative, and no one's customers.
- **Credits are money.** Every Prospeo call goes through `search()` in `tal.py`, which caches by request, logs a receipt and enforces both `--max-credits` and the workspace `credit_cap`. Do not add a call path that bypasses it, and never raise a cap on a user's behalf.
- **The key is never printed.** Not in output, logs, errors or tests.
- **Nothing is deleted from a workspace.** Companies change status; `list.json`, `reads.jsonl` and `data/` only grow.
- **Signals score; gates are tested.** Do not turn a rubric signal into an envelope filter without testing it on seeds and anti-seeds; the reason is in `references/lessons.md`.
- **Keep README, SKILL.md and the commands consistent** when a command or its cost changes.
