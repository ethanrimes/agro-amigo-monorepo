"""Archive official GIS layer schemas and legends. No observation/history deletion.
Run: .venv/bin/python pipelines/spatial/import_layers.py
"""
import concurrent.futures, hashlib, json
from pathlib import Path
import certifi, psycopg, requests
from psycopg.types.json import Jsonb
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def fetch(layer):
    url=f"{layer['service']}/{layer['layer']}?f=pjson"
    response=requests.get(url,timeout=60);response.raise_for_status()
    meta=response.json()
    if 'error' in meta or not meta.get('fields'): raise ValueError(f"Unavailable layer: {layer['id']}")
    names={f['name'] for f in meta['fields']}
    assert set(layer['valueFields']).issubset(names),layer['id']
    if layer.get('monthField'): assert layer['monthField'] in names
    renderer=meta.get('drawingInfo',{}).get('renderer',{})
    legend=renderer.get('uniqueValueInfos',[])
    if not legend: legend=[c for g in renderer.get('uniqueValueGroups',[]) for c in g['classes']]
    entries=[]
    for v in legend:
        color=v.get('symbol',{}).get('color')
        if color and v.get('label') and not any(e['label']==v['label'] for e in entries):
            entries.append({'label':v['label'],'color':'#'+''.join(f'{round(c):02x}' for c in color[:3])})
    content=response.content;did=hashlib.sha256(content).hexdigest()
    definition={**layer,'legend':entries,'documentId':'spatial-'+did}
    records=[{'nombre_de_capa':meta['name'],'entidad':layer['publisher'],'periodo':layer['period'],'escala_y_limitaciones':layer['note'],'campos':[f"{f['name']}: {f['alias']}" for f in meta['fields'] if f['name'] in layer['valueFields']]}]
    return definition,meta,content,did,url,records

def main():
    layers=json.loads((HERE/'layers.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(fetch,layers))
    c=json.loads((ROOT/'.azure-local/database.json').read_text())
    with psycopg.connect(host=c['host'],dbname=c['database'],user=c['user'],password=c['password'],sslmode='verify-full',sslrootcert=certifi.where(),connect_timeout=20) as db:
        db.execute((HERE/'schema.sql').read_text())
        for layer,meta,content,did,url,records in results:
            db.execute('INSERT INTO spatial_snapshot(id,cache_key,title,publisher,source_url,reference_period,content,records,metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING',(did,'schema:'+layer['id'],layer['title']+' — descripción original del geoservicio',layer['publisher'],url,layer['period'],content,Jsonb(records),Jsonb({'note':layer['note'],'layer':layer,'schema':meta})))
            db.execute('INSERT INTO spatial_layer VALUES (%s,%s,%s) ON CONFLICT(id) DO UPDATE SET definition=excluded.definition,document_id=excluded.document_id',(layer['id'],Jsonb(layer),did))
            print(layer['id'],len(content),'bytes archived',len(layer['legend']),'legend categories',flush=True)
if __name__=='__main__':main()
