"""Download official reference data with a recorded URL for every cached response."""
import concurrent.futures,json,subprocess
from pathlib import Path
from urllib.parse import urlencode,urljoin
from bs4 import BeautifulSoup
HERE=Path(__file__).resolve().parent; CACHE=HERE/'cache';CACHE.mkdir(exist_ok=True)
URLS=json.loads((CACHE/'download-urls.json').read_text()) if (CACHE/'download-urls.json').exists() else {}
APTITUDES=['cafe','aguacate_hass','papa_s1','papa_s2','platano','cacao','frijol_comercial','maiz_s1','maiz_s2','yuca','banano','pimenton','cebolla_bulbo_s1','cebolla_bulbo_s2','arroz_secano']
def download(url,name):
 p=CACHE/name
 if not p.exists():
  temp=p.with_suffix(p.suffix+'.tmp')
  subprocess.run(['curl','-fsSL','--retry','2','--max-time','180',url,'-o',str(temp)],capture_output=True,check=True)
  temp.replace(p)
 URLS[name]=url
 return p

def aptitude(key):
 base=f'https://sig.upra.gov.co/server/rest/services/aptitud_uso_suelo/aptitud_{key}/MapServer/0'
 download(base+'?f=pjson',f'aptitude-{key}-meta.json')
 pages=[]
 # This server ignores pagination for grouped statistics. Bound each query by department.
 departments=['05','08','11','13','15','17','18','19','20','23','25','27','41','44','47','50','52','54','63','66','68','70','73','76','81','85','86','88','91','94','95','97','99']
 for offset in range(0,len(departments),2):
  params={'where':"cod_depart IN ("+','.join("'"+d+"'" for d in departments[offset:offset+2])+")",'outStatistics':json.dumps([{'statisticType':'sum','onStatisticField':'area_ha','outStatisticFieldName':'area_ha'}]),'groupByFieldsForStatistics':'cod_dane_mpio,aptitud','orderByFields':'cod_dane_mpio,aptitud','returnGeometry':'false','resultRecordCount':2000,'f':'json'}
  url=base+'/query?'+urlencode(params)
  p=download(url,f'aptitude-{key}-dept-{offset}.json');response=json.loads(p.read_text())
  if 'error' in response:raise ValueError((key,response['error']))
  pages.append({'url':url,'response':response})
  if response.get('exceededTransferLimit'):raise ValueError('Truncated department statistics')
 (CACHE/f'aptitude-{key}.json').write_text(json.dumps({'pages':pages},ensure_ascii=False))
 print('Suitability',key,sum(len(p['response']['features']) for p in pages),flush=True)

def main():
 for name,url in json.loads((HERE/'reference-downloads.json').read_text()).items():download(url,name);print('Reference',name,flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(aptitude,APTITUDES))
 soil='https://www.datos.gov.co/resource/ch4u-f3i5.json?'+urlencode({'$select':'secuencial,fecha_de_an_lisis,departamento,municipio,cultivo,ph_agua_suelo,materia_organica','$order':'secuencial','$limit':150000})
 p=download(soil,'soils.json');print('Soil samples',len(json.loads(p.read_text())),flush=True)
 for y in [2023,2024]:
  url=f'https://upra.gov.co/es-co/eva/eva-{y}'
  p=download(url,f'upra-eva{y}.html')
  for a in BeautifulSoup(p.read_text(),'html.parser').select('a[href]'):
   href=a['href'];text=a.get_text(' ',strip=True).lower()
   if href.endswith('.pdf') and any(w in text for w in ['boletín de frijol','boletín de tomate','costos papa primer','boletín de yuca','boletín de cacao','boletín de plátano','boletín de arveja','boletín de granadilla','boletín cebolla junca','boletín de cebolla bulbo']):
    name='cost-'+href.split('/')[-1];download(urljoin(url,href),name);print('Cost reference',name,flush=True)
 (CACHE/'download-urls.json').write_text(json.dumps(URLS,indent=2))
if __name__=='__main__':
 try:main()
 finally:(CACHE/'download-urls.json').write_text(json.dumps(URLS,indent=2))
