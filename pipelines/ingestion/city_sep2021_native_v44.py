"""PRIVATE v44 source-bound native extension; no Poppler runtime dependency.

Derives every amount/identity from exact PDF glyphs. A digest-only resource is
independently checked against Poppler full17 fields in the private test suite.
Not wired into deployed worker.
"""
import bisect
import copy
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pdfplumber

from . import city_sep2021_native as v43

VERSION='city-v8:sep2021-native-geometry-v44-private-v1'
PINS_SHA='f2153682db653b76753de301541607a8eedfb732c8c1b6df3a5b0f8a1589ca7e'
POPAYAN='301dff168ebe1cc357fd2bf0cc84409b28410e418ff57a43250c05b78a846e66'
BOGOTA='f5d39758d2921991b120381bafbfa2f3dd3cdd07cbbdfc8611f60d51c3a5dd93'
P=Path(__file__).resolve().parent

def _pins():
    path=P/'city_sep2021_v44_pins.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=PINS_SHA:
        raise ValueError('v44 independent source pins changed')
    pins=json.loads(path.read_text())
    if pins['version']!=VERSION or pins['parent_sha256']!=v43.PARENT_SHA:
        raise ValueError('v44 source identity changed')
    if hashlib.sha256((P/'city_sep2021_native.py').read_bytes()).hexdigest()!=pins['v43_module_sha256']:
        raise ValueError('v43 parser implementation changed')
    return pins

def _geometry_cells(page, y, bounds, *, wrapped):
    """Reassemble same source row/columns from native glyph positions only."""
    cells=[[] for _ in range(7)]
    y_min,y_max=(-7,15) if wrapped else (-5,11)
    for word in page.extract_words():
        ym=(word['top']+word['bottom'])/2
        if not y+y_min<=ym<=y+y_max:continue
        x=(word['x0']+word['x1'])/2
        col=bisect.bisect_right(bounds,x)-1
        if 0<=col<7:
            cells[col].append((word['top'],word['x0'],word['text']))
    return [' '.join(text for _,__,text in sorted(words)) for words in cells]

def _selected(review,did):
    return (did==POPAYAN and review['page']==2 and review['round']==1
            and review['reasons']==['native_decoder_identity_disagreement']) or (
            did==BOGOTA and review['page']==2 and review['round'] in (1,2)
            and review['literal_cells'][0]=='Uva Isabela'
            and review['reasons']==['native_decoder_identity_disagreement'])

def parse_exact_parent(source_url,parent_bytes):
    if source_url!=v43.URL:return None
    pins=_pins()
    prior=v43.parse_exact_parent(source_url,parent_bytes)
    if prior is None:raise ValueError('v43 source gate unexpectedly skipped')
    original=copy.deepcopy(prior)
    new=[]
    with zipfile.ZipFile(io.BytesIO(parent_bytes)) as bundle:
        source_manifest=v43.registry()
        for child in prior['children']:
            did=child['child_sha256']
            if did not in (BOGOTA,POPAYAN):continue
            spec=next(c for c in source_manifest['children'] if c['document_id']==did)
            child_bytes=bundle.read(spec['entry_name'])
            if hashlib.sha256(child_bytes).hexdigest()!=did:
                raise ValueError('v44 child source bytes changed')
            with pdfplumber.open(io.BytesIO(child_bytes)) as pdf:
                page=pdf.pages[1]
                bounds=v43._bounds(pdf.pages[0])
                if [round(x,2) for x in bounds]!=child['derived_bounds']:
                    raise ValueError('v44 native table bounds changed')
                remaining=[]
                for review in child['reviews']:
                    if not _selected(review,did):
                        remaining.append(review)
                        continue
                    source_cells=_geometry_cells(page,review['native_y'],bounds,wrapped=(did==BOGOTA))
                    if [''.join(x.split()) for x in source_cells]!=[
                            ''.join(x.split()) for x in review['literal_cells']]:
                        raise ValueError('v44 native glyph geometry or adjacent row changed')
                    if did==BOGOTA and source_cells[2]!='25UND- 450GR':
                        raise ValueError('v44 wrapped source unit changed')
                    state,low,high=v43._range(*review['range_literal'])
                    if state!='positive':raise ValueError('v44 source price not supported')
                    fields=v43._row(review['page'],review['native_y'],review['round'],
                                    review['category_literal'],source_cells,
                                    v43.EXPECTED_MARKETS[did],low,high)
                    if fields is None or len(fields)!=17:
                        raise ValueError('v44 complete source identity missing')
                    source={key:value for key,value in review.items()
                            if key not in ('reasons','independent_poppler_identity_cells')}
                    priced={'source':source,'fields_17':fields}
                    child['priced'].append(priced)
                    new.append(priced)
                child['reviews']=remaining
            child_pin=next(p for p in pins['children'] if p['child_sha256']==did)
            if child_pin['count']!={k:len(child[k]) for k in ('priced','reviews','noquotes','blanks')}:
                raise ValueError('v44 child accounting changed')
    if len(new)!=29 or sum(len(c['reviews']) for c in prior['children'])!=75:
        raise ValueError('v44 geometry selection changed')
    old=[r for c in original['children'] for r in c['priced']]
    if v43.object_digest([r['fields_17'] for r in old])!=pins['old_836_sha256']:
        raise ValueError('v44 old native rows changed')
    if v43.object_digest([r['fields_17'] for r in new])!=pins['new_29_full17_sha256']:
        raise ValueError('v44 independently reviewed full17 oracle differs')
    if v43.object_digest([r['source'] for r in new])!=pins['new_29_evidence_sha256']:
        raise ValueError('v44 source evidence changed')
    for child in prior['children']:
        expected=next(p for p in pins['children'] if p['child_sha256']==child['child_sha256'])
        if [round(x,2) for x in child['derived_bounds']]!=expected['derived_bounds']:
            raise ValueError('v44 source table bounds changed')
        observed={'priced_17_sha256':v43.object_digest([x['fields_17'] for x in child['priced']]),
                  'priced_evidence_sha256':v43.object_digest([x['source'] for x in child['priced']]),
                  'review_evidence_sha256':v43.object_digest(child['reviews']),
                  'noquote_evidence_sha256':v43.object_digest(child['noquotes']),
                  'blank_evidence_sha256':v43.object_digest(child['blanks']),
                  'count':{k:len(child[k]) for k in ('priced','reviews','noquotes','blanks')}}
        if any(observed[k]!=expected[k] for k in observed):
            raise ValueError('v44 per-child native source oracle differs')
    counts={'priced':sum(len(c['priced']) for c in prior['children']),
            'reviews':sum(len(c['reviews']) for c in prior['children']),
            'noquotes':sum(len(c['noquotes']) for c in prior['children']),
            'blanks':sum(len(c['blanks']) for c in prior['children']),
            'lines':prior['counts']['lines'],'category_headings':prior['counts']['category_headings'],
            'pages':prior['counts']['pages']}
    if counts!=pins['counts']:
        raise ValueError('v44 parent source accounting differs')
    return {**prior,'parser_revision':VERSION,'counts':counts}
