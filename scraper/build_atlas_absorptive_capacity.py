#!/usr/bin/env python3
"""Auditable, conservative technology-adoption proxy from Atlas CSV summaries.
Run: python scraper/build_atlas_absorptive_capacity.py
No external packages. Main index = distinct eligible adopted technology types.
"""
from __future__ import annotations
import argparse, collections, csv, datetime as dt, difflib, hashlib, json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT/'data/atlas_full/atlas_full.csv'
DOWNLOAD_URL = 'https://atlasofsurveillance.org/download.csv'
# Aliases identify a technology; they do not establish adoption by themselves.
TECHNOLOGIES = {
 'alpr': ('Automated license plate readers', r'\b(?:ALPRs?|ANPRs?|LPRs?|(?:automatic|automated)\s+(?:license\s+)?plate\s+(?:readers?|recognition|scanners?)|license[- ]plate\s+(?:readers?|recognition|scanners?))\b'),
 'gunshot_detection': ('Gunshot detection', r'\b(?:ShotSpotter|gun[- ]?shot\s+(?:detection|detectors?|sensors?)|acoustic\s+gunfire\s+detection|Flock\s+Raven)\b'),
 'body_worn_cameras': ('Body worn cameras', r'\b(?:body[- ](?:worn|mounted)\s+cameras?|body\s*cams?|BWCs?)\b'),
 'drones': ('Drones', r'\b(?:drones?|unmanned\s+(?:aerial|aircraft)\s+(?:systems?|vehicles?)|UAVs?|UAS)\b'),
 'facial_recognition': ('Facial recognition', r'\b(?:fac(?:e|ial)\s+recognition|Clearview\s+AI)\b'),
 'real_time_crime_center': ('Real time crime center', r'\b(?:real[- ]time\s+crime\s+cent(?:er|re)s?|RTCCs?)\b'),
 'predictive_policing': ('Predictive policing', r'\b(?:predictive\s+policing|PredPol|Geolitica|HunchLab)\b'),
 'surveillance_camera_network': ('Surveillance camera network', r'\b(?:CCTV|surveillance\s+cameras?(?:\s+networks?)?|video\s+surveillance\s+(?:systems?|networks?)|(?:public|citywide)\s+camera\s+networks?)\b'),
 'video_analytics': ('Video analytics', r'\b(?:BriefCam|video\s+analytics|automated\s+video\s+analysis)\b'),
 'fusion_center': ('Fusion center', r'\bfusion\s+cent(?:er|re)s?\b'),
 'camera_registry': ('Camera registry', r'\b(?:(?:private\s+)?camera\s+(?:registr(?:y|ies|ation)|register)|(?:video|camera)\s+sharing\s+program)\b'),
 'cell_site_simulator': ('Cell site simulator', r'\b(?:cell[- ]site\s+simulators?|IMSI[- ]catchers?|Sting[Rr]ays?|Hailstorm)\b'),
 'mobile_device_forensics': ('Mobile device forensics', r'\b(?:Cellebrite|GrayKey|mobile\s+(?:phone|device)\s+forensics|cell\s*phone\s+extraction)\b'),
 'third_party_investigative_platform': ('Third party investigative platform', r'\b(?:Palantir|CrimeTracer|Coplink(?:\s+X)?|Accurint|TLOxp|Thomson\s+Reuters\s+CLEAR|PenLink|Skopenow|Peregrine|Whooster|Dataminr|Chorus\s+Intelligence|ShadowDragon|third[- ]party\s+investigative\s+platforms?|investigative\s+data\s+platforms?|Fog\s+(?:Data\s+Science|Reveal))\b'),
}
COMPILED = {k:re.compile(v[1],re.I) for k,v in TECHNOLOGIES.items()}
FLOCK = re.compile(r'\b(?:flock(?:\s+safety)?|flock\s+raven)\b',re.I)
USE = re.compile(r'\b(?:uses?|used|using|utilizes?|utilized|utilizing|operates?|operated|operating|deployed|installed|adopted|implemented|launched|began|started|participates?\s+in|outfitted|equipped|owns?|owned|maintains?|maintained|has\s+been\s+(?:using|operating)|receives?\s+alerts|has\s+access\s+to|accesses?|accessed)\b',re.I)
POSSESSION = re.compile(r'\b(?:has|have|had)\s+(?:(?:a|an|the|its|their|approximately|about|over|more\s+than)\s+)*(?:\d[\d,]*|one|two|three|four|five|six|seven|eight|nine|ten|several|multiple|a|an)\s+',re.I)
PURCHASE = re.compile(r'\b(?:purchased|bought|acquired|obtained|received|spent\s+\$[\d,]+)\b',re.I)
PLAN = re.compile(r'\b(?:plans?|planned|planning|proposed|proposes?|consider(?:s|ed|ing)?|intends?|intended|will|would|could|may|might|seeks?|seeking|requests?|requested|requesting|hopes?|hoping|expected|scheduled|recommend(?:s|ed|ation)?)\b|\b(?:to\s+(?:buy|purchase|install|deploy|adopt|acquire)|funding\s+to|grant\s+to|budget(?:ed)?\s+for)\b',re.I)
NEGATION = re.compile(r"\b(?:not|never|without|no\s+(?:longer|plans|use|access|cameras)|doesn.t|didn.t|hasn.t|haven.t|isn.t|aren.t|rejected|declined|cancelled|canceled|banned|prohibited)\b",re.I)
STOP = re.compile(r'\b(?:stopped\s+(?:using|operating)|ceased|discontinued|deactivated|terminated|no\s+longer|ended\s+(?:its|the)\s+(?:use|program|contract))\b',re.I)
APPROVAL = re.compile(r'\b(?:approved|authorized|awarded|funded|funding|grant|budget|contract|agreement)\b',re.I)
AGENCY_WORD = re.compile(r"\b(?:police\s+(?:department|division)|sheriff(?:.s)?\s+(?:office|department)|constables?|transportation\s+department)\b",re.I)
GENERIC_SUBJECT = re.compile(r"\b(?:the\s+(?:agency|department|division|sheriff(?:.s)?\s+office)|it)\s+(?:(?:currently|previously|formerly|already|also|now|recently)\s+)*(?:has|had|have|uses?|used|operates?|operated|purchased|bought|acquired|installed|deployed|began|started|owns?|maintains?|is|was|received|spent)\b",re.I)


def clean(value): return re.sub(r'\s+',' ',str(value or '')).strip()
def norm(value): return re.sub(r'[^a-z0-9]+',' ',clean(value).lower()).strip()

def canonical_agency(value):
    value=norm(value)
    value=re.sub(r'\bsheriff s\b|\bsheriffs\b','sheriff',value)
    value=re.sub(r'\bpd\b','police',value)
    value=re.sub(r'\b(?:department|dept|division|office)\b','',value)
    return clean(value)

def split_sentences(text):
    text = re.sub(r'\bU\.S\.', 'US', clean(text))
    text = re.sub(r'\b(?:Dept|Inc|Co)\.', lambda m:m.group(0).replace('.',''),text)
    # Keep the original sentence for audit; contrastive clauses are checked separately.
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z"“])|[\r\n]+',text) if s.strip()]


def clauses(sentence):
    return [s.strip(' ,;') for s in re.split(r';|\bbut\b|\bhowever\b|\bwhereas\b|\bwhile\b|\band\s+(?=(?:purchased|uses?|used|operates?|operated|began|installed|deployed|acquired|adopted|maintains?|has|had|received|plans?|planned)\b)', sentence, flags=re.I) if s.strip(' ,;')]


def attributed(clause, agency):
    """Require target name, recognisable acronym, or agency reference without another named LEA."""
    n, target = norm(clause), norm(agency)
    if target and target in n:
        # Another named LEA in the same clause can be the actual adopter.
        tail = clause[clause.lower().find(agency.lower())+len(agency):] if agency.lower() in clause.lower() else ''
        if AGENCY_WORD.search(tail): return False, 'multiple_agencies_in_clause'
        return True, 'agency_name'
    # Accommodate minor typos in name immediately before police/sheriff designation.
    for m in AGENCY_WORD.finditer(clause):
        prefix = norm(clause[max(0,m.start()-90):m.end()])
        words = target.split()
        if len(words) >= 3:
            candidate = ' '.join(prefix.split()[-len(words):])
            if difflib.SequenceMatcher(None,candidate,target).ratio() >= .94:
                return True, 'near_exact_agency_name'
    acronym = ''.join(w[0] for w in agency.split() if w.lower() not in {'of','the','and'})
    if len(acronym) >= 3 and re.search(r'\b'+re.escape(acronym)+r'\b',clause): return True, 'agency_acronym'
    if GENERIC_SUBJECT.search(clause) and not AGENCY_WORD.search(re.sub(r"the\s+sheriff(?:.s)?\s+office", '', clause, flags=re.I)): return True, 'generic_agency_reference'
    return False, 'uncertain_or_other_agency'


def explicit_year(clause, keyword):
    # Require year attached to use/deployment language; do not use article/link publication dates.
    # Multiple years can describe expansions. Save candidates and use earliest only for observed history.
    patterns = [r'\b(?:since(?:\s+at\s+least)?|as\s+of|in|during)\s+(?:[A-Za-z]+\s+)?((?:19|20)\d{2})\b',
                r'\b((?:19|20)\d{2})\b[^.;]{0,55}\b(?:began|started|installed|deployed|adopted|purchased|launched)\b']
    years = set()
    for pattern in patterns:
        for m in re.finditer(pattern,clause,re.I):
            if abs(m.start()-keyword.start()) <= 170: years.add(int(m.group(1)))
    if re.search(r'\b(?:published|publication|article|report\s+(?:dated|released|published))\b', clause, re.I) and not re.search(r'\bsince\b|\bas\s+of\b',clause,re.I):
        years=set()
    return min(years) if years else '', '|'.join(map(str,sorted(years)))


def classify(clause, agency, tech, match, inherited=False):
    ok, attribution = attributed(clause, agency)
    if not ok and inherited and re.match(r'^(?:purchased|uses?|used|operates?|operated|began|installed|deployed|acquired|adopted|maintains?|has|had|received|plans?|planned)\b',clause,re.I) and not AGENCY_WORD.search(clause):
        ok, attribution=True,'inherited_subject_from_previous_clause'
    if not ok: return 'review_attribution',attribution
    # Local clause includes the technology and predicate. Negation/plans never qualify on their own.
    if STOP.search(clause): return 'historical_discontinued',attribution
    if NEGATION.search(clause): return 'rejected_or_negated',attribution
    if PLAN.search(clause): return 'planned_or_funded_only',attribution
    if re.search(r'\b(?:free\s+trial|trial\s+(?:period|program)|pilot\s+program|testing|evaluating|experimenting)\b',clause,re.I):
        return 'trial_or_evaluation_only',attribution
    # A registry of private cameras does not establish an agency-operated camera network.
    if tech=='surveillance_camera_network' and re.search(r'\b(?:registry|registration|register)\b',clause,re.I):
        return 'review_registry_not_camera_network',attribution
    # A center mentioned as the location of another tool is not proof of opening/operating the center.
    if tech in {'fusion_center','real_time_crime_center'} and not re.search(r'\b(?:operates?|operated|opened|launched|established|runs?|maintains?|has)\b',clause,re.I):
        return 'review_center_context',attribution
    predicates = list(USE.finditer(clause)) + list(POSSESSION.finditer(clause))
    if any(abs(p.start()-match.start()) <= 150 for p in predicates):
        return 'confirmed_use',attribution
    if PURCHASE.search(clause):
        # Funding received is not equipment received. Procurement is separate from operational use.
        if re.search(r'\breceived\b.*\b(?:funds|funding|grant|money|award|approval|authorization)\b',clause,re.I):
            return 'planned_or_funded_only',attribution
        return 'confirmed_procurement',attribution
    if APPROVAL.search(clause): return 'approval_or_contract_only',attribution
    return 'mention_only',attribution


def parse_ori(raw):
    # Atlas field can be ORI+technology suffix (e.g. CO0640100ALPR), not a nine-character ORI.
    raw=clean(raw).upper()
    if re.fullmatch(r'[A-Z]{2}[A-Z0-9]{7}(?:ALPR|BWC|GSD|DRONE|FR|RTCC|CCTV|CR|CSS|UAV|GDT|PRPO|FRT[A-Z0-9]*|TPIP[A-Z0-9]*|VA|FC)?',raw) and not raw.startswith('XX'):
        return raw[:9]
    return ''


def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def write_csv(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)


def score_records(records, cutoff_year=None):
    audit, agencies = [], {}
    for source_file, row in records:
        agency, state=clean(row.get('Agency')),clean(row.get('State'))
        if not agency or not state: continue
        ori=parse_ori(row.get('NEWAOSNUMBER (ORI9)',row.get('ORI','')))
        # Preserve separate agency name/location keys when no usable ORI exists.
        key=(ori+'|' if ori else '')+'name:'+norm(state)+'|'+canonical_agency(agency)
        if not ori: key+='|'+norm(row.get('County'))+'|'+norm(row.get('City'))
        group=agencies.setdefault(key,{'agency_key':key,'ori':ori,'agency_name':agency,'state':state,
            'city':clean(row.get('City')),'county':clean(row.get('County')),'agency_type':clean(row.get('Type of LEA')),
            'names':set(),'record_ids':set(),'source_technologies':set(),'evidence':[]})
        group['names'].add(agency); group['record_ids'].add(clean(row.get('AOSNUMBER')))
        group['source_technologies'].add(clean(row.get('Technology')))
        summary=clean(row.get('Summary')); sentences=split_sentences(summary)
        for sentence_no,sentence in enumerate(sentences,1):
            inherited=False
            for clause in clauses(sentence):
                current_attributed,_=attributed(clause,agency)
                for tech,pattern in COMPILED.items():
                    name_spans=[(m.start(),m.end()) for m in re.finditer(re.escape(agency),clause,re.I)]
                    matches=[m for m in pattern.finditer(clause) if not any(a<=m.start() and m.end()<=b for a,b in name_spans)]
                    if not matches: continue
                    match=matches[0]
                    status,attribution=classify(clause,agency,tech,match,inherited)
                    flock=bool(FLOCK.search(clause)) or (tech=='alpr' and 'flock' in norm(row.get('Vendor')))
                    # On Flock-labelled rows, generic historical ALPR references cannot establish non-Flock use.
                    if flock and tech=='alpr' and not FLOCK.search(clause):
                        explicit_other_vendor=re.search(r'\b(?:Vigilant|ELSAG|Motorola|Genetec|Leonardo|3M|PIPS|PlateSmart|Rekor|Nupark)\b',clause,re.I)
                        explicit_prior=re.search(r'\b(?:prior\s+to|before\s+(?:adopting|using|installing|flock)|previously|formerly)\b',clause,re.I)
                        if explicit_other_vendor or explicit_prior: flock=False
                    year,year_candidates=explicit_year(clause,match)
                    qualifies=status=='confirmed_use' and not flock
                    temporal_status='snapshot'
                    if cutoff_year is not None:
                        temporal_status='undated' if year=='' else 'after_cutoff' if year>cutoff_year else 'documented_by_cutoff'
                        qualifies=qualifies and temporal_status=='documented_by_cutoff'
                    sources=[clean(row.get(f'Link {i}')) for i in (1,2,3) if clean(row.get(f'Link {i}'))]
                    ev={'agency_key':key,'ori':ori,'agency_name':agency,'state':state,'aos_number':clean(row.get('AOSNUMBER')),
                        'source_file':source_file,'record_technology':clean(row.get('Technology')),'record_vendor':clean(row.get('Vendor')),
                        'technology':tech,'matched_keywords':' | '.join(dict.fromkeys(m.group(0) for m in matches)),
                        'sentence_number':sentence_no,'evidence_sentence':sentence,'evidence_clause':clause,
                        'adoption_status':status,'attribution_rule':attribution,'flock_linked_or_uncertain':flock,
                        'evidence_year':year,'year_candidates':year_candidates,'temporal_status':temporal_status,
                        'counts_in_index':qualifies,'source_links':' | '.join(sources),
                        'source_link_note':'Record-level references; sentence-to-link correspondence is not established'}
                    audit.append(ev);group['evidence'].append(ev)
                inherited=current_attributed or (inherited and not AGENCY_WORD.search(clause))
    ori_keys=collections.defaultdict(set)
    for key,g in agencies.items():
        if g['ori']: ori_keys[g['ori']].add(key)
    output=[]
    for key,g in sorted(agencies.items()):
        evidence=g.pop('evidence')
        confirmed={e['technology'] for e in evidence if e['counts_in_index']}
        procurement={e['technology'] for e in evidence if e['adoption_status']=='confirmed_procurement' and not e['flock_linked_or_uncertain'] and (cutoff_year is None or e['temporal_status']=='documented_by_cutoff')}
        discontinued={e['technology'] for e in evidence if e['adoption_status']=='historical_discontinued' and not e['flock_linked_or_uncertain']}
        years=[e['evidence_year'] for e in evidence if e['counts_in_index'] and e['evidence_year']!='']
        result={k:v for k,v in g.items() if k not in {'names','record_ids','source_technologies'}}
        result.update(atlas_based_absorptive_capacity=len(confirmed),
            confirmed_technology_types=' | '.join(sorted(confirmed)),
            procurement_inclusive_index=len(confirmed|procurement),
            historical_discontinued_types=' | '.join(sorted(discontinued)),
            earliest_qualifying_evidence_year=min(years) if years else '',
            cutoff_year=cutoff_year if cutoff_year is not None else '',
            index_mode='documented_by_cutoff' if cutoff_year is not None else 'snapshot_not_pre_treatment',
            atlas_record_count=len(g['record_ids']),
            supporting_clause_count=sum(e['counts_in_index'] for e in evidence),
            ambiguous_clause_count=sum(e['adoption_status'].startswith('review') for e in evidence),
            undated_confirmed_clause_count=sum(e['adoption_status']=='confirmed_use' and not e['flock_linked_or_uncertain'] and e['evidence_year']=='' for e in evidence),
            observed_flock_evidence=any(e['adoption_status']=='confirmed_use' and e['flock_linked_or_uncertain'] for e in evidence),
            agency_name_conflict=len(g['names'])>1,ori_shared_by_distinct_agency_names=bool(g['ori'] and len(ori_keys[g['ori']])>1),ori_join_status='parsed_candidate_verify_against_directory' if g['ori'] else 'unavailable_or_synthetic',
            source_technology_categories=' | '.join(sorted(g['source_technologies'])),
            zero_interpretation='no_qualifying_evidence_in_supplied_records_not_verified_nonadoption')
        for tech in TECHNOLOGIES: result['adopted_'+tech]=int(tech in confirmed)
        output.append(result)
    return output,audit


def download_full_atlas(path):
    import urllib.request, io
    req=urllib.request.Request(DOWNLOAD_URL,headers={'User-Agent':'FlockResearch-AtlasCollector/1.0','Accept':'text/csv'})
    with urllib.request.urlopen(req,timeout=120) as response:
        data=response.read(); final_url=response.geturl()
    rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    if not rows or not {'Agency','State','Summary','Technology'}.issubset(rows[0]):
        raise ValueError('Official download did not return a valid Atlas CSV; original files retained.')
    categories={r['Technology'] for r in rows}
    if len(categories)<5:raise ValueError('Download is not a broad full export; refusing to score as full Atlas.')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    meta={'source_url':DOWNLOAD_URL,'final_url':final_url,'downloaded_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
          'rows':len(rows),'technology_categories':sorted(categories),'sha256':hashlib.sha256(data).hexdigest()}
    path.with_suffix('.metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    return meta


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,nargs='+',default=[DEFAULT_INPUT],help='One or more ORIGINAL Atlas CSV exports')
    p.add_argument('--out-dir',type=Path,default=ROOT/'data/atlas_absorptive_capacity')
    p.add_argument('--cutoff-year',type=int,help='Count only adoption evidence explicitly dated by this year; source publication dates are not used')
    p.add_argument('--download-full',action='store_true',help='Download the current full official Atlas CSV before scoring')
    args=p.parse_args();records=[];source_meta=[]
    if args.download_full:
        download_full_atlas(DEFAULT_INPUT)
        if args.input == [DEFAULT_INPUT]: print('Using freshly downloaded full Atlas data.')
    if args.input == [DEFAULT_INPUT] and not DEFAULT_INPUT.exists():
        print('Full Atlas file not found; downloading from the official source.')
        download_full_atlas(DEFAULT_INPUT)
    for path in args.input:
        rows=read_csv(path)
        if rows and not {'Agency','State','Summary'}.issubset(rows[0]): p.error(f'Not an original Atlas export: {path}')
        records.extend((path.name,row) for row in rows)
        source_meta.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':len(rows)})
    results,audit=score_records(records,args.cutoff_year)
    source_categories=sorted({clean(r.get('Technology')) for _,r in records})
    limitation=len(source_categories)==1
    for r in results:r['single_technology_export_warning']=limitation
    fields=list(results[0]) if results else ['agency_key','atlas_based_absorptive_capacity']
    write_csv(args.out_dir/'atlas_based_absorptive_capacity.csv',results,fields)
    audit_fields=list(audit[0]) if audit else ['agency_key','technology','adoption_status','evidence_sentence']
    write_csv(args.out_dir/'adoption_evidence_audit.csv',audit,audit_fields)
    review=[e for e in audit if not e['counts_in_index']]
    write_csv(args.out_dir/'excluded_and_review_evidence.csv',review,audit_fields)
    dictionary=[{'technology':key,'label':value[0],'keyword_regex':value[1]} for key,value in TECHNOLOGIES.items()]
    write_csv(args.out_dir/'technology_dictionary.csv',dictionary,list(dictionary[0]))
    meta={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'inputs':source_meta,'agency_count':len(results),
        'input_technology_categories':source_categories,'cutoff_year':args.cutoff_year,
        'index_definition':'Count of distinct technology types with confirmed agency use evidence; Flock-linked evidence excluded',
        'index_distribution':dict(collections.Counter(r['atlas_based_absorptive_capacity'] for r in results)),
        'adoption_status_distribution':dict(collections.Counter(e['adoption_status'] for e in audit)),
        'single_technology_export_warning':limitation,
        'limitations':['Proxy for documented technology experience, not a validated measure of absorptive capacity.',
          'Absence of evidence is not evidence of nonadoption. No keyword frequency or repeated-record bonus.',
          'ALPR-only exports cannot support a comprehensive technology breadth comparison.',
          'Snapshot index is not automatically a pre-treatment measure.',
          'Regex rules can miss paraphrases and mishandle attribution or scope; inspect sentence evidence.',
          'Explicit years are local evidence years, not necessarily exact first adoption dates.',
          'ORI suffix stripping produces candidate identifiers; verify against agency directory.',
          'No article fetching; only supplied Atlas Summary text is analysed.']}
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/'run_metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(json.dumps(meta,indent=2))
if __name__=='__main__':main()
