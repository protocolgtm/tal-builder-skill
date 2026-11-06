"""Offline contract tests for tal.py. A fake Prospeo answers from synthetic
records, so nothing here touches the network or spends credits.

  python3 -m unittest discover -s tests -v
"""
import contextlib, io, json, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / '.claude/skills/tal-builder/scripts'))
import tal  # noqa: E402


def firm(i, domain, employees=40, industry='Accounting', state='Ohio', country='United States', founded=1995, desc='CPA firm serving small businesses', like=(), tech=()):
    return {'company_id': f'id{i:04}', 'name': domain.split('.')[0].title(), 'domain': domain, 'employee_count': employees, 'industry': industry,
            'location': {'country': country, 'state': state}, 'founded': founded, 'description_ai': desc, 'keywords': [], '_like': list(like),
            'technology': {'technology_names': list(tech)}, 'attributes': {'has_pricing': False}}


def universe():
    rows = [
        firm(1, 'seed-one.test', like=()), firm(2, 'seed-two.test', employees=60), firm(3, 'seed-three.test', employees=8),
        firm(4, 'bigfour.test', employees=50000), firm(5, 'payroll.test', industry='Software Development', employees=150, desc='payroll software'),
    ]
    # 60 lookalikes of the seeds, some outside the envelope, some with QuickBooks
    for i in range(60):
        rows.append(firm(100 + i, f'look{i}.test', employees=20 + i * 3, like=['id0001', 'id0002'], tech=['QuickBooks'] if i % 3 == 0 else [],
                         country='Canada' if i == 7 else 'United States', desc='staffing agency' if i == 9 else 'CPA firm serving small businesses'))
    return {r['company_id']: r for r in rows}


class FakeProspeo:
    def __init__(self):
        self.db = universe()
        self.calls = 0

    def __call__(self, endpoint, payload, key):
        assert key == 'test-key'
        self.calls += 1
        f, page = payload['filters'], payload.get('page', 1)
        rows = list(self.db.values())
        web = ((f.get('company') or {}).get('websites') or {}).get('include')
        if web:
            rows = [r for r in rows if r['domain'] in web]
        loc = (f.get('company_location_search') or {}).get('include')
        if loc:
            rows = [r for r in rows if r['location']['country'] in loc]
        hc = f.get('company_headcount_custom')
        if hc:
            rows = [r for r in rows if hc['min'] <= r['employee_count'] <= hc['max']]
        ind = (f.get('company_industry') or {}).get('include')
        if ind:
            rows = [r for r in rows if r['industry'] in ind]
        lk = f.get('company_lookalike')
        if lk:
            rows = [r for r in rows if set(r['_like']) & set(lk['company_oids'])]
        if not rows:
            return {'error': True, 'error_code': 'NO_RESULTS'}
        n = -(-len(rows) // 25)
        chunk = rows[(page - 1) * 25: page * 25]
        return {'error': False, 'free': False, 'results': [{'company': {k: v for k, v in r.items() if k != '_like'}} for r in chunk],
                'pagination': {'current_page': page, 'per_page': 25, 'total_page': n, 'total_count': len(rows)}}


ENVELOPE = {'filters': {'company_location_search': {'include': ['United States']}, 'company_headcount_custom': {'min': 5, 'max': 200}, 'company_industry': {'include': ['Accounting']}}}
RUBRIC = {
    'exclude': [{'reason': 'staffing firm', 'when': {'path': 'description_ai', 'op': 'regex', 'value': 'staffing'}}],
    'signals': [
        {'label': 'uses QuickBooks', 'points': 30, 'when': {'path': 'technology.technology_names', 'op': 'contains_any', 'value': ['QuickBooks']}},
        {'label': 'lookalike of a seed', 'points': 20, 'when': {'path': 'sources', 'op': 'contains_any', 'value': ['lookalike']}},
        {'label': '20 to 100 staff', 'points': 10, 'when': {'path': 'employee_count', 'op': 'between', 'value': [20, 100]}},
    ],
}


class TalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name) / 'tal'
        self.fake = FakeProspeo()
        tal.TRANSPORT = self.fake
        tal.os.environ['PROSPEO_API_KEY'] = 'test-key'
        self.tal('init', '--project', self.tmp.name)
        cfg = json.loads((self.dir / 'config.json').read_text())
        cfg['credit_cap'] = 50
        (self.dir / 'config.json').write_text(json.dumps(cfg))

    def tearDown(self):
        self.tmp.cleanup()

    def tal(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            tal.main(['--dir', str(self.dir), *args])
        return buf.getvalue()

    def seeded(self):
        self.tal('seed', 'add', 'core', 'seed-one.test', 'seed-two.test', 'https://www.seed-three.test/about')
        self.tal('antiseed', 'add', 'bigfour.test', 'payroll.test', 'nowhere.test')
        self.tal('lookup', '--max-credits', '1')
        (self.dir / 'envelope.json').write_text(json.dumps(ENVELOPE))
        (self.dir / 'rubric.json').write_text(json.dumps(RUBRIC))

    def test_paid_commands_spend_nothing_without_max_credits_or_on_dry_run(self):
        self.tal('seed', 'add', 'core', 'seed-one.test')
        self.tal('lookup', '--dry-run')
        out = self.tal('lookup')
        self.assertIn('given no --max-credits', out)
        self.assertEqual(self.fake.calls, 0)

    def test_subdomains_are_refused(self):
        with self.assertRaises(SystemExit):
            self.tal('seed', 'add', 'core', 'app.seed-one.test')

    def test_lookup_resolves_by_id_and_flags_unknown(self):
        self.seeded()
        anti = json.loads((self.dir / 'anti-seeds.json').read_text())['anti_seeds']
        self.assertTrue(next(a for a in anti if a['domain'] == 'nowhere.test')['unresolved'])
        s = json.loads((self.dir / 'seeds.json').read_text())['groups']['core']['seeds']
        self.assertEqual({x['company_id'] for x in s}, {'id0001', 'id0002', 'id0003'})

    def test_envelope_gate(self):
        self.seeded()
        out = self.tal('test', 'envelope', '--max-credits', '1')
        self.assertIn('keeps 3 of 3 seeds, 0 of 2 anti-seeds', out)
        self.assertTrue(json.loads((self.dir / 'envelope.json').read_text())['tested']['passed'])
        # A tighter envelope drops a seed and fails the 80% gate
        env = json.loads((self.dir / 'envelope.json').read_text())
        env['filters']['company_headcount_custom'] = {'min': 11, 'max': 200}
        (self.dir / 'envelope.json').write_text(json.dumps(env))
        out = self.tal('test', 'envelope', '--max-credits', '1')
        self.assertIn('FAILED', out)
        with self.assertRaises(SystemExit):
            self.tal('lookalikes', '--max-credits', '5')

    def test_anti_seed_no_filter_can_separate_is_left_to_the_rubric(self):
        self.seeded()
        self.tal('antiseed', 'add', 'look9.test')  # a staffing agency inside the envelope
        self.tal('lookup', '--max-credits', '1')
        self.assertIn('FAILED', self.tal('test', 'envelope', '--max-credits', '1'))
        env = json.loads((self.dir / 'envelope.json').read_text())
        env['rubric_handles'] = ['look9.test']
        (self.dir / 'envelope.json').write_text(json.dumps(env))
        self.assertIn('PASSED', self.tal('test', 'envelope', '--max-credits', '1'))
        self.tal('lookalikes', '--pull', '--max-credits', '5')
        self.assertNotIn('WARNING', self.tal('score'))
        # Without the exclusion that catches it, score warns
        (self.dir / 'rubric.json').write_text(json.dumps({**RUBRIC, 'exclude': []}))
        self.assertIn('WARNING', self.tal('score'))

    def test_cap_stops_pull_midway_and_cached_pages_are_free(self):
        self.seeded()
        self.tal('test', 'envelope', '--max-credits', '1')
        out = self.tal('lookalikes', 'core', '--pull', '--max-credits', '2')
        self.assertIn('incomplete', out)
        calls = self.fake.calls
        self.tal('lookalikes', 'core', '--pull', '--max-credits', '5')
        inv = json.loads((self.dir / 'data/inventories.json').read_text())
        self.assertTrue(all(v['complete'] for v in inv.values()))
        self.assertEqual(self.fake.calls - calls, 1)  # only the missing third page was fetched

    def test_workspace_cap(self):
        self.seeded()
        cfg = json.loads((self.dir / 'config.json').read_text())
        cfg['credit_cap'] = 1
        (self.dir / 'config.json').write_text(json.dumps(cfg))
        out = self.tal('size', 'envelope', '--max-credits', '5')
        self.assertIn('workspace credit cap of 1 reached', out)

    def test_score_merge_read_export(self):
        self.seeded()
        self.tal('test', 'envelope', '--max-credits', '1')
        self.tal('lookalikes', 'core', '--pull', '--max-credits', '5')
        self.tal('score')
        rows = {r['domain']: r for r in json.loads((self.dir / 'data/scored.json').read_text())}
        self.assertIn('staffing firm', rows['look9.test']['failed'])
        self.assertNotIn('look7.test', rows)  # Canadian: the envelope search never returned it
        gates = tal.record_gates(ENVELOPE)
        self.assertEqual([n for n, fn in gates if not fn(firm(7, 'x.test', country='Canada'))], ['location'])
        self.assertEqual([n for n, fn in gates if not fn(firm(7, 'x.test', employees=500))], ['5 to 200 employees'])
        self.assertEqual(rows['look0.test']['score'], 60)
        self.tal('merge')
        lst = {r['domain']: r for r in json.loads((self.dir / 'list.json').read_text())}
        self.assertEqual(lst['look0.test']['status'], 'to read')
        self.assertEqual(lst['seed-one.test']['status'], 'seed')
        self.assertEqual(lst['bigfour.test']['status'], 'anti-seed')
        # model read: a verdict file with a missing index is refused
        self.tal('read-queue', '--batch', '100')
        batch = json.loads((self.dir / 'data/read-queue/batch-001.json').read_text())
        vfile = self.dir / 'data/read-queue/batch-001.verdicts.jsonl'
        vfile.write_text('\n'.join(json.dumps({'i': it['i'], 'verdict': 'keep', 'reason': 'fits'}) for it in batch[1:]))
        with self.assertRaises(SystemExit):
            self.tal('read-merge')
        lines = [{'i': it['i'], 'verdict': 'drop' if it['domain'] == 'look0.test' else 'keep', 'reason': 'owned by a national firm' if it['domain'] == 'look0.test' else 'independent CPA firm'} for it in batch]
        vfile.write_text('\n'.join(json.dumps(x) for x in lines))
        self.tal('read-merge')
        self.tal('merge')
        lst = {r['domain']: r for r in json.loads((self.dir / 'list.json').read_text())}
        self.assertEqual(lst['look0.test']['status'], 'dropped')
        self.assertEqual(lst['look3.test']['status'], 'target')
        out = self.tal('export', '--status', 'target')
        csv_text = (self.dir / 'out/tal-target.csv').read_text()
        self.assertIn('look3.test', csv_text)
        self.assertNotIn('look0.test', csv_text)
        self.assertNotIn('seed-one.test', csv_text)

    def test_removed_seed_marks_its_lookalikes_stale_never_deletes(self):
        self.seeded()
        self.tal('test', 'envelope', '--max-credits', '1')
        self.tal('lookalikes', 'core', '--pull', '--max-credits', '5')
        self.tal('score'); self.tal('merge')
        self.tal('seed', 'remove', 'seed-two.test')
        self.tal('score'); self.tal('merge')
        lst = {r['domain']: r for r in json.loads((self.dir / 'list.json').read_text())}
        self.assertEqual(lst['look3.test']['status'], 'stale')
        self.assertEqual(lst['look3.test']['previous_status'], 'to read')

    def test_refresh_takes_inbox_and_reports_needs_input(self):
        self.seeded()
        self.tal('test', 'envelope', '--max-credits', '1')
        self.assertTrue(json.loads(self.tal('inbox'))['needs_input'])
        (self.dir / 'inbox/new-customers.csv').write_text('domain,group,note\nlook3.test,,closed last week\n')
        self.assertFalse(json.loads(self.tal('inbox'))['needs_input'])
        out = self.tal('refresh', '--max-credits', '10')
        self.assertIn("('seed', 'look3.test')", out)
        groups = json.loads((self.dir / 'seeds.json').read_text())['groups']
        self.assertEqual(groups['new-customers']['seeds'][0]['company_id'], 'id0103')
        self.assertTrue((self.dir / 'out/tal.csv').exists())
        self.assertTrue(json.loads(self.tal('inbox'))['needs_input'])  # same file again is not new input

    def test_key_from_env_file_is_never_printed(self):
        del tal.os.environ['PROSPEO_API_KEY']
        (self.dir / '.env').write_text('PROSPEO_API_KEY="test-key"\n')
        self.tal('seed', 'add', 'core', 'seed-one.test')
        out = self.tal('lookup', '--max-credits', '1')
        self.assertNotIn('test-key', out + ''.join((self.dir / 'data').rglob('*').__class__.__name__))
        for f in (self.dir / 'data').rglob('*'):
            if f.is_file():
                self.assertNotIn('test-key', f.read_text())
        tal.os.environ['PROSPEO_API_KEY'] = 'test-key'

    def test_init_writes_agent_files_once_and_keeps_existing_text(self):
        root = pathlib.Path(self.tmp.name)
        self.assertIn('new-customers.csv', (root / 'AGENTS.md').read_text())
        self.assertEqual((root / 'CLAUDE.md').read_text(), '@AGENTS.md\n')
        self.assertIn('.env', (root / '.gitignore').read_text())
        (root / 'AGENTS.md').write_text('# My project\n\nKeep this.\n\n' + (root / 'AGENTS.md').read_text())
        self.tal('init', '--project', self.tmp.name)
        text = (root / 'AGENTS.md').read_text()
        self.assertIn('Keep this.', text)
        self.assertEqual(text.count('tal-builder:start'), 1)

    def test_provider_error_stops(self):
        self.seeded()
        tal.TRANSPORT = lambda e, p, k: {'error': True, 'error_code': 'INVALID_FILTERS', 'filter_error': 'bad'}
        with self.assertRaises(SystemExit):
            self.tal('size', '{"company_industry": {"include": ["Nope"]}}', '--max-credits', '1')


if __name__ == '__main__':
    unittest.main()
