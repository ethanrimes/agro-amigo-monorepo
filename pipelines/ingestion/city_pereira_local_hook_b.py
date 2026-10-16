"""One-original native table hook using the unchanged city-v8 parser API.

Only exact-SHA caller may use this module. It alters two verified heading
tokens in this PDF's page-local table view and geometrically repairs unit
glyphs at the cell boundary. The shared parser module is never monkeypatched.
"""
import copy
import io

import pdfplumber

from . import city_reports
from .city_pereira_unit_private import verified_city_unit_overflow


_HEADINGS = {10: ('Huevos y Lacteos','Lacteos y Huevos'),
             32: ('Pescados y Mariscos','Pescados')}
_CATEGORY_ROWS = {
    'PDF page 3,table 1,row 12,round 1': ('Lacteos y huevos','Huevos y lacteos'),
    **{f'PDF page 3,table 1,row {n},round 1': ('Pescados','Pescados y mariscos')
       for n in range(34,41)},
}


def parse_verified_pdf(data, day):
    repaired = set()
    observed_headings = set()
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages,1):
            extract = page.extract_tables

            def source_tables(*args, _page=page, _page_no=page_no, _extract=extract, **kwargs):
                tables = _extract(*args, **kwargs)
                if not kwargs:
                    before = copy.deepcopy(tables)
                    tables = verified_city_unit_overflow(_page,tables)
                    for table_no,(old,new) in enumerate(zip(before,tables),1):
                        for row_no,(a,b) in enumerate(zip(old,new),1):
                            if a!=b: repaired.add((_page_no,table_no,row_no))
                if _page_no == 3:
                    if len(tables)!=1 or len(tables[0])<=32:
                        raise ValueError('Pereira verified heading table shape changed')
                    for index,(literal,parser_group) in _HEADINGS.items():
                        if tables[0][index][0] != literal:
                            raise ValueError('Pereira verified printed heading changed')
                        tables[0][index][0] = parser_group
                        observed_headings.add((3,1,index+1))
                return tables

            # Per-page instance method only. No global class/module mutation,
            # so parallel ordinary city-v8 parsing remains unchanged.
            page.extract_tables = source_tables
        rows=list(city_reports.parse_city_pages(pdf.pages,day))
    if observed_headings!={(3,1,11),(3,1,33)} or len(repaired)!=15:
        raise ValueError('Pereira source heading/unit repair coverage changed')
    seen=set()
    output=[]
    for row in rows:
        value=list(row)
        if row[0] in _CATEGORY_ROWS:
            old,new=_CATEGORY_ROWS[row[0]]
            if row[5]!=old:
                raise ValueError('Pereira category context changed')
            value[5]=new
            seen.add(row[0])
        output.append(tuple(value))
    if seen!=set(_CATEGORY_ROWS):
        raise ValueError('Pereira exact category rows changed')
    return output
