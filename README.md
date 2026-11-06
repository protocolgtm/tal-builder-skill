# TAL Builder

A Claude Code skill and seven slash commands that build a target account list (TAL) from companies you know are right and companies you know are wrong, then keep it current every week. Company data comes from [Prospeo](https://prospeo.io)'s company search and lookalikes; Claude does the judgment.

It packages the method a B2B services firm used to replace a list that, by construction, excluded its own customers. Seventeen companies it knew were right and eight it knew were wrong became an envelope of 79,860 companies, and about 800 credits later a scored list of 7,331 with 3,382 targets, every one read by the model. The numbers and lessons are in [`lessons.md`](.claude/skills/tal-builder/references/lessons.md).

> [!IMPORTANT]
> **No warranty.** This is provided "as is", without warranty of any kind, under the [MIT License](LICENSE). Prospeo credits are your money: every paid command needs an explicit `--max-credits`, says its cost first, and stops at the workspace cap in `tal/config.json`, but you are responsible for what you spend and for how you use the data, including your obligations under Prospeo's terms and any privacy or marketing law that applies to you. The list is a list of companies; this skill does not find or contact people.

Disclosure: Prospeo gave the author, Henry Hund, a free test account in exchange for feedback and posts. The skill works with any paid Prospeo plan that includes company search.

## How it works

1. **Seeds and anti-seeds.** About ten companies you want more of (closed customers or your best prospects), in groups of one kind, and about ten that look similar on paper and are wrong.
2. **Read them side by side.** Claude reads the Prospeo records of both lists and proposes what separates them.
3. **Envelope.** The hard filters every fit passes, tested on both lists before it gates anything: it must keep at least 80% of seeds and none of the anti-seeds. Sized once: that number is the market, not the list.
4. **Signals score; they do not gate.** Filters that sound like quality (a pricing page, a revenue band) drop real fits when used as gates. They become points in a rubric, weighted by how much more common they are among seeds than in the market.
5. **Pull lookalikes**, ten seeds per search, inside the envelope. They are the cheapest good companies.
6. **Score, then read.** The score orders companies; Claude reads every company in the target tiers, in batches, and keeps, drops or marks each one to check, with a reason.
7. **One list, one CSV.** Every company keeps a status and a reason (target, to read, check, reserve, dropped, outside, stale and so on). Nothing is deleted; companies change status.
8. **Weekly refresh.** New customers go in an inbox file and become seeds; new bad fits become anti-seeds. The refresh looks them up, re-tests the envelope, pulls new lookalikes, rescores, and exports.

## Install

```bash
git clone https://github.com/protocolgtm/tal-builder-skill.git
cd tal-builder-skill
./install.sh                       # every project: ~/.claude
./install.sh ~/path/to/project     # or one project: its .claude/
```

Then, in the project where you want the list:

```bash
cp ~/path/to/tal-builder-skill/.env.example .env   # paste your Prospeo API key into .env
```

Python 3.9 or newer, standard library only. Nothing else to install.

## Commands

| Command | What it does | Spends credits |
|---|---|---|
| `/tal-init [--sample accounting-firms]` | Creates `tal/`, adds a section to the project's `AGENTS.md` (and makes `CLAUDE.md` import it) so any agent knows how to feed the list, asks for your target, seeds, anti-seeds and credit cap | No |
| `/tal-build` | The whole method, with a checkpoint for your approval before every paid step | Yes, each step capped |
| `/tal-seed add\|remove <group> <domain>...` | Change seeds | Lookup: 1 per 25 domains |
| `/tal-antiseed add\|remove <domain>...` | Change anti-seeds | Lookup: 1 per 25 domains |
| `/tal-refresh [--unattended --max-credits N]` | The weekly run. Checks the inbox first and asks for new customers and bad fits if there is nothing new | Yes, capped |
| `/tal-export [--status target]` | Writes `tal/out/tal.csv` or the targets-only CSV | No |
| `/tal-status` | Seeds, envelope test, list counts, credits spent against the cap | No |

Try it on the shipped sample first: `/tal-init --sample accounting-firms`, then `/tal-build`. The sample is a made-up seller of client-portal software to independent US CPA firms, with ten seed firms and twelve anti-seeds picked from public search results; none is anyone's customer. A capped run of it cost 22 credits; [what it found](.claude/skills/tal-builder/examples/accounting-firms/worked/README.md).

## Costs

Prospeo charges 1 credit for each page of 25 companies a search returns. Repeating an identical page within 30 days is free, and so is a search with no results. The skill caches every page it fetches, so reruns cost nothing. A first build typically costs 20 to 150 credits, depending on how many lookalikes you pull; the method's original run cost about 800 because it downloaded a whole category with no seeds, which the skill now warns against. Every paid call is logged in `tal/data/receipts.jsonl`.

## Running it weekly

See [`weekly.md`](.claude/skills/tal-builder/references/weekly.md): a Claude Code scheduled task, a cron line that runs `/tal-refresh --unattended` with a credit limit, or the script alone with no model (it skips the read and leaves new companies as "to read").

## Repository layout

```
.
├── README.md
├── LICENSE
├── AGENTS.md / CLAUDE.md          # for agents editing this repository
├── install.sh
├── .env.example
├── docs/                          # operations, decisions, agent evals
├── tests/test_tal.py              # offline tests with a fake Prospeo
└── .claude/
    ├── commands/tal-*.md          # the slash commands
    └── skills/tal-builder/
        ├── SKILL.md               # the method
        ├── scripts/tal.py         # every Prospeo call, cache, cap, score, merge, export
        ├── references/            # filters, scoring, lessons, weekly, workspace AGENTS block
        └── examples/accounting-firms/
```

## Contributing

Issues and pull requests are welcome. Never include real customer, prospect or seed lists, API keys or Prospeo responses in examples or issues.

## License

MIT, provided as is with no warranty. See [LICENSE](LICENSE).
