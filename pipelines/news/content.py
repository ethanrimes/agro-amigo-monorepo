"""Extract evidence conservatively: dates, language and relevance are independent."""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from dateutil.parser import isoparse
from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

DetectorFactory.seed = 0
BOGOTA = ZoneInfo('America/Bogota')
CATEGORIES = {
    'precios_y_mercados': 'precio cotizacion mercado demanda compradores comercializacion',
    'abastecimiento_y_cosechas': 'cosecha exportacion importacion produccion toneladas abastecimiento',
    'insumos_y_costos': 'fertilizante fertilizantes urea potasa fosfato insumos costos semilla maquinaria',
    'clima_y_riesgos': 'sequia lluvia lluvias inundacion incendio temperatura meteorologico nino',
    'sanidad_agropecuaria': 'fitosanitario sanidad plaga enfermedad fusarium broca bioseguridad',
    'transporte_y_logistica': 'puerto puertos flete carretera bloqueo transporte logistica naviera',
    'apoyos_y_normativa': 'convocatoria subsidio credito seguro normativa reglamento ministerio',
    'investigacion_y_cultivos': 'investigacion variedad variedades cultivo agronomia tecnologia',
    'eventos_y_formacion': 'curso capacitacion feria webinar taller formacion',
}
CROPS = {
    'café': ['cafe', 'cafetero', 'arabica', 'robusta'], 'cacao': ['cacao', 'cocoa'],
    'arroz': ['arroz', 'arrocero'], 'maíz': ['maiz'], 'papa': ['papa', 'patata'],
    'plátano': ['platano'], 'banano': ['banano', 'banana'], 'yuca': ['yuca'],
    'aguacate': ['aguacate', 'palta', 'hass'], 'mango': ['mango'],
    'cítricos': ['citricos', 'limon', 'naranja', 'mandarina'],
    'caña de azúcar': ['azucar', 'cana', 'panela'], 'palma de aceite': ['palma', 'palmicultor'],
    'fríjol': ['frijol', 'caupi', 'leguminosa'], 'soya': ['soya', 'soja'],
    'trigo': ['trigo'], 'hortalizas': ['hortaliza', 'tomate', 'cebolla', 'zanahoria'],
    'frutas': ['fruta', 'frutal', 'fresa', 'arandano', 'maracuya'],
}
INPUTS = {'urea': ['urea'], 'fertilizantes': ['fertilizante', 'fosfato', 'potasa', 'abono'],
          'semillas': ['semilla', 'plantula'], 'fitosanitarios': ['plaguicida', 'fungicida', 'herbicida'],
          'maquinaria': ['tractor', 'maquinaria'], 'alimentos para animales': ['forraje', 'balanceado']}
MONTHS = {v: i for i, names in enumerate([
    ['enero', 'ene'], ['febrero', 'feb'], ['marzo', 'mar'], ['abril', 'abr'], ['mayo', 'may'],
    ['junio', 'jun'], ['julio', 'jul'], ['agosto', 'ago'], ['septiembre', 'setiembre', 'sept', 'sep', 'set'],
    ['octubre', 'oct'], ['noviembre', 'nov'], ['diciembre', 'dic']], 1) for v in names}

def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))

def clean(text):
    return re.sub(r'\s+', ' ', text or '').strip()

def canonical(url):
    u = urlsplit(url)
    if u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password:
        raise ValueError('Invalid public URL')
    args = [(k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith('utm_') and k.lower() not in {'fbclid', 'gclid', 'mc_cid', 'mc_eid'}]
    return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path.rstrip('/') or '/', urlencode(sorted(args)), ''))

def date_value(value, zone='America/Bogota'):
    """No fuzzy parsing: event years and masthead dates must not become publication."""
    raw = clean(str(value))
    try:
        dt = isoparse(raw)
        precision = 'date' if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw) else 'second'
    except (ValueError, TypeError):
        try:
            dt = parsedate_to_datetime(raw)
            precision = 'second'
        except (ValueError, TypeError):
            normalized = fold(raw).strip(' .,')
            m = re.search(r'\b(\d{1,2})\s*(?:de\s+)?([a-z]+)\.?\s*(?:de\s+)?(20\d{2})\b', normalized)
            n = re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](20\d{2})', normalized)
            leading = re.fullmatch(r'([a-z]+)\s+(\d{1,2}),?\s+(20\d{2})',normalized)
            try:
                if m and m[2] in MONTHS:
                    dt = datetime(int(m[3]), MONTHS[m[2]], int(m[1]))
                elif n:
                    dt = datetime(int(n[3]), int(n[2]), int(n[1]))
                elif leading and leading[1] in MONTHS:
                    dt = datetime(int(leading[3]), MONTHS[leading[1]], int(leading[2]))
                else:
                    return None
                precision = 'date'
            except ValueError:
                return None
    assumed = dt.tzinfo is None
    if assumed: dt = dt.replace(tzinfo=ZoneInfo(zone))
    return dict(value=dt.isoformat(), precision=precision, timezone_assumed=assumed, evidence=raw[:100])

def allowed(url, source):
    try:
        u = urlsplit(canonical(url))
        return u.hostname in source['allowed_hosts'] and (u.port in (None, 80, 443)) and not re.search(r'/(?:en|pt|fr|de)(?:/|$)', u.path)
    except ValueError:
        return False

def words_match(text, term):
    # Canadá and canales are not sugar cane. Most other terms deliberately
    # retain a prefix match for agricultural inflections during triage.
    if term == 'cana': return bool(re.search(r'(?<!\w)cana(?:s|vera\w*)?(?!\w)',text))
    return bool(re.search(r'(?<!\w)' + re.escape(term) + r'\w*', text))

def topics(text):
    text = fold(text)
    crops = [label for label, terms in CROPS.items() if any(words_match(text, t) for t in terms)]
    inputs = [label for label, terms in INPUTS.items() if any(words_match(text, t) for t in terms)]
    scores = {cat: sum(words_match(text, word) for word in terms.split()) for cat, terms in CATEGORIES.items()}
    category = max(scores, key=scores.get)
    agri = bool(crops or inputs or re.search(r'agropecu|agricult|campesin|ganader|acuicult|porcicult|avicult', text))
    channel = None
    for label, pattern in [('clima', r'nino|sequia|precipitacion'), ('insumos', r'fertiliz|urea|fosfato|potasa'),
                           ('logistica', r'puerto|flete|navier|contenedor'), ('comercio', r'export|import|arancel|demanda|precio')]:
        if re.search(pattern, text): channel = label; break
    return dict(crops=crops, inputs=inputs, primary_category=category,
        category_scores=scores, agriculture_signal=agri,
        relevance_kind='direct' if re.search(r'colombi\w*', text) else 'indirect' if (agri or channel) else 'none',
        transmission_channel=channel)

def spanish(text, declared):
    try:
        scores = {x.lang: x.prob for x in detect_langs(text[:16000])}
    except LangDetectException:
        scores = {}
    p = scores.get('es', 0)
    # An es masthead never overrides a non-Spanish body. Very short text is review.
    ok = len(text.split()) >= 35 and p >= .90
    return dict(accepted=ok, detected=max(scores, key=scores.get) if scores else 'unknown',
                confidence=round(p, 4), declared=declared or None, method='langdetect-1.0.9-seed-0',
                reason='body_spanish' if ok else 'short_or_non_spanish_body')

def extract(html, url, source):
    soup = BeautifulSoup(html, 'html.parser')
    heading = soup.select_one(source.get('headline_selector','h1'))
    headline = clean(heading.get_text(' ', strip=True)) if heading else ''
    if not headline:
        meta = soup.find('meta',property='og:title')
        headline = clean(meta.get('content','')) if meta else ''
    primary = soup.select_one('article') or soup.select_one('main') or soup.body or soup
    dates = []
    updated = []
    # Only Article/NewsArticle JSON-LD; ignore sidebar ItemList and WebPage dates.
    for tag in soup.select('script[type="application/ld+json"]'):
        try: data = json.loads(tag.string or tag.get_text())
        except (ValueError, TypeError): continue
        nodes = data if isinstance(data, list) else [data]
        for node in list(nodes):
            if isinstance(node, dict): nodes.extend(node.get('@graph', []))
        for node in nodes:
            if not isinstance(node, dict): continue
            kinds = node.get('@type', [])
            if isinstance(kinds, str): kinds = [kinds]
            if not set(kinds) & {'NewsArticle', 'Article', 'ReportageNewsArticle', 'ScholarlyArticle'}: continue
            if node.get('headline') and headline and fold(clean(node['headline'])) != fold(headline): continue
            for key, output in [('datePublished', dates), ('dateModified', updated)]:
                parsed = date_value(node.get(key, ''), source['timezone'])
                if parsed: output.append(dict(parsed, method='jsonld.'+key))
    for key, output in [('article:published_time', dates), ('datePublished', dates), ('pubdate', dates),
                        ('article:modified_time', updated), ('dateModified', updated)]:
        for tag in soup.find_all('meta', attrs={'property': key}) + soup.find_all('meta', attrs={'name': key}):
            parsed = date_value(tag.get('content', ''), source['timezone'])
            if parsed: output.append(dict(parsed, method='meta.'+key))
    time_tags = list(primary.select('time[datetime]')) + list(soup.select('[itemprop="datePublished"]'))
    for tag in time_tags:
        if tag.get('itemprop') == 'dateModified': continue
        if tag.find_parent(['aside','nav']) or (tag.find_parent('footer') and tag.get('itemprop')!='datePublished'): continue
        # Without explicit published semantics, only accept a single time in article.
        if tag.get('itemprop') != 'datePublished' and len(primary.select('time[datetime]')) != 1: continue
        parsed = date_value(tag.get('datetime') or tag.get('content') or tag.get_text(' ', strip=True), source['timezone'])
        if parsed: dates.append(dict(parsed, method='article.time'))
    for element in soup.find_all(string=re.compile(r'Fecha de publicaci[oó]n\s*:', re.I)):
        raw = clean(element)
        parsed = date_value(re.split(r'Fecha de publicaci[oó]n\s*:', raw, flags=re.I)[-1], source['timezone'])
        if parsed: dates.append(dict(parsed, method='explicit_publication_label'))
    for tag in soup.select(source.get('publication_date_selector','.__no_date_selector__')):
        parsed=date_value(tag.get_text(' ',strip=True),source['timezone'])
        if parsed: dates.append(dict(parsed,method='source_visible_publication_date'))
    chosen = dates[0] if dates else None
    date_days = {datetime.fromisoformat(d['value']).astimezone(ZoneInfo(source['timezone'])).date() for d in dates}
    conflict = len(date_days) > 1
    for tag in primary.select('script, style, nav, footer, aside, form, header, .related, .related-posts, .comments'):
        tag.decompose()
    paragraphs = [clean(p.get_text(' ', strip=True)) for p in primary.find_all('p')]
    body = '\n'.join(p for p in paragraphs if len(p.split()) >= 8)
    # Some official pages use divs rather than paragraphs; keep this fallback visible.
    fallback = len(body.split()) < 35
    if fallback: body = clean(primary.get_text(' ', strip=True))
    language = spanish(headline + '\n' + body, (soup.html or {}).get('lang', ''))
    ctag = soup.find('link', rel=lambda v: v and 'canonical' in v)
    target = urljoin(url, ctag.get('href', '')) if ctag else url
    target = canonical(target) if allowed(target, source) and urlsplit(target).path not in ('', '/') else canonical(url)
    signals = topics(headline + '\n' + body[:14000])
    return dict(canonical_url=target, original_url=url,
        # Keep a bounded headline only, never the downloaded article body/photos.
        headline=' '.join(headline.split()[:20]), content_sha256=hashlib.sha256(body.encode()).hexdigest(),
        headline_sha256=hashlib.sha256(fold(headline).encode()).hexdigest(),
        published_at=chosen['value'] if chosen and not conflict else None,
        date_precision=chosen['precision'] if chosen and not conflict else 'unknown',
        publication_evidence=dates, date_conflict=conflict,
        updated_at=updated[0]['value'] if updated else None,
        language=language, extraction_fallback=fallback, body_words=len(body.split()), **signals)

def discover(content, url, source):
    """RSS, Atom, sitemap and permitted HTML listing discovery; dates are hints only."""
    output, channels, next_pages = [], [], []
    stripped = content.lstrip()
    is_xml = stripped.startswith('<?xml') or re.match(r'<(?:rss|feed|urlset|sitemapindex)\b', stripped)
    if is_xml:
        if '<!DOCTYPE' in stripped.upper() or '<!ENTITY' in stripped.upper():
            raise ValueError('XML document type and entity declarations are not supported')
        root = ElementTree.fromstring(content)
        for node in root.iter():
            tag = node.tag.rsplit('}', 1)[-1]
            if tag not in ('item', 'entry', 'url', 'sitemap'): continue
            fields = {c.tag.rsplit('}', 1)[-1]: c for c in node}
            link = fields.get('link')
            href = link.get('href') or link.text if link is not None else fields.get('loc').text if fields.get('loc') is not None else None
            if not href or not allowed(urljoin(url, href), source): continue
            if tag == 'sitemap': channels.append(urljoin(url, href)); continue
            title = clean(fields['title'].text) if fields.get('title') is not None else ''
            date = next((clean(fields[k].text) for k in ('pubDate', 'published') if fields.get(k) is not None), None)
            output.append(dict(url=canonical(urljoin(url, href)), headline=' '.join(title.split()[:20]), listing_date_hint=date))
    else:
        soup = BeautifulSoup(content, 'html.parser')
        for link in soup.select('link[rel="alternate"]'):
            if any(t in link.get('type', '') for t in ('rss', 'atom')):
                channels.append(urljoin(url, link.get('href', '')))
        for link in soup.select('a[href], link[rel="next"]'):
            target = urljoin(url, link.get('href', ''))
            if not allowed(target, source): continue
            if 'next' in link.get('rel', []): next_pages.append(target); continue
            if re.search(r'\.(pdf|jpg|png|svg|zip|xlsx?|mp[34])(?:\?|$)', target, re.I): continue
            title = clean(link.get_text(' ', strip=True))
            if len(title.split()) < 5 or len(title) > 400: continue
            if not topics(title)['agriculture_signal'] and not topics(title)['transmission_channel']: continue
            output.append(dict(url=canonical(target), headline=' '.join(title.split()[:20]), listing_date_hint=None))
    return list({c['url']: c for c in output}.values()), list(dict.fromkeys(channels)), list(dict.fromkeys(next_pages))

LIFETIMES = {'general': 14*24, 'market_trend': 7*24, 'spot_price': 48,
             'weather_operational': 48, 'road_disruption': 48, 'seasonal_outlook': 14*24,
             'sanitary_alert': 14*24, 'event': 14*24, 'research': 14*24, 'policy': 14*24}

def expiry(published, kind, explicit_end=None):
    if kind not in LIFETIMES: raise ValueError('Unknown story kind')
    dt = datetime.fromisoformat(published)
    end = dt + timedelta(hours=LIFETIMES[kind])
    if explicit_end:
        cutoff = datetime.fromisoformat(explicit_end)
        if cutoff.tzinfo is None: raise ValueError('Deadline requires timezone')
        end = min(end, cutoff)
    review = min(end, dt + timedelta(hours=24)) if kind in ('weather_operational', 'road_disruption', 'sanitary_alert', 'seasonal_outlook') else end
    return end.isoformat(), review.isoformat()

def diverse(stories, limit=5, max_publisher=2):
    """Round-robin source groups; caps independent editorial owners, not domains."""
    groups = {}
    for s in sorted(stories, key=lambda s: (s.get('priority', 0), s.get('published_at', '')), reverse=True):
        groups.setdefault(s['source_group'], []).append(s)
    selected, publishers, clusters = [], {}, set()
    while groups and len(selected) < limit:
        for group in list(groups):
            s = groups[group].pop(0)
            if not groups[group]: del groups[group]
            owner, cluster = s['publisher_id'], s.get('event_id') or s['id']
            if publishers.get(owner, 0) >= max_publisher or cluster in clusters: continue
            selected.append(s); publishers[owner] = publishers.get(owner, 0)+1; clusters.add(cluster)
            if len(selected) == limit: break
    return selected
