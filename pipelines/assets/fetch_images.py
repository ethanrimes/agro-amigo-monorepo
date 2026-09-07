"""Download attributed Commons photography for product families and market references.
Illustrative material photos are never presented as the packaging of a named brand.
The reviewed manifest is preserved. Only missing families are downloaded. Review every new image before publishing.
"""
import concurrent.futures, hashlib, json, re, sys, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'apps/web/public/images/library';OUT.mkdir(parents=True,exist_ok=True)
MANIFEST=ROOT/'apps/web/src/lib/image-library.json'
QUERIES={
'apple':'red apples fruit','blueberry':'blueberries fruit','badea':'Passiflora quadrangularis fruit','borojo':'Borojo fruit','fig':'fig fruit cut','plum':'plums fruit','coconut':'coconut fruit','curuba':'banana passionfruit fruit','peach':'peach fruit','feijoa':'feijoa fruit','strawberry':'strawberries fruit','granadilla':'Passiflora ligularis fruit','soursop':'soursop fruit','guava':'guava fruit','passionfruit':'passion fruit cut','kiwi':'kiwifruit cut','lime':'lime fruit','lulo':'Solanum quitoense fruit','mandarin':'mandarin oranges fruit','mango':'mango fruit','orange':'oranges fruit','papaya':'papaya fruit cut','watermelon':'watermelon fruit','pear':'pear fruit','pineapple':'pineapple fruit','pitaya':'pitahaya fruit','blackberry':'blackberries fruit','tamarillo':'tamarillo fruit','grape':'grapes fruit','uchuva':'Physalis peruviana fruit','melon':'cantaloupe melon','zapote':'Pouteria sapota fruit',
'garlic':'garlic bulbs','artichoke':'artichoke vegetable','celery':'celery vegetable','peas':'green peas pods','aubergine':'eggplant vegetable','broccoli':'broccoli vegetable','pumpkin':'pumpkin vegetable','zucchini':'zucchini vegetable','onion':'onion bulbs','spring-onion':'scallions vegetable','cilantro':'coriander leaves','cauliflower':'cauliflower vegetable','spinach':'spinach leaves vegetable','beans-green':'green beans vegetable','lettuce':'lettuce vegetable','corn':'maize cobs','cucumber':'cucumber vegetable','bell-pepper':'red bell pepper','beet':'beetroot vegetable','cabbage':'cabbage vegetable','carrot':'carrots vegetable','chayote':'chayote fruit','arracacha':'arracacha roots','cassava':'cassava roots','yam':'yam tuber','ullucus':'Ullucus tubers','rice':'white rice grains','lentils':'lentils seeds','beans':'red kidney beans','chickpeas':'chickpeas seeds','oats':'oat flakes','wheat':'wheat grains','peanut':'peanuts kernels','panela':'panela Colombia','sugar':'white sugar crystals','flour':'wheat flour','oil':'vegetable oil bottle','salt':'table salt','pasta':'dry pasta','chocolate':'chocolate bars','coffee-roasted':'roasted coffee beans','cheese':'fresh cheese','milk':'milk bottle','eggs':'chicken eggs','butter':'butter food','chicken':'raw chicken breast','pork':'raw pork meat','beef':'raw beef meat','fish':'fresh fish market','shrimp':'raw shrimp',
'market':'Paloquemao market Colombia fruit','corabastos':'Corabastos','paloquemao':'Paloquemao market','minorista':'Plaza Minorista Medellin','bazurto':'Mercado Bazurto Cartagena','alameda':'Galeria Alameda Cali','market-coffee':'coffee sacks warehouse','market-rice':'rice mill sacks',
'fertilizer':'fertilizer granules','compost':'compost soil','limestone':'agricultural lime powder','liquid-input':'liquid fertilizer bottle','bioinput':'biofertilizer','sulphur':'sulfur powder','potassium':'potassium chloride crystals',
}

def fetch(item,attempt=0):
    key,query=item
    time.sleep(3.2)
    headers={'User-Agent':'AgroAmigo/1.0 (public-data agriculture app; github.com/ethanrimes/agro-amigo-monorepo)'}
    try:
        r=requests.get('https://commons.wikimedia.org/w/api.php',params={'action':'query','format':'json','generator':'search','gsrsearch':query+' filetype:bitmap','gsrnamespace':6,'gsrlimit':5,'prop':'imageinfo','iiprop':'url|extmetadata|size','iiurlwidth':800},headers=headers,timeout=35);
        if r.status_code == 429 and attempt < 3:
            time.sleep(max(65,int(r.headers.get('Retry-After','65'))))
            return fetch(item,attempt+1)
        r.raise_for_status()
        pages=sorted(r.json().get('query',{}).get('pages',{}).values(),key=lambda p:p.get('index',100))
        for p in pages:
            i=p.get('imageinfo',[{}])[0];m=i.get('extmetadata',{});license=m.get('LicenseShortName',{}).get('value','')
            if not any(s in license for s in ['CC BY','CC0','Public domain']):continue
            if i.get('width',0)<400 or i.get('height',0)<250:continue
            url=i.get('thumburl',i.get('url','')).split('?')[0]
            if not re.search(r'\.(jpe?g|png|webp)$',url,re.I):continue
            photo=requests.get(url,headers=headers,timeout=45)
            if not photo.ok or not photo.headers.get('Content-Type','').startswith('image/'): continue
            if len(photo.content)>2500000:continue
            ext=url.rsplit('.',1)[-1].lower();path=OUT/f'{key}.{ext}';path.write_bytes(photo.content)
            clean=lambda k:BeautifulSoup(m.get(k,{}).get('value',''),'html.parser').get_text(' ',strip=True)
            return key,{'src':'/images/library/'+path.name,'title':p['title'].removeprefix('File:'),'source':i.get('descriptionurl'),'author':clean('Artist'),'license':license,'licenseUrl':m.get('LicenseUrl',{}).get('value',''),'description':clean('ImageDescription'),'sha256':hashlib.sha256(photo.content).hexdigest(),'illustrative':True}
        print('No licensed photo:',key,flush=True)
    except Exception as e: print('Image lookup failed:',key,type(e).__name__,str(e)[:180],flush=True)
    return key,None

def main():
    current=json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    todo=[x for x in QUERIES.items() if x[0] not in current]
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        for key,result in pool.map(fetch,todo):
            if result:current[key]=result;print('Photo:',key,flush=True)
            MANIFEST.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
    print('Attributed photographs:',len(current),flush=True)
if __name__=='__main__':main()
