# Operations

## Prospeo

- **Endpoint:** `POST https://api.prospeo.io/search-company`, header `X-KEY`, body `{"filters": {...}, "page": N}`. Filter shapes the skill uses are in `.claude/skills/tal-builder/references/prospeo-filters.md`.
- **Pages:** 25 companies a page; a search shows at most 1,000 pages (25,000 companies). Cut a bigger search into slices.
- **Cost:** 1 credit for a page that returns at least one company. Free: an identical page repeated within 30 days (`"free": true`), and a search with no results (`NO_RESULTS`, HTTP 400). Seed lookup is a search on `company.websites.include`, so 25 domains cost 1 credit.
- **Errors:** any error other than `NO_RESULTS` (`INVALID_FILTERS`, `PLAN_REQUIRED`, `INSUFFICIENT_CREDITS`, `INVALID_API_KEY`, `INVALID_REQUEST`, `SERVICE_TEMPORARILY_UNAVAILABLE`, `INTERNAL_ERROR`, HTTP 429) stops the command at once; nothing after it is called. Rerun when the cause is fixed: pages already fetched come from the cache.
- **Known limits of the data:** `company.company_oids` is rejected on search-company; department headcount is a search filter but not on the record; some records carry another company's description, and headcounts can understate a firm. The read exists for these.

## Money controls (all in `tal.py`)

- `--max-credits N` on every paid command; without it, or with `--dry-run`, nothing is spent.
- `credit_cap` in `tal/config.json` (default 100) bounds the whole workspace. Only the owner raises it.
- Every page is cached under `tal/data/responses/` by a hash of the request; `pull_max_age_days` (default 7) decides when a refresh refetches.
- Every call is logged in `tal/data/receipts.jsonl` (label, page, charged, free, error code, total). `tal status` sums it.

## Data a workspace holds

The user's own seeds, anti-seeds, Prospeo records and exports, in `tal/`, gitignored by `tal init`. Nothing leaves the machine except the Prospeo requests. Nothing is deleted: companies change status (`stale`, `dropped`, `outside`), and `reads.jsonl` keeps every verdict.
