"""Check the news research artifact; does not publish or prove source accuracy."""
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, unquote
import json
import sys

CATEGORIES = {
    'precios_y_mercados', 'abastecimiento_y_cosechas', 'insumos_y_costos',
    'clima_y_riesgos', 'sanidad_agropecuaria', 'transporte_y_logistica',
    'apoyos_y_normativa', 'investigacion_y_cultivos', 'eventos_y_formacion',
}
REQUIRED = {
    'canonical_url', 'source_name', 'source_type', 'title', 'factual_label_es',
    'published_at', 'date_precision', 'updated_at', 'retrieved_at', 'decision',
    'confidence', 'primary_category', 'tags', 'crops', 'inputs', 'named_markets',
    'geography', 'colombia_relevance_es', 'evidence_urls', 'display_expires_at',
    'expiry_reason', 'source_valid_until', 'review_at', 'status', 'rights_status',
}

def iso(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp has no timezone')
    return result

def canonical(value):
    u = urlsplit(value)
    if u.scheme not in ('https', 'http') or not u.hostname:
        raise ValueError('invalid public URL')
    args = [(k, v) for k, v in parse_qsl(u.query) if not k.startswith('utm_') and k not in ('fbclid', 'gclid')]
    return urlunsplit((u.scheme, u.netloc.lower().removeprefix('www.'), unquote(u.path).rstrip('/'), urlencode(sorted(args)), ''))

def validate(path):
    data = json.loads(path.read_text())
    errors, warnings = [], []
    start, end, run = (iso(data[k]) for k in ('window_start', 'window_end', 'run_at'))
    if not start < end <= run:
        errors.append('Window must end no later than run time and start earlier.')
    if run > datetime.now(timezone.utc) + timedelta(minutes=1):
        errors.append('Run timestamp is in the future.')
    stories = data.get('stories', [])
    expired = data.get('expired_or_corrected', [])
    # expired_or_corrected may be references to stories, or full separate records.
    extra = [s for s in expired if isinstance(s, dict) and 'factual_label_es' in s]
    all_records = stories + extra
    seen = {}
    for i, s in enumerate(all_records):
        name = s.get('canonical_url', f'item {i}')
        missing = REQUIRED - s.keys()
        if missing:
            errors.append(f'{name}: missing fields {sorted(missing)}')
        try:
            key = canonical(s['canonical_url'])
            if key in seen:
                errors.append(f'{name}: duplicate canonical URL ({seen[key]} and {i})')
            seen[key] = i
        except (KeyError, ValueError) as exc:
            errors.append(f'{name}: {exc}')
        if s.get('decision') not in ('include', 'review', 'discard'):
            errors.append(f'{name}: invalid decision')
        if s.get('primary_category') not in CATEGORIES:
            errors.append(f'{name}: invalid category')
        if s.get('decision') == 'include':
            if not s.get('publication_evidence'):
                errors.append(f'{name}: no publication evidence recorded')
            if not s.get('evidence_urls') or not s.get('colombia_relevance_es'):
                errors.append(f'{name}: missing provenance or relevance')
        try:
            published = iso(s['published_at']) if s.get('published_at') else None
            expiry = iso(s['display_expires_at']) if s.get('display_expires_at') else None
            if s.get('decision') == 'include' and not published:
                errors.append(f'{name}: included with no publication date')
            if published and not start <= published <= end:
                errors.append(f'{name}: publication outside requested window')
            if expiry and published and expiry <= published:
                errors.append(f'{name}: expiry must follow publication')
            if expiry and published and s.get('expiry_rule_hours') is not None and expiry > published + timedelta(hours=s['expiry_rule_hours']):
                errors.append(f'{name}: expiry exceeds declared lifetime')
            if expiry and published and '48 horas' in s.get('expiry_reason', '') and expiry > published + timedelta(hours=48):
                errors.append(f'{name}: expiry conflicts with its stated 48-hour rule')
            if s.get('status') == 'active' and (not expiry or expiry <= run):
                errors.append(f'{name}: active despite absent/past expiry')
            if s.get('status') == 'expired' and expiry and expiry > run:
                errors.append(f'{name}: expired before its expiry')
            for key in ('updated_at', 'retrieved_at', 'source_valid_until', 'review_at'):
                if s.get(key):
                    d = iso(s[key])
                    if key == 'retrieved_at' and d > run:
                        errors.append(f'{name}: retrieved after the recorded run')
        except (ValueError, TypeError) as exc:
            errors.append(f'{name}: date error: {exc}')
        if s.get('date_precision') == 'date' and not s.get('publication_evidence'):
            warnings.append(f'{name}: date-only midnight interpretation needs documentation')
        if s.get('rights_status') not in ('unverified', 'not_established'):
            warnings.append(f'{name}: review rights claim {s.get("rights_status")}')
    catalog_path = Path(__file__).resolve().parents[2] / 'automation/news-cloud-job.json'
    expected = {s['name'] for s in json.loads(catalog_path.read_text())['sources']}
    coverage = data.get('coverage', [])
    for c in coverage:
        if c.get('checked_at') and iso(c['checked_at']) > run:
            errors.append(f'{c.get("source")}: checked after run timestamp')
    covered = [c.get('source', c.get('source_name', c.get('name'))) for c in coverage]
    missing_sources = sorted(expected - set(covered))
    if missing_sources:
        errors.append(f'Catalog sources missing from coverage: {missing_sources}')
    duplicates = [s for s, n in Counter(covered).items() if n > 1]
    if duplicates:
        warnings.append(f'Multiple coverage records for {duplicates}')
    output = {
        'artifact': str(path), 'check_scope': 'structure, dates, URL deduplication, source-accounting; not content truth or licensing',
        'window_start': data['window_start'], 'window_end': data['window_end'],
        'records': len(all_records), 'decisions': dict(Counter(s.get('decision') for s in all_records)),
        'statuses': dict(Counter(s.get('status') for s in all_records)),
        'categories': dict(Counter(s.get('primary_category') for s in all_records)),
        'contributing_sources': dict(Counter(s.get('source_name') for s in all_records if s.get('decision') == 'include')),
        'coverage_records': len(coverage), 'coverage_statuses': dict(Counter(c.get('status') for c in coverage)),
        'errors': errors, 'warnings': warnings, 'passed': not errors,
    }
    return output

if __name__ == '__main__':
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name('backfill.json')
    result = validate(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['passed'] else 1)
