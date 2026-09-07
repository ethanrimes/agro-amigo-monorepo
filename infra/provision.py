"""Provision isolated demo resources. Credentials stay in ignored, owner-only files."""
import argparse,json,os,secrets,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'.azure-local'
SUB='9a04b64b-af19-4519-be50-56ec2acbd855'
GROUP='agroamigo-demo-rg'
REGION='northcentralus'
SERVER='agroamigo-demo-pg-9a04'
APP='agroamigo-demo-9a04'
def az(*args):
    result=subprocess.run(['az',*args,'--subscription',SUB,'--only-show-errors','-o','json'],capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout) if result.stdout.strip() else None
def private_write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f: f.write(text)
def provision_db():
    LOCAL.mkdir(exist_ok=True)
    credentials=LOCAL/'database.json'
    if credentials.exists(): config=json.loads(credentials.read_text())
    else:
        config={'host':f'{SERVER}.postgres.database.azure.com','database':'agroamigo','user':'agroadmin','password':secrets.token_urlsafe(36)+'Aa1!','appPassword':secrets.token_urlsafe(36)+'Aa1!'}
        private_write(credentials,json.dumps(config))
    ip=subprocess.check_output(['curl','-fsS','https://api.ipify.org'],text=True).strip()
    print('Provisioning PostgreSQL (Burstable B1ms, 32 GiB), restricted to this client IP.',flush=True)
    az('postgres','flexible-server','create','-g',GROUP,'-n',SERVER,'-l',REGION,'--tier','Burstable','--sku-name','Standard_B1ms','--storage-size','32','--version','16','--admin-user',config['user'],'--admin-password',config['password'],'--public-access',ip,'--backup-retention','7','--tags','project=agroamigo','environment=demo','--yes')
    az('postgres','flexible-server','db','create','-g',GROUP,'--server-name',SERVER,'--name',config['database'])
    print('Database created.',flush=True)
def provision_web():
    print('Provisioning Linux App Service B1.',flush=True)
    az('appservice','plan','create','-g',GROUP,'-n','agroamigo-demo-plan','--is-linux','--sku','B1','-l',REGION)
    app=az('webapp','create','-g',GROUP,'-p','agroamigo-demo-plan','-n',APP,'--runtime','NODE:22-lts')
    az('webapp','update','-g',GROUP,'-n',APP,'--https-only','true')
    az('webapp','config','set','-g',GROUP,'-n',APP,'--startup-file','node apps/web/server.js','--min-tls-version','1.2','--ftps-state','Disabled','--always-on','true')
    print('Web host: https://'+app['defaultHostName'],flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('target',choices=['db','web']); args=parser.parse_args()
    (provision_db if args.target=='db' else provision_web)()
