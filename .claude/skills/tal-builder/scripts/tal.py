#!/usr/bin/env python3
"""TAL Builder: build and keep a target account list current from seeds and
anti-seeds, with Prospeo's company search. Python standard library only.

Run `tal.py --help` or `tal.py <command> --help`. Every command that can spend
Prospeo credits needs --max-credits N and accepts --dry-run, which spends
nothing. The API key comes from PROSPEO_API_KEY in the environment or in a
.env file in the project; it is never printed or written anywhere else.

Workspace files (default ./tal, change with --dir):
  config.json      credit cap, read rules, tier cut-offs
  target.md        the target in one paragraph (written by you or the agent)
  seeds.json       seed groups: companies you want more of
  anti-seeds.json  companies that look similar and are wrong
  envelope.json    hard filters every fit passes (Prospeo filter shape)
  rubric.json      exclusions and scoring signals, applied offline
  slices.json      extra named searches to pull (signal cuts, trigger slices)
  inbox/           new-customers.csv and new-anti-seeds.csv, read by refresh
  data/            raw responses, receipts, records, slice inventories
  reads.jsonl      the model's keep / drop / check verdicts
  list.json        the one list, every company with score, tier and status
  out/             CSV exports
"""
import argparse, csv, datetime, hashlib, json, os, pathlib, re, sys, time, urllib.error, urllib.request

API = 'https://api.prospeo.io/'
FREE_ERRORS = {'NO_RESULTS'}  # documented: credits are charged only when a page returns companies
LOOKALIKE_MAX = 10            # Prospeo takes at most ten seed company IDs per lookalike search
PAGE_SIZE = 25
NOW = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')

DEFAULT_CONFIG = {
    'credit_cap': 100,               # total paid credits this workspace may spend; raise it on purpose
    'gate_keep_seeds_min': 0.8,      # an envelope must keep at least this share of seeds...
    'gate_keep_anti_max': 0,         # ...and at most this many anti-seeds
    'tiers': {'A': 55, 'B': 35, 'C': 15},
    'target_tiers': ['A', 'B'],      # tiers that can become target; the rest are reserve or low score
    'require_read': True,            # a company is target only after the model read keeps it
    'lookalike_tier': 'T1',          # T1 is the tightest; T2 and T3 widen and blur
    'pull_max_age_days': 7,          # stored pull pages older than this are fetched again on refresh
}


class Stop(SystemExit):
    pass


# ---------------------------------------------------------------- workspace

class WS:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.data = self.root / 'data'

    def p(self, name):
        return self.root / name

    def load(self, name, default=None):
        path = self.p(name)
        if not path.exists():
            return default
        return json.loads(path.read_text())

    def save(self, name, obj):
        path = self.p(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + '\n')
        tmp.replace(path)

    def config(self):
        return {**DEFAULT_CONFIG, **(self.load('config.json', {}) or {})}

    def require(self):
        if not self.p('config.json').exists():
            raise Stop(f'No workspace at {self.root}. Run: tal.py init')

    # receipts: one line per real (non-cached) API call
    def receipts(self):
        path = self.data / 'receipts.jsonl'
        if not path.exists():
            return []
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    def spent(self):
        return sum(1 for r in self.receipts() if r.get('charged'))

    def add_receipt(self, row):
        self.data.mkdir(parents=True, exist_ok=True)
        with open(self.data / 'receipts.jsonl', 'a') as fh:
            fh.write(json.dumps(row) + '\n')

    def records(self):
        return self.load('data/records.json', {}) or {}

    def inventories(self):
        return self.load('data/inventories.json', {}) or {}


# ---------------------------------------------------------------- domains

def root_domain(value):
    d = value.strip().lower()
    d = re.sub(r'^[a-z]+://', '', d).split('/')[0].split('?')[0].split(':')[0]
    d = d.removeprefix('www.')
    return d


def check_domains(values):
    out, bad = [], []
    for v in values:
        d = root_domain(v)
        if not d:
            continue
        # Prospeo rejects the whole request for a subdomain; keep two-part
        # names and common two-part suffixes such as co.uk.
        parts = d.split('.')
        ok = len(parts) == 2 or (len(parts) == 3 and parts[-2] in {'co', 'com', 'org', 'net', 'ac', 'gov'} and len(parts[-1]) == 2)
        (out if ok and re.fullmatch(r'[a-z0-9.-]+', d) else bad).append(d)
    if bad:
        raise Stop(f'Root domains only (Prospeo rejects the whole request otherwise): {bad}')
    return sorted(set(out))


def read_csv_domains(path):
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        cols = {c.lower().strip(): c for c in reader.fieldnames or []}
        dcol = cols.get('domain') or cols.get('website') or cols.get('url')
        if not dcol:
            raise Stop(f'{path}: needs a "domain" column')
        for r in reader:
            if (r.get(dcol) or '').strip():
                rows.append({'domain': root_domain(r[dcol]), 'group': (r.get(cols.get('group', '')) or '').strip(), 'note': (r.get(cols.get('note', '')) or r.get(cols.get('reason', '')) or '').strip()})
    return rows


# ---------------------------------------------------------------- Prospeo

def api_key(ws):
    key = os.environ.get('PROSPEO_API_KEY')
    if not key:
        for env in (ws.root / '.env', ws.root.parent / '.env', pathlib.Path('.env')):
            if env.exists():
                for line in env.read_text().splitlines():
                    m = re.match(r'\s*(?:export\s+)?PROSPEO_API_KEY\s*=\s*(.*)$', line)
                    if m:
                        key = m.group(1).strip().strip('"').strip("'")
                        break
            if key:
                break
    if not key:
        raise Stop('PROSPEO_API_KEY is not set. Put it in .env (see .env.example). Do not paste it into chat.')
    return key


def http_post(endpoint, payload, key):
    """One request. Returns the parsed JSON body, also for 4xx answers."""
    req = urllib.request.Request(API + endpoint, data=json.dumps(payload).encode(), headers={'X-KEY': key, 'Content-Type': 'application/json'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            body = err.read()
            if err.code == 429 and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            try:
                return json.loads(body)
            except ValueError:
                return {'error': True, 'error_code': f'HTTP_{err.code}'}
        except urllib.error.URLError as err:
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            return {'error': True, 'error_code': 'NETWORK', 'detail': str(err.reason)[:200]}
    return {'error': True, 'error_code': 'RATE_LIMITED'}


TRANSPORT = http_post  # tests replace this


class Budget:
    """Credits one command may spend: its --max-credits, inside the workspace cap."""

    def __init__(self, ws, max_credits, dry_run):
        self.ws, self.max, self.dry, self.used = ws, max_credits, dry_run, 0
        self.cap = ws.config()['credit_cap']
        self.would = 0  # pages a dry run would have paid for

    def left(self):
        if self.max is None:
            return 0
        return max(0, min(self.max - self.used, self.cap - self.ws.spent()))

    def why_stopped(self):
        if self.max is None:
            return 'this command was given no --max-credits'
        if self.ws.spent() >= self.cap:
            return f'workspace credit cap of {self.cap} reached (config.json credit_cap; raising it is your decision)'
        return f'--max-credits {self.max} reached'


def search(ws, budget, label, filters, page=1, max_age_days=None):
    """One search-company page. Stored answers are re-read, not paid for again.

    Returns the response dict, or None when a dry run or the budget stopped it.
    Stops the whole command on any provider error that is not NO_RESULTS.
    """
    payload = {'filters': filters, 'page': page}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    path = ws.data / 'responses' / f'{digest}.json'
    if path.exists():
        stored = json.loads(path.read_text())
        age = datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(stored['at'])
        if max_age_days is None or age.days < max_age_days:
            return stored['response']
    if budget.dry:
        budget.would += 1
        print(f'  dry run: would call search-company for {label} page {page} (1 credit if it returns companies)')
        return None
    if budget.left() < 1:
        print(f'  not called: {label} page {page}; {budget.why_stopped()}')
        return None
    response = TRANSPORT('search-company', payload, api_key(ws))
    charged = not response.get('error') and response.get('free') is False
    ws.add_receipt({'at': NOW(), 'label': label, 'page': page, 'digest': digest, 'charged': charged, 'free': response.get('free'), 'error_code': response.get('error_code'), 'total': (response.get('pagination') or {}).get('total_count')})
    if charged:
        budget.used += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'at': NOW(), 'label': label, 'payload': payload, 'response': response}))
    if response.get('error') and response.get('error_code') not in FREE_ERRORS:
        raise Stop(f"{label}: Prospeo answered {response.get('error_code')} {json.dumps(response.get('filter_error') or '')[:300]}. Stopped; nothing more was called.")
    return response


def companies(response):
    return [r['company'] for r in (response or {}).get('results', []) if r.get('company')]


def total(response):
    return ((response or {}).get('pagination') or {}).get('total_count') or 0


def pages(response):
    return ((response or {}).get('pagination') or {}).get('total_page') or 0


def keep_records(ws, rows):
    recs = ws.records()
    for c in rows:
        recs[c['company_id']] = c
    ws.save('data/records.json', recs)


def pull_all(ws, budget, label, filters, max_age_days=None):
    """Every page of a search, inside the budget. Returns (company_ids, complete, total_count)."""
    first = search(ws, budget, label, filters, 1, max_age_days)
    if first is None:
        return None, False, None
    n_pages, ids = pages(first), []
    rows = companies(first)
    need = sum(1 for p in range(2, n_pages + 1) if not stored(ws, filters, p, max_age_days))
    if need:
        print(f'  {label}: {total(first)} companies on {n_pages} pages; {need} more page(s) to fetch, up to {need} credits')
    complete = True
    for p in range(2, n_pages + 1):
        r = search(ws, budget, label, filters, p, max_age_days)
        if r is None:
            complete = False
            break
        rows += companies(r)
    keep_records(ws, rows)
    ids = list(dict.fromkeys(c['company_id'] for c in rows))
    return ids, complete, total(first)


def stored(ws, filters, page, max_age_days):
    digest = hashlib.sha256(json.dumps({'filters': filters, 'page': page}, sort_keys=True).encode()).hexdigest()[:16]
    path = ws.data / 'responses' / f'{digest}.json'
    if not path.exists():
        return False
    if max_age_days is None:
        return True
    at = datetime.datetime.fromisoformat(json.loads(path.read_text())['at'])
    return (datetime.datetime.now(datetime.timezone.utc) - at).days < max_age_days


def set_inventory(ws, slice_name, ids, complete, total_count, meta=None):
    inv = ws.inventories()
    inv[slice_name] = {'at': NOW(), 'ids': ids, 'complete': complete, 'total': total_count, **(meta or {})}
    ws.save('data/inventories.json', inv)


# ---------------------------------------------------------------- controls (seeds + anti-seeds)

def seeds(ws):
    return ws.load('seeds.json', {'groups': {}})


def antis(ws):
    return ws.load('anti-seeds.json', {'anti_seeds': []})


def control_rows(ws):
    """[(kind, group, entry)] for every seed and anti-seed."""
    out = []
    for g, grp in seeds(ws)['groups'].items():
        out += [('seed', g, s) for s in grp['seeds']]
    out += [('anti', None, a) for a in antis(ws)['anti_seeds']]
    return out


def lookup(ws, budget):
    """Resolve every seed and anti-seed with no company_id: 1 credit per 25 domains."""
    rows = [r for r in control_rows(ws) if not r[2].get('company_id') and not r[2].get('unresolved')]
    if not rows:
        return
    domains = sorted({r[2]['domain'] for r in rows})
    found = {}
    for i in range(0, len(domains), PAGE_SIZE):
        chunk = domains[i:i + PAGE_SIZE]
        resp = search(ws, budget, 'lookup', {'company': {'websites': {'include': chunk}}})
        if resp is None:
            return
        for c in companies(resp):
            for d in [c.get('domain')] + [root_domain(w) for w in c.get('other_websites') or []]:
                if d:
                    found.setdefault(d, c)
        keep_records(ws, companies(resp))
    sd, ad = seeds(ws), antis(ws)
    for grp in sd['groups'].values():
        for s in grp['seeds']:
            fill(s, found)
    for a in ad['anti_seeds']:
        fill(a, found)
    ws.save('seeds.json', sd)
    ws.save('anti-seeds.json', ad)
    for kind, g, e in control_rows(ws):
        if e['domain'] in domains:
            print(f"  {kind:5} {g or '':14} {e['domain']:28} " + (f"-> {e.get('name')} | {e.get('employees')} staff | {e.get('industry')}" if e.get('company_id') else 'NOT FOUND at Prospeo (check the domain; it stays unresolved)'))


def fill(entry, found):
    if entry.get('company_id') or entry['domain'] not in found:
        if not entry.get('company_id') and entry['domain'] not in found:
            entry['unresolved'] = True
        return
    c = found[entry['domain']]
    entry.update({'company_id': c['company_id'], 'name': c.get('name'), 'employees': c.get('employee_count'), 'industry': c.get('industry')})
    entry.pop('unresolved', None)


def test_on_controls(ws, budget, label, filters):
    """Run filters restricted to the seeds and anti-seeds. Matches on company ID."""
    rows = [r for r in control_rows(ws) if r[2].get('company_id')]
    if not rows:
        raise Stop('No resolved seeds or anti-seeds yet. Add them, then run: tal.py lookup --max-credits 2')
    domains = sorted({r[2]['domain'] for r in rows})
    f = json.loads(json.dumps(filters))
    f.setdefault('company', {})['websites'] = {'include': domains}
    kept = set()
    for i in range(0, len(domains), 500):
        f['company']['websites']['include'] = domains[i:i + 500]
        p = 1
        while True:
            resp = search(ws, budget, f'test:{label}', f, p)
            if resp is None:
                return None
            kept |= {c['company_id'] for c in companies(resp)}
            if p >= pages(resp):
                break
            p += 1
    s = [r for r in rows if r[0] == 'seed']
    a = [r for r in rows if r[0] == 'anti']
    ks = [r[2]['name'] or r[2]['domain'] for r in s if r[2]['company_id'] in kept]
    ds = [r[2]['name'] or r[2]['domain'] for r in s if r[2]['company_id'] not in kept]
    ka = [r[2]['name'] or r[2]['domain'] for r in a if r[2]['company_id'] in kept]
    print(f'  {label}: keeps {len(ks)} of {len(s)} seeds, {len(ka)} of {len(a)} anti-seeds')
    if ds:
        print(f'    seeds it drops: {ds}  (a dropped seed may mean the filter is wrong, not the seed)')
    if ka:
        print(f'    anti-seeds it keeps: {ka}')
    return {'seeds_kept': len(ks), 'seeds': len(s), 'anti_kept': len(ka), 'antis': len(a), 'seeds_dropped': ds, 'anti_kept_names': ka,
            'anti_kept_domains': [r[2]['domain'] for r in a if r[2]['company_id'] in kept]}


# ---------------------------------------------------------------- record tests, gates and scoring (offline)

def get_path(rec, path):
    cur = rec
    for part in path.split('.'):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def text_of(v):
    if v is None:
        return ''
    if isinstance(v, (list, tuple)):
        return ' | '.join(text_of(x) for x in v)
    if isinstance(v, dict):
        return ' | '.join(text_of(x) for x in v.values())
    return str(v)


def test(rec, cond, sources=()):
    """A rubric condition. {"all": [...]}, {"any": [...]}, {"not": {...}} or
    {"path": "...", "op": "...", "value": ...}; path "sources" tests which
    searches found the company."""
    if 'all' in cond:
        return all(test(rec, c, sources) for c in cond['all'])
    if 'any' in cond:
        return any(test(rec, c, sources) for c in cond['any'])
    if 'not' in cond:
        return not test(rec, cond['not'], sources)
    path, op, val = cond['path'], cond['op'], cond.get('value')
    v = list(sources) if path == 'sources' else get_path(rec, path)
    if op == 'exists':
        return v not in (None, '', [], {}, 0, False)
    if op == 'eq':
        return v == val
    if op == 'in':
        return v in val
    if op in ('gte', 'lte', 'between'):
        if not isinstance(v, (int, float)):
            return False
        lo, hi = (val, None) if op == 'gte' else (None, val) if op == 'lte' else val
        return (lo is None or v >= lo) and (hi is None or v <= hi)
    if op == 'contains_any':
        t = text_of(v).lower()
        return any(str(x).lower() in t for x in val)
    if op == 'regex':
        return re.search(val, text_of(v), re.I) is not None
    if op == 'starts_with_any':
        return any(str(x) == p or str(x).startswith(p) for x in (v or []) for p in val)
    if op == 'within_years':
        s = text_of(v)[:10]
        try:
            d = datetime.date.fromisoformat(s)
        except ValueError:
            return False
        return (datetime.date.today() - d).days <= 365.25 * val
    raise Stop(f'Unknown op {op!r} in rubric.json')


def record_gates(envelope):
    """The envelope's filters that can be checked on a stored record. Department
    headcount is a search filter only, so it is known from the search, not the record."""
    f = envelope.get('filters', {})
    gates = []
    loc = (f.get('company_location_search') or {}).get('include')
    if loc:
        gates.append(('location', lambda r, loc=loc: any(x.lower() in text_of([get_path(r, 'location.country'), get_path(r, 'location.state'), get_path(r, 'location.city')]).lower() for x in loc)))
    hc = f.get('company_headcount_custom')
    if hc:
        gates.append((f"{hc.get('min', 1)} to {hc.get('max', '')} employees", lambda r, hc=hc: isinstance(r.get('employee_count'), int) and hc.get('min', 0) <= r['employee_count'] <= hc.get('max', 10**9)))
    fo = f.get('company_founded')
    if fo:
        gates.append((f"founded {fo.get('min', 1900)} to {fo.get('max', '')}", lambda r, fo=fo: (r.get('founded') is None and fo.get('include_unknown_founded')) or (isinstance(r.get('founded'), int) and fo.get('min', 0) <= r['founded'] <= fo.get('max', 9999))))
    ind = f.get('company_industry') or {}
    if ind.get('include'):
        gates.append(('industry', lambda r, s=set(ind['include']): r.get('industry') in s))
    if ind.get('exclude'):
        gates.append(('industry not excluded', lambda r, s=set(ind['exclude']): r.get('industry') not in s))
    return gates


def score_one(rec, sources, rubric, gates):
    failed = [name for name, fn in gates if not fn(rec)]
    for ex in rubric.get('exclude', []):
        if test(rec, ex['when'], sources):
            failed.append(ex['reason'])
    pts, why = 0, []
    for sig in rubric.get('signals', []):
        if test(rec, sig['when'], sources):
            pts += sig['points']
            why.append(f"{sig['points']:+d} {sig['label']}")
    return pts, why, failed


def tier_of(score, tiers):
    for t in ('A', 'B', 'C'):
        if score >= tiers[t]:
            return t
    return 'low'


# ---------------------------------------------------------------- commands

def cmd_init(ws, a):
    ws.root.mkdir(parents=True, exist_ok=True)
    for sub in ('inbox', 'out', 'data'):
        (ws.root / sub).mkdir(exist_ok=True)
    made = []
    def put(name, content):
        if not ws.p(name).exists():
            if isinstance(content, str):
                ws.p(name).write_text(content)
            else:
                ws.save(name, content)
            made.append(name)
    put('config.json', DEFAULT_CONFIG)
    put('seeds.json', {'groups': {}})
    put('anti-seeds.json', {'anti_seeds': []})
    put('target.md', '# Target\n\nWrite one paragraph: who you sell to, what makes a company a fit, and what makes one that looks similar wrong.\n')
    put('inbox/new-customers.csv', 'domain,group,note\n')
    put('inbox/new-anti-seeds.csv', 'domain,note\n')
    if a.sample:
        sample = pathlib.Path(__file__).resolve().parents[1] / 'examples' / a.sample
        if not sample.exists():
            raise Stop(f'No sample named {a.sample} in {sample.parent}')
        ws.p('target.md').write_text((sample / 'target.md').read_text())
        sd, ad = seeds(ws), antis(ws)
        for r in read_csv_domains(sample / 'seeds.csv'):
            g = r['group'] or 'core'
            sd['groups'].setdefault(g, {'created': datetime.date.today().isoformat(), 'seeds': []})['seeds'].append({'domain': r['domain'], 'note': r['note'], 'added': datetime.date.today().isoformat()})
        for r in read_csv_domains(sample / 'anti-seeds.csv'):
            ad['anti_seeds'].append({'domain': r['domain'], 'note': r['note'], 'added': datetime.date.today().isoformat()})
        ws.save('seeds.json', sd)
        ws.save('anti-seeds.json', ad)
        made.append(f'sample {a.sample}')
    if not a.no_agent_files:
        made += write_agent_files(pathlib.Path(a.project))
    print(f'workspace {ws.root}: ' + (', '.join(made) if made else 'already set up, nothing changed'))


START, END = '<!-- tal-builder:start -->', '<!-- tal-builder:end -->'


def write_agent_files(project):
    """Put the TAL block in the project's AGENTS.md (replacing an older block),
    make CLAUDE.md import it, and keep .env out of git. Returns what changed."""
    block = (pathlib.Path(__file__).resolve().parents[1] / 'references' / 'workspace-agents.md').read_text().strip()
    changed = []
    agents = project / 'AGENTS.md'
    text = agents.read_text() if agents.exists() else ''
    if START in text and END in text:
        new = text[:text.index(START)] + block + text[text.index(END) + len(END):]
    else:
        new = (text.rstrip() + '\n\n' if text.strip() else '') + block + '\n'
    if new != text:
        agents.write_text(new)
        changed.append('AGENTS.md (TAL section)')
    claude = project / 'CLAUDE.md'
    ctext = claude.read_text() if claude.exists() else ''
    if '@AGENTS.md' not in ctext and START not in ctext:
        claude.write_text((ctext.rstrip() + '\n\n' if ctext.strip() else '') + '@AGENTS.md\n')
        changed.append('CLAUDE.md (imports AGENTS.md)')
    gi = project / '.gitignore'
    gtext = gi.read_text() if gi.exists() else ''
    if not re.search(r'^\.env$', gtext, re.M):
        gi.write_text((gtext.rstrip() + '\n' if gtext.strip() else '') + '.env\n')
        changed.append('.gitignore (.env)')
    return changed


def add_controls(ws, a, kind):
    ws.require()
    domains = check_domains(a.domains + ([r['domain'] for r in read_csv_domains(a.csv)] if a.csv else []))
    if not domains:
        raise Stop('No domains given')
    today = datetime.date.today().isoformat()
    if kind == 'seed':
        if not re.fullmatch(r'[a-z0-9-]+', a.group):
            raise Stop('GROUP is lowercase letters, digits and hyphens, e.g. "core" or "agencies"')
        sd = seeds(ws)
        anti = {x['domain'] for x in antis(ws)['anti_seeds']}
        clash = [d for d in domains if d in anti]
        if clash:
            raise Stop(f'Already anti-seeds: {clash}. Remove them there first.')
        grp = sd['groups'].setdefault(a.group, {'created': today, 'seeds': []})
        have = {s['domain'] for g in sd['groups'].values() for s in g['seeds']}
        new = [d for d in domains if d not in have]
        grp['seeds'] += [{'domain': d, 'added': today, 'note': a.note or ''} for d in new]
        ws.save('seeds.json', sd)
        print(f'group {a.group}: added {len(new)} ({", ".join(new) or "none new"}); {len(grp["seeds"])} seeds in the group')
        if len(grp['seeds']) > LOOKALIKE_MAX:
            print(f'  note: lookalikes are searched {LOOKALIKE_MAX} seeds at a time; keep a group to one kind of company')
    else:
        ad = antis(ws)
        have = {x['domain'] for x in ad['anti_seeds']}
        seeded = {s['domain'] for g in seeds(ws)['groups'].values() for s in g['seeds']}
        clash = [d for d in domains if d in seeded]
        if clash:
            raise Stop(f'Already seeds: {clash}. Remove them there first.')
        new = [d for d in domains if d not in have]
        ad['anti_seeds'] += [{'domain': d, 'added': today, 'note': a.note or ''} for d in new]
        ws.save('anti-seeds.json', ad)
        print(f'anti-seeds: added {len(new)} ({", ".join(new) or "none new"}); {len(ad["anti_seeds"])} in all')
    budget = Budget(ws, a.max_credits, a.dry_run)
    if a.max_credits is None and not a.dry_run:
        print('  not looked up yet: rerun with --max-credits 1 (or run tal.py lookup) to resolve them at Prospeo')
        return
    lookup(ws, budget)
    env = ws.load('envelope.json')
    if env and env.get('filters'):
        print('  re-testing the envelope on all seeds and anti-seeds:')
        res = test_on_controls(ws, budget, 'envelope', env['filters'])
        if res:
            gate_verdict(ws, res)
    footer(ws, budget)


def remove_controls(ws, a, kind):
    ws.require()
    domains = {root_domain(d) for d in a.domains}
    if kind == 'seed':
        sd = seeds(ws)
        gone = []
        for g, grp in sd['groups'].items():
            keep = [s for s in grp['seeds'] if s['domain'] not in domains]
            gone += [(g, s) for s in grp['seeds'] if s['domain'] in domains]
            grp['seeds'] = keep
        sd.setdefault('removed', []).extend({'domain': s['domain'], 'group': g, 'company_id': s.get('company_id'), 'removed': datetime.date.today().isoformat(), 'reason': a.note or ''} for g, s in gone)
        ws.save('seeds.json', sd)
        print(f'removed {len(gone)} seed(s): {[s["domain"] for _, s in gone]}')
        if gone:
            print('  companies found only by lookalikes that included these seeds are marked stale at the next merge; /tal-refresh re-pulls those groups')
    else:
        ad = antis(ws)
        before = len(ad['anti_seeds'])
        ad['anti_seeds'] = [x for x in ad['anti_seeds'] if x['domain'] not in domains]
        ws.save('anti-seeds.json', ad)
        print(f'removed {before - len(ad["anti_seeds"])} anti-seed(s)')


def cmd_list_controls(ws, a):
    ws.require()
    for g, grp in seeds(ws)['groups'].items():
        print(f'seed group {g} ({len(grp["seeds"])}):')
        for s in grp['seeds']:
            print(f"  {s['domain']:28} {s.get('name') or ('UNRESOLVED' if s.get('unresolved') else 'not looked up')}")
    ad = antis(ws)['anti_seeds']
    print(f'anti-seeds ({len(ad)}):')
    for x in ad:
        print(f"  {x['domain']:28} {x.get('name') or ('UNRESOLVED' if x.get('unresolved') else 'not looked up')}  {x.get('note') or ''}")


def cmd_lookup(ws, a):
    ws.require()
    budget = Budget(ws, a.max_credits, a.dry_run)
    lookup(ws, budget)
    footer(ws, budget)


SHOW = ['name', 'domain', 'industry', 'employee_count', 'founded', 'location.state', 'type', 'revenue_range_printed', 'funding.latest_funding_stage', 'funding.latest_funding_date', 'attributes', 'job_postings.active_titles', 'technology.technology_names', 'keywords', 'description_ai']


def cmd_controls(ws, a):
    """Print every resolved seed and anti-seed record side by side, for the model to read."""
    ws.require()
    recs = ws.records()
    for kind, g, e in control_rows(ws):
        r = recs.get(e.get('company_id') or '')
        print(f"\n### {'SEED [' + g + ']' if kind == 'seed' else 'ANTI-SEED'}: {e['domain']}" + (f"  note: {e['note']}" if e.get('note') else ''))
        if not r:
            print('  (no record: not looked up, or not found at Prospeo)')
            continue
        for k in SHOW:
            v = get_path(r, k)
            if k == 'attributes' and isinstance(v, dict):
                v = ', '.join(x for x, on in v.items() if on)
            if k == 'technology.technology_names' and isinstance(v, list):
                v = ', '.join(v[:40]) + (f' (+{len(v) - 40} more)' if len(v) > 40 else '')
            if v not in (None, '', [], {}):
                print(f'  {k}: {text_of(v)[:600]}')


def cmd_test(ws, a):
    """Test a filter (a name in slices.json, 'envelope', or inline JSON) on the seeds and anti-seeds."""
    ws.require()
    budget = Budget(ws, a.max_credits, a.dry_run)
    label, filters = resolve_filters(ws, a.filters)
    res = test_on_controls(ws, budget, label, filters)
    if res and label == 'envelope':
        gate_verdict(ws, res)
    footer(ws, budget)


def resolve_filters(ws, spec):
    if spec == 'envelope':
        env = ws.load('envelope.json')
        if not env:
            raise Stop('No envelope.json yet')
        return 'envelope', env['filters']
    sl = (ws.load('slices.json', {}) or {}).get(spec)
    if sl:
        return spec, {**ws.load('envelope.json', {}).get('filters', {}), **sl['filters']} if sl.get('inside_envelope', True) else sl['filters']
    try:
        return 'inline', json.loads(spec)
    except ValueError:
        raise Stop(f'{spec!r} is not "envelope", a slice name in slices.json, or JSON filters')


def gate_verdict(ws, res):
    cfg = ws.config()
    env = ws.load('envelope.json')
    # Some misses look exactly like fits to every filter (right industry, right
    # size). List them under "rubric_handles" with the reason; they then do not
    # fail the gate, and tal score checks that the rubric keeps them out instead.
    handled = set(env.get('rubric_handles') or [])
    counted = [d for d in res.get('anti_kept_domains', []) if d not in handled]
    ok = res['seeds'] and res['seeds_kept'] / res['seeds'] >= cfg['gate_keep_seeds_min'] and len(counted) <= cfg['gate_keep_anti_max']
    env['tested'] = {'at': NOW(), 'passed': bool(ok), **{k: res[k] for k in ('seeds_kept', 'seeds', 'anti_kept', 'antis')}, 'rubric_handles_kept': sorted(handled & set(res.get('anti_kept_domains', [])))}
    ws.save('envelope.json', env)
    print(f"  envelope gate: {'PASSED' if ok else 'FAILED'} (needs at least {cfg['gate_keep_seeds_min']:.0%} of seeds kept and at most {cfg['gate_keep_anti_max']} anti-seeds"
          + (f"; {len(handled)} anti-seed(s) left to the rubric: {sorted(handled)}" if handled else '') + ')')
    if counted and not ok:
        print('  if no filter can separate an anti-seed it keeps, list its domain under "rubric_handles" in envelope.json and add a rubric exclusion that catches it')
    return ok


def cmd_size(ws, a):
    """Count a search without downloading it: one page, one credit."""
    ws.require()
    budget = Budget(ws, a.max_credits, a.dry_run)
    label, filters = resolve_filters(ws, a.filters)
    r = search(ws, budget, f'size:{label}', filters, 1)
    if r is not None:
        print(f'  {label}: {total(r):,} companies, {pages(r)} pages' + ('  (Prospeo shows at most 25,000 per search; cut it into slices to pull more)' if total(r) >= 25000 else ''))
    footer(ws, budget)


def envelope_or_stop(ws, need_pass=True):
    env = ws.load('envelope.json')
    if not env or not env.get('filters'):
        raise Stop('No envelope.json yet. Write it from the seed analysis, then test it: tal.py test envelope --max-credits 2')
    if need_pass and not (env.get('tested') or {}).get('passed'):
        raise Stop('The envelope has not passed its test on the seeds and anti-seeds. Run: tal.py test envelope --max-credits 2')
    return env


def group_chunks(grp):
    ids = [s['company_id'] for s in grp['seeds'] if s.get('company_id')]
    return [ids[i:i + LOOKALIKE_MAX] for i in range(0, len(ids), LOOKALIKE_MAX)]


def chunk_name(group, oids):
    return f"lookalike:{group}:{hashlib.sha256(','.join(sorted(oids)).encode()).hexdigest()[:8]}"


def cmd_lookalikes(ws, a):
    """Count (default) or --pull lookalikes of each seed group, inside the envelope, ten seeds per search."""
    ws.require()
    env = envelope_or_stop(ws)
    cfg = ws.config()
    budget = Budget(ws, a.max_credits, a.dry_run)
    groups = seeds(ws)['groups']
    names = a.groups or list(groups)
    for g in names:
        if g not in groups:
            raise Stop(f'No seed group {g}')
        for oids in group_chunks(groups[g]):
            name = chunk_name(g, oids)
            filters = {**env['filters'], 'company_lookalike': {'company_oids': oids, 'minimum_tier': cfg['lookalike_tier']}}
            if a.pull:
                ids, complete, n = pull_all(ws, budget, name, filters, cfg['pull_max_age_days'] if a.refresh else None)
                if ids is not None:
                    set_inventory(ws, name, ids, complete, n, {'group': g, 'seed_ids': oids})
                    print(f"  {name}: {len(ids)} of {n} companies stored{'' if complete else ' (incomplete; rerun with more credits)'}")
            else:
                r = search(ws, budget, name, filters, 1)
                if r is not None:
                    keep_records(ws, companies(r))
                    print(f'  {name} ({len(oids)} seeds): {total(r):,} lookalikes inside the envelope, {pages(r)} pages; pulling them all costs up to {max(pages(r) - 1, 0)} more credits')
    footer(ws, budget)


def cmd_pull(ws, a):
    """Download every page of a slice in slices.json (or the envelope) under a credit limit."""
    ws.require()
    env = envelope_or_stop(ws)
    cfg = ws.config()
    budget = Budget(ws, a.max_credits, a.dry_run)
    for spec in a.slices:
        label, filters = resolve_filters(ws, spec)
        ids, complete, n = pull_all(ws, budget, label, filters, cfg['pull_max_age_days'] if a.refresh else None)
        if ids is not None:
            set_inventory(ws, label, ids, complete, n)
            print(f"  {label}: {len(ids)} of {n} companies stored{'' if complete else ' (incomplete; rerun with more credits)'}")
    footer(ws, budget)


def current_chunks(ws):
    return {chunk_name(g, oids) for g, grp in seeds(ws)['groups'].items() for oids in group_chunks(grp)}


def build_sources(ws):
    """company_id -> set of slice tags. A lookalike chunk whose seeds changed is 'stale'."""
    live = current_chunks(ws)
    src, stale = {}, {}
    for name, inv in ws.inventories().items():
        is_stale = name.startswith('lookalike:') and name not in live
        for cid in inv['ids']:
            if is_stale:
                stale.setdefault(cid, set()).add(name)
            else:
                tags = src.setdefault(cid, set())
                tags.add(name)
                if name.startswith('lookalike:'):
                    tags.add('lookalike')
                    tags.add('lookalike:' + name.split(':')[1])
    return src, stale


def cmd_signals(ws, a):
    """Offline: how often each rubric signal and exclusion fires among seeds, anti-seeds and pulled companies.
    Lift = share among seeds / share among everything pulled. Pulls are not a random sample, so read it as an ordering."""
    ws.require()
    rubric = ws.load('rubric.json', {}) or {}
    recs = ws.records()
    src, _ = build_sources(ws)
    seed_ids = [e['company_id'] for k, _, e in control_rows(ws) if k == 'seed' and e.get('company_id')]
    anti_ids = [e['company_id'] for k, _, e in control_rows(ws) if k == 'anti' and e.get('company_id')]
    pool = [cid for cid in src if cid not in set(seed_ids) | set(anti_ids)]
    def share(ids, cond):
        ids = [i for i in ids if i in recs]
        return (sum(test(recs[i], cond, ()) for i in ids) / len(ids)) if ids else None
    fmt = lambda x: '  -  ' if x is None else f'{x:5.0%}'
    print(f'{"signal":48} seeds  anti   pulled  lift   (n = {len(seed_ids)} seeds, {len(anti_ids)} anti-seeds, {len(pool)} pulled)')
    for kind, items in (('signal', rubric.get('signals', [])), ('exclude', rubric.get('exclude', []))):
        for s in items:
            if any(c.get('path') == 'sources' for c in flatten(s['when'])):
                continue
            ss, sa, sp = share(seed_ids, s['when']), share(anti_ids, s['when']), share(pool, s['when'])
            lift = f'{ss / sp:5.1f}x' if ss is not None and sp else '  -  '
            label = (s.get('label') or s.get('reason'))[:44]
            print(f'{kind[0]} {label:46} {fmt(ss)} {fmt(sa)}  {fmt(sp)}  {lift}')


def flatten(cond):
    if 'all' in cond or 'any' in cond:
        return [x for c in cond.get('all', []) + cond.get('any', []) for x in flatten(c)]
    if 'not' in cond:
        return flatten(cond['not'])
    return [cond]


def cmd_score(ws, a):
    """Offline: gates and rubric for every stored company. Writes data/scored.json."""
    ws.require()
    env = envelope_or_stop(ws, need_pass=False)
    rubric = ws.load('rubric.json')
    if not rubric:
        raise Stop('No rubric.json yet. Write it from the seed analysis (see the skill references).')
    cfg = ws.config()
    gates = record_gates(env)
    recs = ws.records()
    src, stale = build_sources(ws)
    seed_ids = {e['company_id']: g for k, g, e in control_rows(ws) if k == 'seed' and e.get('company_id')}
    anti_ids = {e['company_id'] for k, _, e in control_rows(ws) if k == 'anti' and e.get('company_id')}
    rows = []
    for cid in set(src) | set(stale) | set(seed_ids) | anti_ids:
        rec = recs.get(cid)
        if not rec:
            continue
        sources = src.get(cid, set())
        pts, why, failed = score_one(rec, sources, rubric, gates)
        rows.append({'company_id': cid, 'name': rec.get('name'), 'domain': rec.get('domain'), 'industry': rec.get('industry'), 'employees': rec.get('employee_count'), 'founded': rec.get('founded'), 'state': get_path(rec, 'location.state'), 'country': get_path(rec, 'location.country'), 'linkedin_url': rec.get('linkedin_url'),
                     'score': pts, 'tier': tier_of(pts, cfg['tiers']), 'why': why, 'failed': failed, 'sources': sorted(sources), 'stale_only': cid in stale and not sources,
                     'control': 'seed' if cid in seed_ids else 'anti-seed' if cid in anti_ids else None})
    rows.sort(key=lambda r: (-r['score'], r['name'] or ''))
    ws.save('data/scored.json', rows)
    live = [r for r in rows if not r['control']]
    by = {t: sum(1 for r in live if r['tier'] == t and not r['failed']) for t in ('A', 'B', 'C', 'low')}
    print(f"scored {len(live)} companies: {sum(1 for r in live if r['failed'])} fail a gate; passing: A {by['A']}, B {by['B']}, C {by['C']}, low {by['low']}")
    # Seeds and anti-seeds scored the same way, without lookalike points (their
    # own lookalikes would flatter them). If the score cannot tell them apart,
    # it orders companies but does not judge them; the read does that.
    for kind in ('seed', 'anti-seed'):
        ctl = [r for r in rows if r['control'] == kind]
        if ctl:
            no_lk = []
            for r in ctl:
                s, _, failed = score_one(recs[r['company_id']], set(), rubric, gates)
                no_lk.append((r['name'], s if not failed else 'out: ' + '; '.join(failed), r['domain'], bool(failed) or tier_of(s, cfg['tiers']) not in cfg['target_tiers']))
            top = sum(1 for x in no_lk if not x[3])
            print(f"  {kind}s in target tiers without source points: {top} of {len(ctl)}  {[(n, s) for n, s, _, _ in sorted(no_lk, key=lambda x: (isinstance(x[1], str), -x[1] if not isinstance(x[1], str) else 0))]}")
            if kind == 'anti-seed':
                leak = [d for _, _, d, out in no_lk if not out and d in set(env.get('rubric_handles') or [])]
                if leak:
                    print(f'  WARNING: anti-seeds left to the rubric still reach the target tiers: {leak}. Add or fix an exclusion.')


def reads(ws):
    path = ws.p('reads.jsonl')
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out[r['company_id']] = r  # later verdicts win; the file keeps every one
    return out


def cmd_read_queue(ws, a):
    """Write the companies that need a model read into batch files of fixed size."""
    ws.require()
    rows = ws.load('data/scored.json') or []
    cfg = ws.config()
    done = reads(ws)
    todo = [r for r in rows if not r['control'] and not r['failed'] and r['tier'] in cfg['target_tiers'] and r['company_id'] not in done]
    if a.include_reserve:
        todo += [r for r in rows if not r['control'] and not r['failed'] and r['tier'] == 'C' and r['company_id'] not in done]
    if a.limit:
        todo = todo[:a.limit]
    qdir = ws.root / 'data' / 'read-queue'
    qdir.mkdir(parents=True, exist_ok=True)
    for old in qdir.glob('batch-*.json'):
        old.unlink()
    recs = ws.records()
    for b in range(0, len(todo), a.batch):
        items = [{'i': i, 'company_id': r['company_id'], 'name': r['name'], 'domain': r['domain'], 'industry': r['industry'], 'employees': r['employees'], 'state': r['state'], 'score': r['score'], 'tier': r['tier'],
                  'description': (recs[r['company_id']].get('description_ai') or recs[r['company_id']].get('description') or '')[:900], 'keywords': (recs[r['company_id']].get('keywords') or [])[:20]} for i, r in enumerate(todo[b:b + a.batch])]
        (qdir / f'batch-{b // a.batch + 1:03}.json').write_text(json.dumps(items, indent=1, ensure_ascii=False))
    print(f'{len(todo)} companies to read in {-(-len(todo) // a.batch) if todo else 0} batch file(s) under {qdir}')
    if todo:
        print('  for each batch write one line per company to batch-NNN.verdicts.jsonl: {"i": 0, "verdict": "keep|drop|check", "reason": "..."}')
        print('  then: tal.py read-merge')


def cmd_read_merge(ws, a):
    """Validate verdict files against their batches and append them to reads.jsonl. Fails on a missing or repeated index."""
    ws.require()
    qdir = ws.root / 'data' / 'read-queue'
    merged = 0
    for batch in sorted(qdir.glob('batch-*.json')):
        vfile = batch.with_name(batch.stem + '.verdicts.jsonl')
        if not vfile.exists():
            print(f'  {batch.name}: no verdicts yet')
            continue
        items = json.loads(batch.read_text())
        lines = [json.loads(l) for l in vfile.read_text().splitlines() if l.strip()]
        idx = [v['i'] for v in lines]
        missing = sorted(set(range(len(items))) - set(idx))
        dup = sorted({i for i in idx if idx.count(i) > 1})
        bad = [v for v in lines if v.get('verdict') not in ('keep', 'drop', 'check') or not v.get('reason')]
        if missing or dup or bad:
            raise Stop(f'{vfile.name}: missing {missing}, repeated {dup}, invalid {len(bad)}. Fix it; nothing was merged from this batch.')
        with open(ws.p('reads.jsonl'), 'a') as fh:
            for v in lines:
                it = items[v['i']]
                fh.write(json.dumps({'company_id': it['company_id'], 'name': it['name'], 'verdict': v['verdict'], 'reason': v['reason'], 'at': NOW()}) + '\n')
        merged += len(lines)
        batch.unlink()
        vfile.unlink()
    print(f'merged {merged} verdicts into reads.jsonl')


def cmd_merge(ws, a):
    """Build list.json: every company with score, tier, status and the reason. Nothing is deleted."""
    ws.require()
    rows = ws.load('data/scored.json')
    if rows is None:
        raise Stop('Run tal.py score first')
    cfg = ws.config()
    rd = reads(ws)
    prev = {r['company_id']: r for r in (ws.load('list.json') or [])}
    out = []
    for r in rows:
        v = rd.get(r['company_id'])
        if r['control'] == 'seed':
            status, why = 'seed', 'a seed (customer or best prospect)'
        elif r['control'] == 'anti-seed':
            status, why = 'anti-seed', 'an anti-seed'
        elif r['failed']:
            status, why = 'outside', 'fails: ' + '; '.join(r['failed'])
        elif r['stale_only']:
            status, why = 'stale', 'found only by lookalikes of seeds that have since changed; re-pull to confirm'
        elif v and v['verdict'] == 'drop':
            status, why = 'dropped', 'read: ' + v['reason']
        elif v and v['verdict'] == 'check':
            status, why = 'check', 'read: ' + v['reason']
        elif r['tier'] in cfg['target_tiers']:
            if v or not cfg['require_read']:
                status, why = 'target', ('read: ' + v['reason']) if v else f"tier {r['tier']}"
            else:
                status, why = 'to read', f"tier {r['tier']}, not read yet"
        elif r['tier'] == 'C':
            status, why = 'reserve', 'passes every gate, tier C'
        else:
            status, why = 'low score', 'passes every gate, scores below tier C'
        p = prev.get(r['company_id'], {})
        out.append({**{k: r[k] for k in ('company_id', 'name', 'domain', 'industry', 'employees', 'founded', 'state', 'country', 'linkedin_url', 'score', 'tier')},
                    'status': status, 'status_reason': why, 'score_reasons': r['why'], 'sources': [s for s in r['sources'] if s.count(':') < 2],
                    'first_seen': p.get('first_seen') or datetime.date.today().isoformat(), 'status_since': p.get('status_since') if p.get('status') == status else datetime.date.today().isoformat(), 'previous_status': p.get('status') if p.get('status') != status else p.get('previous_status')})
    # A company that was on the list and is no longer found by any search keeps its row.
    have = {r['company_id'] for r in out}
    for cid, p in prev.items():
        if cid not in have:
            out.append({**p, 'status': p['status'] if p['status'] in ('seed', 'anti-seed') else 'not found', 'status_reason': p['status_reason'] if p['status'] in ('seed', 'anti-seed') else 'no current search returns it'})
    order = ['target', 'to read', 'check', 'reserve', 'low score', 'stale', 'dropped', 'outside', 'not found', 'seed', 'anti-seed']
    out.sort(key=lambda r: (order.index(r['status']) if r['status'] in order else 99, -(r['score'] or 0)))
    ws.save('list.json', out)
    changed = sum(1 for r in out if prev and prev.get(r['company_id'], {}).get('status') != r['status'])
    counts = {s: sum(1 for r in out if r['status'] == s) for s in order}
    print('list: ' + ', '.join(f'{s} {n:,}' for s, n in counts.items() if n) + (f' | {changed} changed status since the last merge' if prev else ''))


EXPORT_COLS = ['domain', 'name', 'status', 'status_reason', 'tier', 'score', 'score_reasons', 'industry', 'employees', 'founded', 'state', 'country', 'linkedin_url', 'sources', 'first_seen', 'status_since', 'previous_status', 'company_id']


def cmd_export(ws, a):
    ws.require()
    rows = ws.load('list.json')
    if rows is None:
        raise Stop('Run tal.py merge first')
    if a.status:
        rows = [r for r in rows if r['status'] in a.status]
    seen, uniq = set(), []
    for r in rows:
        key = r.get('domain') or r['company_id']
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    out = pathlib.Path(a.out) if a.out else ws.root / 'out' / ('tal-' + '-'.join(s.replace(' ', '_') for s in a.status) + '.csv' if a.status else 'tal.csv')
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, EXPORT_COLS, extrasaction='ignore')
        w.writeheader()
        for r in uniq:
            w.writerow({**r, 'score_reasons': '; '.join(r.get('score_reasons') or []), 'sources': '; '.join(r.get('sources') or [])})
    print(f'wrote {len(uniq):,} rows to {out}')


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else None


def cmd_inbox(ws, a):
    """Report whether the inbox has new input since the last refresh. Prints JSON."""
    ws.require()
    state = ws.load('data/state.json', {}) or {}
    out = {}
    for name in ('new-customers.csv', 'new-anti-seeds.csv'):
        path = ws.root / 'inbox' / name
        rows = read_csv_domains(path) if path.exists() else []
        out[name] = {'exists': path.exists(), 'rows': len(rows), 'changed_since_last_refresh': file_digest(path) != state.get('inbox', {}).get(name), 'modified': datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='minutes') if path.exists() else None}
    out['last_refresh'] = state.get('last_refresh')
    out['needs_input'] = not any(v['rows'] and v['changed_since_last_refresh'] for k, v in out.items() if k.endswith('.csv'))
    print(json.dumps(out, indent=1))


def cmd_refresh(ws, a):
    """Weekly: take the inbox, look up, re-test, re-pull lookalikes and weekly slices, score, merge, export."""
    ws.require()
    cfg = ws.config()
    budget = Budget(ws, a.max_credits, a.dry_run)
    state = ws.load('data/state.json', {}) or {}
    print('1. inbox')
    sd, ad = seeds(ws), antis(ws)
    have = {s['domain'] for g in sd['groups'].values() for s in g['seeds']} | {x['domain'] for x in ad['anti_seeds']}
    added = []
    for name, kind in (('new-customers.csv', 'seed'), ('new-anti-seeds.csv', 'anti')):
        path = ws.root / 'inbox' / name
        if not path.exists():
            continue
        for r in read_csv_domains(path):
            try:
                d = check_domains([r['domain']])[0]
            except Stop as err:
                print(f'   skipped {r["domain"]} in {name}: {err}')
                continue
            if d in have:
                continue
            have.add(d)
            entry = {'domain': d, 'added': datetime.date.today().isoformat(), 'note': r['note'] or f'from inbox/{name}'}
            if kind == 'seed':
                sd['groups'].setdefault(r['group'] or a.default_group, {'created': datetime.date.today().isoformat(), 'seeds': []})['seeds'].append(entry)
            else:
                ad['anti_seeds'].append(entry)
            added.append((kind, d))
    if not a.dry_run:
        ws.save('seeds.json', sd)
        ws.save('anti-seeds.json', ad)
    print(f"   {len(added)} new: {added or 'none'}")
    print('2. look up new seeds and anti-seeds')
    lookup(ws, budget)
    env = envelope_or_stop(ws, need_pass=False)
    if any(k == 'anti' for k, _ in added) or any(k == 'seed' for k, _ in added):
        print('3. re-test the envelope on the changed seeds and anti-seeds')
        res = test_on_controls(ws, budget, 'envelope', env['filters'])
        if res and not gate_verdict(ws, res):
            print('   the envelope no longer passes: new seeds fall outside it or new anti-seeds pass it. Pulls are skipped until it is revised and re-tested.')
            return finish_refresh(ws, a, budget, state, pulled=False)
    else:
        print('3. no seed changes; envelope test kept')
    print('4. lookalikes for every seed group (stored pages younger than', cfg['pull_max_age_days'], 'days are reused)')
    # Groups with this week's new seeds go first, so a tight credit limit buys
    # the new lookalikes before it finishes an old, partly pulled group.
    new_seeds = {d for k, d in added if k == 'seed'}
    groups = sorted(seeds(ws)['groups'].items(), key=lambda kv: not any(s['domain'] in new_seeds for s in kv[1]['seeds']))
    for g, grp in groups:
        for oids in group_chunks(grp):
            name = chunk_name(g, oids)
            filters = {**env['filters'], 'company_lookalike': {'company_oids': oids, 'minimum_tier': cfg['lookalike_tier']}}
            ids, complete, n = pull_all(ws, budget, name, filters, cfg['pull_max_age_days'])
            if ids is not None:
                set_inventory(ws, name, ids, complete, n, {'group': g, 'seed_ids': oids})
                print(f"   {name}: {len(ids)} of {n}{'' if complete else ' (incomplete)'}")
    print('5. weekly slices')
    for name, sl in (ws.load('slices.json', {}) or {}).items():
        if not sl.get('weekly'):
            continue
        label, filters = resolve_filters(ws, name)
        ids, complete, n = pull_all(ws, budget, label, filters, cfg['pull_max_age_days'])
        if ids is not None:
            set_inventory(ws, label, ids, complete, n)
            print(f"   {name}: {len(ids)} of {n}{'' if complete else ' (incomplete)'}")
    return finish_refresh(ws, a, budget, state, pulled=True)


def finish_refresh(ws, a, budget, state, pulled):
    if a.dry_run:
        footer(ws, budget)
        return
    print('6. score, merge, export')
    cmd_score(ws, a)
    cmd_merge(ws, a)
    cmd_export(ws, argparse.Namespace(status=None, out=None))
    cmd_export(ws, argparse.Namespace(status=['target'], out=None))
    state['last_refresh'] = NOW()
    state['inbox'] = {n: file_digest(ws.root / 'inbox' / n) for n in ('new-customers.csv', 'new-anti-seeds.csv')}
    ws.save('data/state.json', state)
    todo = sum(1 for r in ws.load('list.json') if r['status'] == 'to read')
    print(f'7. {todo} companies wait for a model read' + ('. Run /tal-refresh interactively, or tal.py read-queue, to read them.' if todo else ''))
    footer(ws, budget)


def cmd_status(ws, a):
    ws.require()
    cfg = ws.config()
    sd = seeds(ws)
    print(f'workspace {ws.root}')
    for g, grp in sd['groups'].items():
        n = len(grp['seeds'])
        print(f"  seed group {g}: {n} seeds, {sum(1 for s in grp['seeds'] if s.get('company_id'))} resolved, {len(group_chunks(grp))} lookalike search(es)")
    print(f"  anti-seeds: {len(antis(ws)['anti_seeds'])}")
    env = ws.load('envelope.json')
    print('  envelope: ' + ('none yet' if not env else json.dumps(env.get('tested') or 'not tested')))
    lst = ws.load('list.json')
    if lst:
        counts = {}
        for r in lst:
            counts[r['status']] = counts.get(r['status'], 0) + 1
        print('  list: ' + ', '.join(f'{k} {v:,}' for k, v in counts.items()))
    st = ws.load('data/state.json', {}) or {}
    print(f"  last refresh: {st.get('last_refresh') or 'never'}")
    rc = ws.receipts()
    print(f"  credits: {ws.spent()} spent of cap {cfg['credit_cap']} across {len(rc)} calls")


def footer(ws, budget):
    if budget.dry:
        print(f'dry run: nothing called. Paid pages it would have requested: {budget.would} (more may follow once page counts are known)')
    else:
        print(f'credits this command: {budget.used} | workspace: {ws.spent()} of cap {ws.config()["credit_cap"]}')


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(prog='tal.py', description=__doc__.split('\n\n')[0])
    ap.add_argument('--dir', default=os.environ.get('TAL_DIR', 'tal'), help='workspace directory (default ./tal or $TAL_DIR)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def paid(p):
        p.add_argument('--max-credits', type=int, help='most credits this command may spend; without it nothing paid is called')
        p.add_argument('--dry-run', action='store_true', help='spend nothing; say what would be called')
        return p

    p = sub.add_parser('init', help='create the workspace')
    p.add_argument('--sample', help='load a shipped example, e.g. accounting-firms')
    p.add_argument('--project', default='.', help='project root for AGENTS.md, CLAUDE.md and .gitignore (default .)')
    p.add_argument('--no-agent-files', action='store_true', help='do not touch AGENTS.md, CLAUDE.md or .gitignore')
    for kind in ('seed', 'antiseed'):
        sp = sub.add_parser(kind, help=f'add, remove or list {kind}s').add_subparsers(dest='action', required=True)
        p = paid(sp.add_parser('add'))
        if kind == 'seed':
            p.add_argument('group', help='seed group: one kind of company, e.g. core')
        p.add_argument('domains', nargs='*')
        p.add_argument('--csv', help='CSV with a domain column')
        p.add_argument('--note', help='why (kept with the entry)')
        p = sp.add_parser('remove')
        p.add_argument('domains', nargs='+')
        p.add_argument('--note', help='why')
        sp.add_parser('list')
    paid(sub.add_parser('lookup', help='resolve seeds and anti-seeds at Prospeo (1 credit per 25 domains)'))
    sub.add_parser('controls', help='print seed and anti-seed records side by side (offline)')
    p = paid(sub.add_parser('test', help='test filters on the seeds and anti-seeds'))
    p.add_argument('filters', help='"envelope", a slice name, or inline JSON filters')
    p = paid(sub.add_parser('size', help='count a search: one page, one credit'))
    p.add_argument('filters', help='"envelope", a slice name, or inline JSON filters')
    p = paid(sub.add_parser('lookalikes', help='count or pull lookalikes of seed groups'))
    p.add_argument('groups', nargs='*')
    p.add_argument('--pull', action='store_true', help='download every page (default: count only)')
    p.add_argument('--refresh', action='store_true', help='re-fetch stored pages older than pull_max_age_days')
    p = paid(sub.add_parser('pull', help='download a slice from slices.json'))
    p.add_argument('slices', nargs='+')
    p.add_argument('--refresh', action='store_true')
    sub.add_parser('signals', help='how often each rubric signal fires on seeds, anti-seeds and pulls (offline)')
    sub.add_parser('score', help='apply gates and rubric to every stored company (offline)')
    p = sub.add_parser('read-queue', help='write batches of companies for the model read')
    p.add_argument('--batch', type=int, default=50)
    p.add_argument('--limit', type=int)
    p.add_argument('--include-reserve', action='store_true')
    sub.add_parser('read-merge', help='validate and merge verdict files')
    sub.add_parser('merge', help='build list.json with a status for every company')
    p = sub.add_parser('export', help='write a CSV')
    p.add_argument('--status', nargs='*', help='only these statuses, e.g. target')
    p.add_argument('--out')
    sub.add_parser('inbox', help='is there new input since the last refresh? (JSON)')
    p = paid(sub.add_parser('refresh', help='weekly: inbox, look up, re-test, pull, score, merge, export'))
    p.add_argument('--default-group', default='new-customers', help='seed group for inbox rows with no group')
    sub.add_parser('status')

    a = ap.parse_args(argv)
    ws = WS(a.dir)
    if a.cmd in ('seed', 'antiseed'):
        kind = 'seed' if a.cmd == 'seed' else 'anti'
        return {'add': lambda: add_controls(ws, a, kind), 'remove': lambda: remove_controls(ws, a, kind), 'list': lambda: cmd_list_controls(ws, a)}[a.action]()
    return {'init': cmd_init, 'lookup': cmd_lookup, 'controls': cmd_controls, 'test': cmd_test, 'size': cmd_size, 'lookalikes': cmd_lookalikes, 'pull': cmd_pull, 'signals': cmd_signals, 'score': cmd_score,
            'read-queue': cmd_read_queue, 'read-merge': cmd_read_merge, 'merge': cmd_merge, 'export': cmd_export, 'inbox': cmd_inbox, 'refresh': cmd_refresh, 'status': cmd_status}[a.cmd](ws, a)


if __name__ == '__main__':
    main()
