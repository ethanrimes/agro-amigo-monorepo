"""Read-only whole-source adjudication for one reviewed Armenia OCR child.

Projects copies of two retained readings; source bytes and cached JSON remain
immutable. Any changed source, note, task identity, or typed row fails closed.
"""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json

import pdfplumber

from .city_reports import parse_city_pages
from .pdf_sources import VerifiedPDFPage
from .ocr import VERSION as OCR_VERSION, normalize

PDF_ID = 'f7b1980c7b511bf7a12fdfb325862df6ab64b35571a7ccd935f9306dbc21a412'
PARENT_ID = '503a044d44069e1bbb39d18f5082c86cc1489ad697c823c1345920cda56b8a2b'
URL = 'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-25ene2024.zip'
ENTRY = 'Armenia, Mercar 25-1-2024.pdf'
OLD_ERROR = 'Independent OCR readings disagree or contain uncertainty; not published as prices'
PAGE = {
  1: {
    'image_id':'c448dee7e0e84b348c13789bcef36edc92594e1b38c8e616007637d83c04f1f3',
    'reading_sha':{
      0:'f977deac859493b2cfd2000c8f5dce12725bf4ba8efddc39fd42eafccccfd424',
      1:'c4260cc1bb9bd968739bbc1f23049c4605674716d3fcf2d97cef597b046eb0cb',
    },
    'notes0':[
      "The word 'cartÓn' is written with a capital 'Ó' in the 'Presentación' column.",
      "The category header 'PIÁtano' is written with capital 'I' and 'Á'.",
    ],
    'printed_typography':{'cartÓn':'cartón','PIÁtano':'Plátano'},
    'expected_rows':37,'expected_table_lines':49,
  },
  2: {
    'image_id':'b011257b884b377b07c4e8479efda3193feacb5f2c9f8399d4aa08132f93ae7b',
    'reading_sha':{
      0:'c2ba76fa321fa13ef9a62b850674759e40fe5602906073192e9ca6a8e8b93cf2',
      1:'7b59fed38741a9ad0e57cd4a58b0a8c27d97d83df12ced7b59ec38e9883a7dd6',
    },
    'notes0':["The word 'cartÓn' in 'Caja de cartÓn' is spelled with a capital 'Ó' in the original document."],
    'printed_typography':{'cartÓn':'cartón'},
    'expected_rows':22,'expected_table_lines':29,
  },
}
EXPECTED_RAW_DIFFERENCES = {
    1: [(14,1,'Caja de cartÓn','Caja de cartón'),
        (21,1,'Caja de cartÓn','Caja de cartón'),
        (22,1,'Caja de cartÓn','Caja de cartón'),
        (23,1,'Caja de cartÓn','Caja de cartón'),
        (29,1,'Caja de cartÓn','Caja de cartón'),
        (32,1,'Caja de cartÓn','Caja de cartón'),
        (36,0,'PIÁtano','PlÁtano')],
    2: [],
}
EXPECTED_ROWS_SHA = '1d36c3c84654d674ff940feb365cee8c41ed046b0e79af2df6b2debc4d9eea7a'


def digest_result(result):
    return sha256(json.dumps(result, ensure_ascii=False, sort_keys=True,
                             separators=(',',':')).encode()).hexdigest()


def insist(condition, reason):
    if not condition:
        raise ValueError(reason)


def raw_differences(a,b):
    insist(len(a['tables'])==len(b['tables'])==1, 'table_count_changed')
    first,second=a['tables'][0],b['tables'][0]
    insist(len(first)==len(second) and all(len(x)==len(y)==7 for x,y in zip(first,second)),
           'table_shape_changed')
    return [(ri,ci,x,y) for ri,(ra,rb) in enumerate(zip(first,second))
            for ci,(x,y) in enumerate(zip(ra,rb)) if x!=y]


def project(result):
    copy=deepcopy(result)
    for table in copy['tables']:
        for row in table:
            for index,cell in enumerate(row):
                if cell=='Caja de cartÓn':row[index]='Caja de cartón'
                elif cell in ('PIÁtano','PlÁtano'):row[index]='Plátano'
    # Leave review_notes in the immutable input and this copy. The only
    # permitted notes are checked exactly by adjudicate() before parsing.
    return copy


def rows_digest(rows):
    return sha256(json.dumps([[str(v) for v in row] for row in rows],
                             ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def adjudicate(pdf_bytes, tasks, cached):
    insist(sha256(pdf_bytes).hexdigest()==PDF_ID, 'original_pdf_sha_changed')
    with pdfplumber.open(__import__('io').BytesIO(pdf_bytes)) as pdf:
        insist(len(pdf.pages)==2 and all(not (page.extract_text() or '') for page in pdf.pages),
               'original_not_exact_two_image_only_pages')
    insist(len(tasks)==2 and len(cached)==4 and OCR_VERSION=='gemini-image-ocr-v2',
           'task_or_ocr_version_changed')
    by_task={t['source_page']:t for t in tasks}
    insist(set(by_task)=={1,2}, 'task_page_set_changed')
    by_reading={(r['image_id'],r['reading']):r for r in cached}
    insist(len(by_reading)==4, 'reading_pair_not_exact')
    projected={}
    raw_summary={}
    for page in (1,2):
        task=by_task[page]; expected=PAGE[page]
        insist(task['document_id']==PDF_ID and task['source_locator']==f'PDF page {page}' and
               task['image_id']==expected['image_id'] and task['error']==OLD_ERROR and
               task['source_url']==URL and task['media_type']=='application/pdf' and
               task['kind']=='original' and task['metadata'].get('parents')==[PARENT_ID] and
               task['metadata'].get('archive_entry')==ENTRY and
               task['metadata'].get('ingestion_kind')=='city-pdf',
               'task_or_source_binding_changed')
        pair=[]
        for reading in (0,1):
            item=by_reading.get((expected['image_id'],reading))
            insist(item is not None and item['version']==OCR_VERSION,
                   'reading_identity_changed')
            result=item['result']
            insist(digest_result(result)==expected['reading_sha'][reading],
                   'retained_ocr_result_changed')
            insist(result['review_notes']==(expected['notes0'] if reading==0 else []),
                   'new_or_uncertain_review_note')
            insist(len(result['tables'])==1 and
                   len(result['tables'][0])==expected['expected_table_lines'] and
                   not any('?' in str(c) for t in result['tables'] for row in t for c in row),
                   'table_size_or_uncertain_cell_changed')
            insist('Armenia, Mercar' in result['text'] and
                   '25 de Enero de 2024' in result['text'] and
                   f'Pagina {page} de 2' in result['text'],
                   'heading_date_or_page_changed')
            pair.append(result)
        differences=raw_differences(*pair)
        insist(differences==EXPECTED_RAW_DIFFERENCES[page], 'raw_cell_difference_changed')
        raw_summary[page]={'table_lines':len(pair[0]['tables'][0]),
                           'raw_differences':len(differences),
                           'reading_sha':expected['reading_sha'],
                           'descriptive_notes_preserved':expected['notes0']}
        projected[page]=[project(r) for r in pair]
    results=[]
    for reading in (0,1):
        source_pages=[VerifiedPDFPage(projected[p][reading]) for p in (1,2)]
        rows=list(parse_city_pages(source_pages,heading=source_pages[0].extract_text()))
        insist(len(rows)==59 and all(
            sum(r[0].startswith(f'PDF page {p},') for r in rows)==PAGE[p]['expected_rows']
            for p in (1,2)), 'typed_row_count_or_page_locator_changed')
        insist(all(len(r)==17 and r[1]==date(2024,1,25) and
                   normalize(r[4])==normalize('Armenia, Mercar') and
                   r[11]>0 and r[12]>0 and r[7]>0 for r in rows),
               'typed_identity_quantity_or_price_invalid')
        results.append(rows)
    insist(results[0]==results[1], 'full_17_field_typed_readings_disagree')
    insist(rows_digest(results[0]) == EXPECTED_ROWS_SHA, 'independent_full_17_field_oracle_changed')
    insist(sum(r[5]=='Tubérculos, raíces y plátanos > Plátano' for r in results[0])==2 and
           all('Piátano' not in r[5] for r in results[0]),
           'bounded_category_projection_changed')
    return {'status':'source_proof_only',
            'source_pdf_sha256':PDF_ID,'parent_zip_id':PARENT_ID,'source_url':URL,'archive_entry':ENTRY,
            'page_image_ids':{p:PAGE[p]['image_id'] for p in (1,2)},
            'raw':raw_summary,'projected_full17_sha256':rows_digest(results[0]),
            'projected_observations':59,'page_observations':{1:37,2:22},
            'projected_category_rows':2,
            'rounds':{1:sum(r[9]==1 for r in results[0]),2:sum(r[9]==2 for r in results[0])},
            'projection_only':{'Caja de cartÓn':'Caja de cartón',
                               'PIÁtano/PlÁtano':'Plátano'},
            'raw_provider_results_mutated':False}
