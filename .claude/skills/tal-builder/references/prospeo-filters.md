# Prospeo company search: filter shapes that work

Checked against Prospeo's docs on 2026-11-06 (https://prospeo.io/api-docs/filters-documentation and https://prospeo.io/api-docs/search-company). Confirm there before relying on a limit.

## The request

`POST https://api.prospeo.io/search-company`, header `X-KEY`, body `{"filters": {...}, "page": 1}`. 25 companies a page, at most 1,000 pages (25,000 companies) per search. 1 credit per page that returns at least one company; an identical page repeated within 30 days is free (`"free": true`). `tal.py` also keeps every response under `tal/data/responses/` and re-reads it instead of paying again.

Errors (`error_code`): `NO_RESULTS` (free, not a failure), `INVALID_FILTERS` and `PLAN_REQUIRED` (read `filter_error`), `INSUFFICIENT_CREDITS`, `INVALID_API_KEY`, `INVALID_REQUEST`, `SERVICE_TEMPORARILY_UNAVAILABLE`, `INTERNAL_ERROR`, and HTTP 429 for the rate limit. An exclude-only search is refused.

## Filters used by this skill

```json
{
  "company_location_search": {"include": ["United States"]},
  "company_headcount_custom": {"min": 11, "max": 200},
  "company_headcount_by_department": [{"department": "Marketing", "min": 0, "max": 3}],
  "company_founded": {"min": 1900, "max": 2021},
  "company_industry": {"include": ["Accounting"], "exclude": []},
  "company_attributes": {"b2b": true, "pricing": true},
  "company_technology": {"include": ["HubSpot"]},
  "company_job_posting_hiring_for": {"include": ["head of marketing", "revenue operations"], "exclude": ["intern"], "match_type": "contains"},
  "company_lookalike": {"company_oids": ["<up to 10 company_id values>"], "minimum_tier": "T1"},
  "company": {"websites": {"include": ["example.com"]}}
}
```

- Location, industry and technology values must match Prospeo's lists exactly (industry names are LinkedIn's; Prospeo's Search Suggestions API returns valid location values). A misspelt value fails the whole request with `INVALID_FILTERS`, which costs nothing.
- `company_headcount_by_department` is a search filter only; the company record does not carry department counts. A company's band is known from the search that found it.
- `company.websites.include` takes root domains only, up to 500. One subdomain fails the whole request. `company.company_oids` is refused on this endpoint, so look companies up by website.
- `company_lookalike` takes at most 10 seed IDs. `minimum_tier` T1 is the most similar; T2 and T3 widen. Lookalikes from real companies beat lookalikes from a written description (`icp_text`), which drift toward whatever the words suggest.
- Technology, job-posting and lookalike filters need Prospeo's Starter plan or above (`PLAN_REQUIRED` otherwise).

## Booleans that do not mean what they say

- `false` on an attribute (for example `uses_ai: false`, `is_venture_backed: false`) can return nothing at all rather than "companies without it". Remove such companies after the download, from the record, instead.
- A record field can be empty where the matching filter is reliable. Read the seed records before choosing: in the run this skill came from, a "business model" field was empty for 7 of 17 known fits while the `b2b` attribute was true for all of them.
- A job-posting filter on a broad word ("marketing") returns staffing firms advertising their clients' jobs. Use narrow titles.

## Record fields worth scoring on

`employee_count`, `founded`, `industry`, `location.country`, `location.state`, `type`, `revenue_range`, `funding.latest_funding_stage`, `funding.latest_funding_date`, `funding.count`, `attributes.has_pricing`, `attributes.has_demo`, `attributes.is_b2b`, `technology.technology_names`, `job_postings.active_titles`, `job_postings.active_count`, `keywords`, `description`, `description_ai`. `tal.py controls` prints them for the seeds and anti-seeds.
