"""Verify native unit glyphs bleeding into a city PDF's first price cell.

Call after default page.extract_tables(). Ambiguous candidates remain literal
so the ordinary parser can retain a review; no units or money are guessed.
"""
import re

_PRICE = re.compile(r"^([rRcC]|G\s*R|C\s*C|\d\s*G\s*R)\s*(\d+(?:\.\d{3})*(?:,\d+)?|-)$")
_NUMERIC = re.compile(r"\d+(?:\.\d{3})*(?:,\d+)?")


def _chars_in(page, box):
    return sorted((c for c in page.chars if c['text'].strip()
        and box[0] <= (c['x0']+c['x1'])/2 <= box[2]
        and box[1] <= (c['top']+c['bottom'])/2 <= box[3]),key=lambda c:c['x0'])


def _baseline(chars):
    if not chars:return False
    first=chars[0]
    return all(abs(c['top']-first['top'])<=.25
        and abs(c['bottom']-first['bottom'])<=.25
        and abs(c['size']-first['size'])<=.2
        and c['fontname']==first['fontname'] for c in chars)


def _gap(a,b):return b['x0']-a['x1']


def _one_cell(page,row,cells):
    if len(row)<7 or len(cells)<7 or cells[2] is None or cells[3] is None:return None
    unit=row[2] or '';price=row[3] or '';high=row[4] or ''
    match=_PRICE.fullmatch(price.strip())
    if not match:return None
    prefix=''.join(match[1].split());amount=match[2]
    if amount=='-' and high.strip()!='-':return None
    if amount!='-' and not _NUMERIC.fullmatch(high.strip()):return None
    ub,pb=cells[2],cells[3]
    if abs(ub[2]-pb[0])>.5 or abs(ub[1]-pb[1])>.5 or abs(ub[3]-pb[3])>.5:return None
    uc=_chars_in(page,ub);pc=_chars_in(page,pb)
    if not uc or len(pc)<len(prefix)+1:return None
    if ''.join(c['text'] for c in uc)!=''.join(unit.split()):return None
    if ''.join(c['text'] for c in pc)!=''.join(price.split()):return None
    overflow=pc[:len(prefix)];money=pc[len(prefix):]
    if ''.join(c['text'] for c in overflow)!=prefix or ''.join(c['text'] for c in money)!=amount:return None
    preceding=uc[-1]
    if preceding['text']!=unit.strip()[-1]:return None
    if not _baseline([preceding,*overflow,*money]):return None
    if not -.1<=_gap(preceding,overflow[0])<=3.5:return None
    if any(not -.1<=_gap(a,b)<=3.5 for a,b in zip(overflow,overflow[1:])):return None
    money_gap=_gap(overflow[-1],money[0])
    if not 5<=money_gap<=(45 if amount=='-' else 30):return None
    if any(not -.3<=_gap(a,b)<=1.5 for a,b in zip(money,money[1:])):return None
    # Only a source-specified compound gram or cubic-centimetre suffix is
    # reconstructed. Leave its printed quantity and native case untouched.
    if unit.endswith(('G','g')) and prefix in ('r','R'):
        fixed_unit=unit+prefix
    elif unit.endswith(('C','c')) and prefix in ('C','c'):
        fixed_unit=unit+prefix
    elif unit[-1:].isdigit() and prefix in ('GR','CC'):
        fixed_unit=unit+' '+prefix
    elif unit[-1:].isdigit() and re.fullmatch(r'\dGR', prefix):
        # One visible last quantity digit crossed the table border before the
        # source's literal gram suffix (for example, 50 + 0GR = 500 GR).
        fixed_unit=unit+prefix[0]+' '+prefix[1:]
    else:return None
    return fixed_unit,amount


def verified_city_unit_overflow(page,tables,*,repair_prices=True):
    if not repair_prices:return tables
    geometry=page.find_tables()
    if len(geometry)!=len(tables):return tables
    if any(len(t.rows)!=len(rows) or any(len(r.cells)!=len(cells)
        for r,cells in zip(t.rows,rows)) for t,rows in zip(geometry,tables)):
        return tables
    for table,shape in zip(tables,geometry):
        for row,shape_row in zip(table,shape.rows):
            fixed=_one_cell(page,row,shape_row.cells)
            if fixed:row[2],row[3]=fixed
    return tables
