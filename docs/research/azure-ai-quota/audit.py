"""Read-only subscription quota and regional catalog snapshot. No API keys saved."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import requests

SUBSCRIPTION = '9a04b64b-af19-4519-be50-56ec2acbd855'
ROOT = f'https://management.azure.com/subscriptions/{SUBSCRIPTION}'
OUT = Path(__file__).resolve().parent

def main():
    token = subprocess.check_output(['az', 'account', 'get-access-token', '--subscription', SUBSCRIPTION, '--resource', 'https://management.azure.com/', '--query', 'accessToken', '-o', 'tsv'], text=True).strip()
    headers = {'Authorization': 'Bearer ' + token}
    provider = requests.get(ROOT+'/providers/Microsoft.CognitiveServices', params={'api-version':'2021-04-01'}, headers=headers, timeout=40)
    provider.raise_for_status()
    regions = next(t['locations'] for t in provider.json()['resourceTypes'] if t['resourceType']=='accounts')
    regions = [x.lower().replace(' ','') for x in regions if x != 'Global']
    now = datetime.now(timezone.utc).isoformat()

    def fetch(region):
        base = ROOT+f'/providers/Microsoft.CognitiveServices/locations/{region}'
        record = {'region':region}
        payloads = {}
        for endpoint in ['usages', 'models']:
            version = '2026-07-01' if endpoint == 'usages' else '2024-10-01'
            r = requests.get(base+'/'+endpoint, params={'api-version':version}, headers=headers, timeout=60)
            record[endpoint+'_http_status'] = r.status_code
            if not r.ok:
                record[endpoint+'_error_code'] = r.json().get('error',{}).get('code')
                continue
            data = r.json()
            rows = data.get('value',[])
            for _ in range(5):
                if not data.get('nextLink'): break
                r = requests.get(data['nextLink'], headers=headers, timeout=60)
                r.raise_for_status(); data = r.json(); rows.extend(data.get('value',[]))
            payloads[endpoint] = rows
        by_usage = {}
        for entry in payloads.get('models',[]):
            model = entry.get('model',{})
            for sku in model.get('skus',[]):
                expiry = sku.get('deprecationDate')
                if expiry and expiry < now: continue
                usage = sku.get('usageName')
                if not usage: continue
                info = {'model':model.get('name'),'version':model.get('version'),'format':model.get('format'),'sku':sku.get('name'),'deprecation_date':expiry,'rate_limits':sku.get('rateLimits',[])}
                if info not in by_usage.setdefault(usage,[]): by_usage[usage].append(info)
        record['quotas'] = []
        for row in payloads.get('usages',[]):
            name = row.get('name',{}).get('value','')
            record['quotas'].append({'name':name,'description':row.get('name',{}).get('localizedValue'),'limit':row.get('limit'),'allocated':row.get('currentValue'),'remaining':row.get('limit',0)-row.get('currentValue',0),'unit':row.get('unit'),'scope_id':row.get('scopeId'),'scope_type':row.get('scopeType'),'catalog_matches':by_usage.get(name,[])})
        return record

    records = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        tasks = {pool.submit(fetch,r):r for r in regions}
        for future in as_completed(tasks):
            try: record = future.result()
            except Exception as e: record = {'region':tasks[future],'error_type':type(e).__name__}
            records.append(record)
            print(json.dumps({'region':record['region'],'quota_rows':len(record.get('quotas',[])),'model_status':record.get('models_http_status'),'error':record.get('error_type')}),flush=True)
    report = {'checked_utc':now,'subscription_id':SUBSCRIPTION,'scope':'Microsoft.CognitiveServices regional usage quotas joined to current regional model catalogs. No deployment or inference tests in this audit.','regions':sorted(records,key=lambda x:x['region'])}
    (OUT/'snapshot.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'regions':len(records),'saved':'docs/research/azure-ai-quota/snapshot.json'}),flush=True)

if __name__=='__main__': main()
