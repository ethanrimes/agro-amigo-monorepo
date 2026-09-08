"""Run with python -m pipelines.news.cli. Collect first; review before publication."""
import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .content import BOGOTA, CATEGORIES, CROPS, INPUTS, LIFETIMES, allowed, canonical, discover, diverse, expiry, extract, spanish, topics
from .state import State, stamp
from .transport import Fetcher, FetchError

HERE = Path(__file__).resolve().parent

def config(path):
    data = json.loads(Path(path).read_text())
    if data['policy']['source_language'] != 'es' or data['policy']['allow_machine_translation']:
        raise ValueError('This collector requires original Spanish-language source pages')
    ids = [s['id'] for s in data['sources']]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate source IDs')
    for s in data['sources']:
        if s['language'] != 'es': raise ValueError('Non-Spanish source in catalog')
        if not allowed(s['url'], s) and s['enabled']: raise ValueError('Invalid source origin: '+s['id'])
    return data

def write_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)

def assess(record, source, start, end):
    record.update(source_id=source['id'],source_name=source['name'],source_group=source['group'],
        publisher_id=source['publisher_id'], rights_status=source['public_display_rights'],
        source_language='es',title=None,decision='review',status='review',
        classification_method='deterministic_triage_not_luna', review_reason='semantic_classification_pending')
    if not record['language']['accepted']:
        if record['language']['detected']=='es' and record['language']['confidence']>=.90:
            record['review_reason']='insufficient_article_text_for_language_check'
        else:
            record.update(decision='discard',status='discarded',review_reason='source_not_verified_spanish')
    elif not record['published_at']:
        record['review_reason'] = 'conflicting_publication_dates' if record['date_conflict'] else 'publication_date_missing'
    elif not start <= datetime.fromisoformat(record['published_at']) <= end:
        record.update(decision='discard',status='discarded',review_reason='publication_outside_window')
    elif record['relevance_kind'] == 'none':
        record.update(decision='discard',status='discarded',review_reason='no_agricultural_relevance_signal')
    return record

def collect(args, data, state):
    started = stamp(); now = datetime.fromisoformat(started)
    end = datetime.fromisoformat(args.end).replace(tzinfo=BOGOTA)+timedelta(days=1)-timedelta(microseconds=1) if args.end else now
    if end > now: end = now
    start = datetime.fromisoformat(args.since).replace(tzinfo=BOGOTA) if args.since else end-timedelta(days=14)
    if start > end: raise ValueError('Start must precede end')
    selected = set(args.source or [])
    known_ids = {s['id'] for s in data['sources']}
    if selected-known_ids: raise ValueError('Unknown source IDs: '+','.join(sorted(selected-known_ids)))
    seeds = json.loads(Path(args.seeds).read_text()) if args.seeds else []
    for seed in seeds:
        source = next((s for s in data['sources'] if s['id']==seed['source_id']), None)
        if not source or not source['enabled'] or not allowed(seed['url'],source): raise ValueError('Seed outside allowed source')
        state.enqueue(source['id'],[dict(url=canonical(seed['url']),headline='',listing_date_hint=None)])
    sources = [s for s in data['sources'] if not selected or s['id'] in selected]
    # Older/unattempted sources go first on the next bounded invocation.
    attempted = dict(state.db.execute('SELECT source,last_attempt FROM source_state'))
    sources.sort(key=lambda s: attempted.get(s['id']) or '')
    report = dict(run_id=started,started_at=started,window_start=start.isoformat(),window_end=end.isoformat(),
        language='es',mode='research_only',discovery_mode='seeds_only' if args.seeds_only else 'listings',
        coverage=[],errors=[],classified_with_luna=False)
    fetcher = Fetcher(timeout=args.timeout,retries=1)
    fetcher.blocked_until.update(state.backoffs())
    deadline = time.monotonic()+args.max_seconds
    try:
        for source in sources:
            row = dict(source_id=source['id'],source=source['name'],group=source['group'],
                discovery_pages=0,candidates_found=0,articles_attempted=0,outcomes={},errors=[])
            report['coverage'].append(row)
            if not source['enabled']:
                row.update(status='disabled',reason=source['disabled_reason']); continue
            if time.monotonic() >= deadline:
                row.update(status='deferred_time_budget',backlog=state.backlog(source['id'])); continue
            checkpoint = state.checkpoint(source['id'])
            source_start = start if args.since or not checkpoint else min(end,datetime.fromisoformat(checkpoint)-timedelta(hours=72))
            row['window_start'] = source_start.isoformat()
            listing_queue = [] if args.seeds_only else list(source['discovery_urls'])
            visited, successes = set(), 0
            while listing_queue and len(visited) < args.pages and time.monotonic() < deadline:
                url = listing_queue.pop(0)
                if url in visited or not allowed(url,source): continue
                visited.add(url)
                try:
                    page = fetcher.fetch(url,source)
                    candidates, feeds, next_pages = discover(page.text,page.url,source)
                    candidates = [c for c in candidates if c['url'] not in {canonical(u) for u in source['discovery_urls']}]
                    candidates = [c for c in candidates if urlsplit(c['url']).path not in ('','/') or urlsplit(c['url']).query]
                    if source.get('article_path_pattern'):
                        candidates = [c for c in candidates if re.search(source['article_path_pattern'],urlsplit(c['url']).path)]
                    # Apply the same triage to RSS and HTML, avoiding general-news
                    # homepages filling the article budget with politics or sport.
                    candidates = [c for c in candidates if not c['headline'] or topics(c['headline'])['agriculture_signal'] or topics(c['headline'])['transmission_channel']]
                    state.enqueue(source['id'],candidates)
                    row['candidates_found'] += len(candidates)
                    row['discovery_pages'] += 1; successes += 1
                    listing_queue = feeds+next_pages+listing_queue
                except (FetchError,ValueError) as exc:
                    row['errors'].append(dict(url=url,code=exc.code if isinstance(exc,FetchError) else 'invalid_discovery_document'))
            outcomes = Counter()
            pending = state.pending(source['id'],args.articles)
            # Reserve capacity for due alert checks without starving new stories.
            due = state.rechecks(source['id'],max(1,args.articles//4))
            urls = list(dict.fromkeys(due+pending))[:args.articles]
            for url in urls:
                if time.monotonic() >= deadline: break
                row['articles_attempted'] += 1
                try:
                    page = fetcher.fetch(url,source)
                    record = assess(extract(page.text,page.url,source),source,source_start,end)
                    record['original_url'] = url
                    state.upsert(source['id'],record)
                    outcomes[record['review_reason']] += 1
                    state.candidate_result(url,'processed')
                except (FetchError,ValueError) as exc:
                    code = exc.code if isinstance(exc,FetchError) else 'invalid_article_document'
                    outcomes[code] += 1
                    retry = max(3600,exc.retry_after) if isinstance(exc,FetchError) else 86400
                    state.candidate_result(url,'error',retry)
                    row['errors'].append(dict(url=url,code=code))
            row.update(status='partial' if row['errors'] or listing_queue or time.monotonic()>=deadline else 'checked',
                outcomes=dict(outcomes),backlog=state.backlog(source['id']),checked_at=stamp(),
                listing_pages_remaining=len(listing_queue),coverage_complete=False)
            # Seed-only verification is not a successful archive scan.
            complete_listing = successes>0 and not listing_queue and not row['errors']
            state.finish_source(source['id'],complete_listing,row,started)
            print(json.dumps({'source':source['id'],'status':row['status'],'attempted':row['articles_attempted'],'backlog':row['backlog']},ensure_ascii=False),flush=True)
    finally:
        state.save_backoffs(fetcher.blocked_until)
        fetcher.close()
    report['finished_at'] = stamp()
    records = state.stories()
    report['totals'] = dict(stored=len(records),decisions=dict(Counter(s['decision'] for s in records)),
                            source_statuses=dict(Counter(s['status'] for s in report['coverage'])))
    state.finish_run(started,started,report)
    write_json(Path(args.output)/'run.json',report)
    export(args,state)
    return report

def apply_reviews(state, reviews, reviewer):
    if not reviewer.strip(): raise ValueError('Reviewer identity is required')
    indexed = {s['id']:s for s in state.stories()}
    updates=[]
    ids=[r.get('id') for r in reviews]
    if len(ids)!=len(set(ids)): raise ValueError('Duplicate story in review handoff')
    for review in reviews:
        record = indexed.get(review.get('id'))
        if not record: raise ValueError('Unknown story ID')
        if review.get('content_sha256') != record['content_sha256']: raise ValueError('Stale classification: source content changed')
        decision = review.get('decision')
        if decision not in ('include','review','discard','retracted','superseded','corrected'): raise ValueError('Unknown review decision')
        updated=dict(record)
        updated.update(classified_by=reviewer,classified_at=stamp(),classification_method='reviewed_handoff')
        if decision=='include':
            if not record['language']['accepted'] or not record['published_at'] or record['date_conflict']:
                raise ValueError('Language and publication evidence must pass before inclusion')
            if record.get('review_reason') == 'publication_outside_window': raise ValueError('Publication is outside the collection window')
            if review.get('primary_category') not in CATEGORIES: raise ValueError('Invalid category')
            if review.get('story_kind') not in LIFETIMES: raise ValueError('Invalid story kind')
            for field, vocabulary in (('crops',CROPS),('inputs',INPUTS)):
                values=review.get(field,record[field])
                if not isinstance(values,list) or any(v not in vocabulary for v in values):
                    raise ValueError('Invalid '+field+' tags')
                updated[field]=list(dict.fromkeys(values))
            channel=review.get('transmission_channel',record.get('transmission_channel'))
            if channel not in (None,'clima','insumos','logistica','comercio'):
                raise ValueError('Invalid transmission channel')
            updated['transmission_channel']=channel
            for field in ('factual_label_es','colombia_relevance_es'):
                text = review.get(field,'')
                if not isinstance(text,str) or not 5 <= len(text.split()) <= 65: raise ValueError('Expected a concise Spanish factual label and relevance explanation')
            combined=review['factual_label_es']+' '+review['colombia_relevance_es']
            if not spanish(combined,'es')['accepted']: raise ValueError('Classification output is not verified Spanish')
            if record['relevance_kind']=='indirect' and not review.get('impact_is_inference'):
                raise ValueError('International relevance must distinguish inferred impact')
            if review.get('explicit_end') and not review.get('deadline_evidence_url') in (record['canonical_url'],record['original_url']):
                raise ValueError('An earlier deadline needs original-source evidence')
            expires,check=expiry(record['published_at'],review['story_kind'],review.get('explicit_end'))
            updated.update({k:review[k] for k in ('primary_category','story_kind','factual_label_es','colombia_relevance_es')})
            updated.update(decision='include',status='active',display_expires_at=expires,review_at=check,
                impact_is_inference=bool(review.get('impact_is_inference')),event_id=review.get('event_id') or record['id'],
                priority=max(0,min(100,int(review.get('priority',50)))),classification=review)
        elif decision in ('retracted','superseded','corrected'):
            # A correction must reference a collected original, not an invented URL.
            correction=indexed.get(review.get('correction_story_id'))
            if not correction or not correction['language']['accepted'] or not correction['published_at']:
                raise ValueError('A correction requires a verified source record')
            updated.update(decision='review',status=decision,correction_url=correction['canonical_url'],classification=review)
        else:
            updated.update(decision=decision,status='review' if decision=='review' else 'discarded',classification=review)
        updates.append(updated)
    # Validate the entire handoff before writing any decisions.
    with state.db:
        for record in updates:
            state.db.execute('UPDATE stories SET record=? WHERE id=?',(json.dumps(record,ensure_ascii=False),record['id']))
    return len(updates)

def export(args,state):
    now = datetime.now(timezone.utc)
    records = state.stories()
    accepted=[]
    for record in records:
        if record['decision'] != 'include' or record['status'] in ('retracted','superseded','corrected'): continue
        record['status'] = 'expired' if datetime.fromisoformat(record['display_expires_at'])<=now else 'active'
        accepted.append(record)
    active=[s for s in accepted if s['status']=='active']
    # Near-identical headings become review suggestions; never silently delete a source.
    clusters={}
    for s in records: clusters.setdefault(s['headline_sha256'],[]).append(s['id'])
    queue=[s for s in records if s['decision']=='review' and s['status']=='review']
    output=Path(args.output)
    write_json(output/'review-queue.json',dict(schema_version=1,language='es',generated_at=stamp(),
        note='Original sources must be opened by the reviewer. No article bodies or images stored. Deterministic tags are suggestions, not Luna classifications.',
        stories=queue,duplicate_suggestions=[v for v in clusters.values() if len(v)>1]))
    write_json(output/'research-feed.json',dict(schema_version=1,generated_at=stamp(),language='es',
        public_display_authorized=False,stories=accepted,home=diverse(active),
        by_crop={crop:diverse([s for s in active if crop in s['crops']],4) for crop in sorted({c for s in active for c in s['crops']})}))
    write_json(output/'records.json',dict(schema_version=1,generated_at=stamp(),stories=records))

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['collect','review','export','catalog'])
    parser.add_argument('--catalog',default=str(HERE/'sources.json'))
    parser.add_argument('--state',default=str(HERE/'cache/news.sqlite3'))
    parser.add_argument('--output',default=str(HERE/'cache/latest'))
    parser.add_argument('--source',action='append')
    parser.add_argument('--since');parser.add_argument('--end')
    parser.add_argument('--pages',type=int,default=2);parser.add_argument('--articles',type=int,default=8)
    parser.add_argument('--max-seconds',type=int,default=900);parser.add_argument('--timeout',type=int,default=15)
    parser.add_argument('--seeds');parser.add_argument('--seeds-only',action='store_true')
    parser.add_argument('--reviews');parser.add_argument('--reviewer',default='')
    args=parser.parse_args(argv)
    if not 1<=args.max_seconds<=3600 or not 1<=args.pages<=10 or not 1<=args.articles<=100 or not 1<=args.timeout<=30:
        parser.error('Invalid bounded run limits')
    if args.seeds_only and not args.seeds: parser.error('--seeds-only requires --seeds')
    data=config(args.catalog)
    if args.command=='catalog':
        print(json.dumps({'sources':len(data['sources']),'enabled_candidates':sum(s['enabled'] for s in data['sources']),
                          'groups':dict(Counter(s['group'] for s in data['sources']))},ensure_ascii=False,indent=2));return
    state=State(args.state)
    try:
        with state.lock():
            if args.command=='collect': collect(args,data,state)
            elif args.command=='review':
                if not args.reviews: parser.error('--reviews is required')
                handoff=json.loads(Path(args.reviews).read_text())
                n=apply_reviews(state,handoff['stories'],args.reviewer)
                export(args,state);print(json.dumps({'reviewed':n,'public_display_authorized':False}))
            else: export(args,state)
    finally: state.close()

if __name__=='__main__':
    main()
