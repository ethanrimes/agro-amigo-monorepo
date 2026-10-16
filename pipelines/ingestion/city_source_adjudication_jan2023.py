"""Source-bound registration for the Jan 3, 2023 Medellín CMA ZIP member."""
from datetime import date
from pathlib import Path
from . import city_source_adjudication as engine

URL='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol-reg-03-01-2023.zip'
PARENT='220e0d23060a337f4307b5f93e729fa4f777e89e4373228cb6552a68b8da2c04'
DAY=date(2023,1,3)
VERSION=engine.VERSION
# Source proof files are packaged with the ingestion runtime. Cached provider
# readings remain in the retained database and are not packaged here.
BASE=Path(__file__).resolve().parent/'testdata/city_cma_20230103_adjudication'
CMA=BASE
VISUAL=BASE
FILES=dict(spec=CMA/'spec.json',
           grid=CMA/'source-grid.json',
           projection=CMA/'projection.json',
           diff=CMA/'source-diff.json',rendered_dir=VISUAL)

def retained_exact_parent(db,url,kind,expected_version):
    if (url,kind,expected_version)!=(URL,'city-zip',VERSION):return None
    row=db.execute('''SELECT a.kind,a.observed_on,a.document_id,a.status,
      d.kind,d.source_url,d.media_type,d.reference_period,d.metadata,d.content
      FROM ingestion_asset a LEFT JOIN source_document d ON d.id=a.document_id
      WHERE a.url=%s''',(URL,)).fetchone()
    if row is None:return None
    if row[2]!=PARENT:
        # A distinct immutable publisher revision keeps ordinary discovery.
        return None
    engine.require(row[:3]==('city-zip',DAY,PARENT)
       and row[3] in ('review','failed','pending','complete')
       and row[4:8]==('original',URL,'application/zip',DAY.isoformat())
       and isinstance(row[8],dict)
       and row[8].get('ingestion_kind')=='city-zip'
       and row[8].get('retention')=='permanent'
       and row[8].get('original_filename')==URL.rsplit('/',1)[-1],
       'registered parent asset metadata changed')
    body=bytes(row[9])
    engine.checked_registry_inputs(FILES['spec'],FILES['grid'],FILES['projection'],
                                   FILES['diff'],FILES['rendered_dir'],body)
    return body

def maybe_publish(db,url,parent_bytes,parent_id):
    if url!=URL or parent_id!=PARENT:return None
    result=engine.publish_registered_exact_child(db,url,parent_bytes,parent_id,FILES)
    if result['status']=='held':raise ValueError(result['reason'])
    # Return None: ordinary city ZIP publisher sees only CMA's 206-row exact
    # checkpoint and handles all other children under the same version.
    return None
