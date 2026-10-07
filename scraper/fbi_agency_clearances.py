#!/usr/bin/env python3
"""Collect monthly FBI offenses/clearances and optional arrests. Standard library only."""
from __future__ import annotations
import argparse, concurrent.futures, csv, datetime as dt, hashlib, json, os
from pathlib import Path
import threading, time, urllib.error, urllib.parse, urllib.request

# PASTE YOUR API KEY BETWEEN THE QUOTES, OR SET FBI_API_KEY.
# Do not commit a pasted key to GitHub.
API_KEY = "WfBehMNXN56fr9qJv6gGtyTuJSddSAeeY4PgfEkK"
BASE_URL = "https://cde.ucr.cjis.gov/LATEST"
ROOT = Path(__file__).resolve().parents[1]
# Separate code systems: NIBRS 240 = MVT; arrest 90 = MVT.
OFFENSES = [
    ("MVT", "Motor vehicle theft", "240", "90", "primary"),
    ("LAR", "Larceny theft", "23A|23B|23C|23D|23E|23F|23G|23H", "70", "secondary_vehicle_subtypes_combined"),
    ("ROB", "Robbery", "120", "30", "secondary"),
    ("BUR", "Burglary", "220", "60", "secondary"),
    ("ASS", "Aggravated assault", "13A", "50", "exploratory"),
    ("HOM", "Murder and nonnegligent homicide", "09A", "11", "exploratory"),
    ("ARS", "Arson", "200", "110", "exploratory"),
]
EXTRA_ARRESTS = [("210", "Stolen property", "280"), ("220", "Vandalism", "290"),
                 ("230", "Weapons violations", "520"), ("260", "Driving under the influence", "90D")]
US_STATES = "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or sorted({k for r in rows for k in r})
    tmp = path.with_suffix('.csv.tmp')
    with tmp.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    tmp.replace(path)


class Client:
    def __init__(self, out, key, base, timeout, delay, retries, refresh):
        self.out, self.key, self.base = out, key, base.rstrip('/')
        self.timeout, self.delay, self.retries, self.refresh = timeout, delay, retries, refresh
        self.lock, self.next_request = threading.Lock(), 0.0
    def get(self, endpoint, params, cache):
        path = self.out / 'raw' / cache
        url = self.base + '/' + endpoint + ('?' + urllib.parse.urlencode(params) if params else '')
        if path.exists() and not self.refresh:
            return json.loads(path.read_text()), url, 'cached'
        headers = {'Accept': 'application/json', 'User-Agent': 'FlockResearch-FBICollector/1.0'}
        if self.key: headers['X-Api-Key'] = self.key
        for attempt in range(self.retries + 1):
            with self.lock:
                wait = max(0, self.next_request - time.monotonic())
                self.next_request = time.monotonic() + wait + self.delay
            if wait: time.sleep(wait)
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=self.timeout) as response:
                    payload = json.load(response)
                if not isinstance(payload, (dict, list)): raise ValueError('Unexpected JSON payload')
                save_json(path, payload)
                return payload, url, 'downloaded'
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise RuntimeError(f'HTTP {e.code}') from None
                time.sleep(min(30, max(2 ** attempt, float(e.headers.get('Retry-After', '0')))))
            except (OSError, ValueError) as e:
                if attempt == self.retries: raise RuntimeError(type(e).__name__) from None
                time.sleep(min(15, 2 ** attempt))


def flatten_agencies(payload, state):
    records = payload if isinstance(payload, list) else [r for group in payload.values() if isinstance(group, list) for r in group]
    unique = {}
    for r in records:
        ori = r.get('ori', '')
        if len(ori) != 9 or r.get('state_abbr', state) != state: continue
        if ori in unique and unique[ori].get('agency_name') != r.get('agency_name'):
            raise ValueError(f'Conflicting names for ORI {ori}')
        unique[ori] = dict(r, state_abbr=state)
    if not unique: raise ValueError(f'No agencies returned for {state}')
    return list(unique.values())


def agency_series(series, agency, suffix):
    """Never pick state/national comparison series or add multiple series together."""
    if not isinstance(series, dict): return {}
    exact = agency['agency_name'] + ' ' + suffix
    if exact in series: return series[exact]
    comparison_names = {agency.get('state_name', ''), 'United States', 'Illinois'}
    matches = [(k, v) for k, v in series.items() if k.endswith(' ' + suffix) and k[:-len(suffix)-1] not in comparison_names]
    if len(matches) == 1: return matches[0][1]
    if matches: raise ValueError(f'Ambiguous agency {suffix} series')
    if series: raise ValueError(f'No agency {suffix} series; refusing comparison data')
    return {}


def parse_counts(payload, agency):
    block = payload.get('offenses')
    if not isinstance(block, dict): raise ValueError('Missing offenses object')
    counts = block.get('actuals', block.get('counts'))
    if not isinstance(counts, dict): raise ValueError('Missing count series; will not substitute rates')
    return agency_series(counts, agency, 'Offenses'), agency_series(counts, agency, 'Clearances')


def months(start, end):
    return [f'{m:02d}-{y}' for y in range(start, end + 1) for m in range(1, 13)]


def number(value):
    if value is None: return ''
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0: raise ValueError('Invalid count')
    if int(value) != value: raise ValueError('Noninteger count')
    return int(value)


def normalize(payload, agency, code, label, nibrs, kind, periods, url, retrieved):
    if kind == 'summarized':
        known, cleared = parse_counts(payload, agency)
    else:
        block = payload.get('arrests', payload)
        series = block.get('actuals', block.get('counts', {})) if isinstance(block, dict) else {}
        if not isinstance(series, dict) or not any(k in block for k in ('actuals', 'counts')): raise ValueError('Missing arrest count series')
        known = agency_series(series, agency, 'Arrests'); cleared = {}
        if not known and series: raise ValueError('No agency arrest series identified')
    rows = []
    for period in periods:
        m, y = period.split('-'); month = f'{y}-{m}'
        a, c = number(known.get(period)), number(cleared.get(period))
        population = payload.get('populations', {}).get('population', {}).get(agency['agency_name'], {}).get(period)
        participating = payload.get('populations', {}).get('participated_population', {}).get(agency['agency_name'], {}).get(period)
        row = {'ori': agency['ori'], 'agency_name': agency['agency_name'], 'state_abbr': agency['state_abbr'],
               'agency_type': agency.get('agency_type_name', ''), 'county': agency.get('counties', agency.get('county_name', '')),
               'year_month': month, 'year': int(y), 'month': int(m), 'api_offense_code': code,
               'offense_name': label, 'nibrs_codes': nibrs, 'population': population if population is not None else '',
               'participated_population': participating if participating is not None else '',
               'nibrs_start_date': agency.get('nibrs_start_date', ''),
               'before_listed_nibrs_start': bool(agency.get('nibrs_start_date') and month < agency['nibrs_start_date'][:7]),
               'source_url': url, 'retrieved_at_utc': retrieved,
               'source_max_data_date': json.dumps(payload.get('cde_properties', {}).get('max_data_date', {}))}
        if kind == 'summarized':
            row.update(offenses=a, clearances=c,
                       clearance_ratio=c/a if a != '' and a > 0 and c != '' else '',
                       clearances_exceed_offenses=a != '' and c != '' and c > a,
                       data_status='available' if a != '' and c != '' else 'partial' if a != '' or c != '' else 'missing')
        else: row.update(arrests=a, data_status='available' if a != '' else 'missing')
        rows.append(row)
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--states', nargs='+', default=['IL'], help='IL, multiple state abbreviations, or ALL')
    p.add_argument('--start-year', type=int, default=2021); p.add_argument('--end-year', type=int, default=2025)
    p.add_argument('--offenses', nargs='+', default=[o[0] for o in OFFENSES], choices=[o[0] for o in OFFENSES])
    p.add_argument('--include-arrests', action='store_true'); p.add_argument('--ori', nargs='+')
    p.add_argument('--limit-agencies', type=int); p.add_argument('--workers', type=int, default=6)
    p.add_argument('--delay', type=float, default=0.2); p.add_argument('--timeout', type=float, default=45)
    p.add_argument('--retries', type=int, default=2); p.add_argument('--refresh', action='store_true')
    p.add_argument('--base-url', default=BASE_URL); p.add_argument('--out-dir', type=Path, default=ROOT/'data/fbi_clearances')
    args = p.parse_args()
    if args.start_year > args.end_year or args.workers < 1 or args.delay < 0: p.error('Invalid date range/workers/delay')
    states = US_STATES if args.states == ['ALL'] else [s.upper() for s in args.states]
    if any(s not in US_STATES for s in states): p.error('Unknown state abbreviation')
    client = Client(args.out_dir, os.getenv('FBI_API_KEY') or API_KEY, args.base_url, args.timeout, args.delay, args.retries, args.refresh)
    agencies = []
    for state in states:
        payload, _, _ = client.get(f'agency/byStateAbbr/{state}', {}, f'lookups/agencies_{state}.json')
        agencies.extend(flatten_agencies(payload, state))
    agencies.sort(key=lambda a: (a['agency_name'] != 'Chicago Police Department', a['ori']))
    write_csv(args.out_dir/'agency_directory.csv', agencies)
    if args.ori:
        missing = set(args.ori) - {a['ori'] for a in agencies}
        if missing: p.error(f'ORI not in selected state directory: {sorted(missing)}')
        agencies = [a for a in agencies if a['ori'] in args.ori]
    if args.limit_agencies: agencies = agencies[:args.limit_agencies]
    selected = [o for o in OFFENSES if o[0] in args.offenses]
    write_csv(args.out_dir/'offense_crosswalk.csv', [dict(zip(['summary_code','offense_name','nibrs_codes','arrest_code','research_priority'], o)) for o in OFFENSES])
    jobs = [(a, 'summarized', o[0], o[1], o[2]) for a in agencies for o in selected]
    if args.include_arrests:
        jobs += [(a, 'arrest', o[3], o[1], o[2]) for a in agencies for o in selected]
        jobs += [(a, 'arrest', code, label, nibrs) for a in agencies for code, label, nibrs in EXTRA_ARRESTS]
    periods = months(args.start_year, args.end_year)
    print(f'{len(agencies)} agencies; {len(jobs)} requests; {len(periods)} months per series', flush=True)
    def collect(job):
        agency, kind, code, label, nibrs = job
        cache = f'{kind}/{agency["ori"]}_{code}_{args.start_year}_{args.end_year}.json'
        try:
            payload, url, origin = client.get(f'{kind}/agency/{agency["ori"]}/{code}', {'from':periods[0], 'to':periods[-1], 'type':'counts'}, cache)
            timestamp = dt.datetime.fromtimestamp((args.out_dir/'raw'/cache).stat().st_mtime, dt.timezone.utc).isoformat()
            rows = normalize(payload, agency, code, label, nibrs, kind, periods, url, timestamp)
            return job, rows, {'ori':agency['ori'],'kind':kind,'code':code,'status':origin,'error':'','raw_file':cache,
                               'sha256':hashlib.sha256((args.out_dir/'raw'/cache).read_bytes()).hexdigest()}
        except Exception as e:
            return job, [], {'ori':agency['ori'],'kind':kind,'code':code,'status':'failed','error':str(e),'raw_file':cache,'sha256':''}
    clearance_rows, arrest_rows, manifest = [], [], []
    def checkpoint():
        for kind, rows in [('clearances',clearance_rows), ('arrests',arrest_rows)]:
            if rows: write_csv(args.out_dir/f'{kind}_monthly.csv', sorted(rows, key=lambda r:(r['ori'],r['api_offense_code'],r['year_month'])))
        write_csv(args.out_dir/'request_manifest.csv', manifest)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        for i, (job, rows, record) in enumerate(executor.map(collect, jobs), 1):
            (clearance_rows if job[1]=='summarized' else arrest_rows).extend(rows); manifest.append(record)
            if i % 50 == 0 or i == len(jobs):
                checkpoint(); print(f'{i}/{len(jobs)} processed; failures={sum(r["status"]=="failed" for r in manifest)}',flush=True)
    coverage = []
    indexed = {}
    for row in clearance_rows:
        indexed.setdefault((row['ori'], row['api_offense_code']), []).append(row)
    for agency in agencies:
        for o in selected:
            rr = indexed.get((agency['ori'], o[0]), [])
            coverage.append({'ori':agency['ori'],'agency_name':agency['agency_name'],'offense':o[0],
                             'expected_months':len(periods),'returned_panel_months':len(rr),
                             'available_months':sum(r['data_status']=='available' for r in rr),
                             'partial_months':sum(r['data_status']=='partial' for r in rr),
                             'missing_months':sum(r['data_status']=='missing' for r in rr),
                             'request_failed':not rr})
    write_csv(args.out_dir/'coverage_by_agency_offense.csv', coverage)
    summary = {'states':states,'start_year':args.start_year,'end_year':args.end_year,'agency_count':len(agencies),
               'requests':len(jobs),'failed_requests':sum(r['status']=='failed' for r in manifest),
               'clearance_panel_rows':len(clearance_rows),'arrest_panel_rows':len(arrest_rows),
               'completed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
               'notes':['Missing values are not zero. Counts are reported, not imputed.',
                        'Clearances combine arrest and exceptional means; they are not arrest counts.',
                        'Monthly clearance ratio is not a cohort probability and can exceed 1.',
                        'Agency directory is current, not a complete historical ORI universe.',
                        'Before NIBRS start is a caution flag, not proof of nonreporting.']}
    save_json(args.out_dir/'run_metadata.json', summary); print(json.dumps(summary,indent=2))
    return 1 if summary['failed_requests'] else 0

if __name__ == '__main__': raise SystemExit(main())
