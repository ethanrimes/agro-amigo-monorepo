"""Bounded read-only counts of dated public news listings; no article bodies saved."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

START=date(2026,8,24)
END=date(2026,9,7)  # Exclusive; excludes the still-in-progress September 7.
OUT=Path(__file__).resolve().parent
MONTHS={'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12,'ene':1,'feb':2,'mar':3,'abr':4,'may':5,'jun':6,'jul':7,'ago':8,'sept':9,'oct':10,'nov':11,'dic':12}

def get(url,params=None):
    r=requests.get(url,params=params,timeout=30)
    r.raise_for_status()
    return r

def stats(source,url,rows,coverage,extra=None):
    unique={x['url']:x for x in rows}
    chosen=[x for x in unique.values() if START<=date.fromisoformat(x['date'])<END]
    counts=Counter(x['date'] for x in chosen)
    return {'source':source,'listing_url':url,'coverage':coverage,'count_14_days':len(chosen),'mean_per_calendar_day':len(chosen)/14,'daily_counts':dict(sorted(counts.items())),'rows':sorted(chosen,key=lambda x:(x['date'],x['url'])),'oldest_listing_date':min((x['date'] for x in rows),default=None),**(extra or {})}

def wordpress(task):
    source,base,category=task
    params={'after':'2026-08-23T23:59:59','before':'2026-09-07T00:00:00','per_page':100,'_fields':'id,date,date_gmt,link,categories'}
    if category:params['categories']=category
    r=get(base+'/wp-json/wp/v2/posts',params);body=r.json()
    rows=[{'url':x['link'],'date':x['date'][:10],'date_gmt':x.get('date_gmt'),'categories':x.get('categories',[])} for x in body]
    assert len(body)==int(r.headers['X-WP-Total']), 'Incomplete API result: do not report as full window'
    assert all(START<=date.fromisoformat(x['date'])<END for x in rows), 'Date filter was ignored'
    return stats(source,base,rows,'All posts returned by public WordPress API date/category query; publisher-local date.',{'query_url':r.url,'api_total':int(r.headers['X-WP-Total'])})

def agrosavia():
    u='https://www.agrosavia.co/noticias';s=BeautifulSoup(get(u).text,'html.parser');rows=[]
    for a in s.select('a[data-date]'):
        match=re.search(r'(\w+)\.?\s+(\d+),\s*(\d{4})',a['data-date'])
        if not match:continue
        month,day,year=match.groups()
        d=date(int(year),MONTHS[month.lower()],int(day))
        rows.append({'url':urljoin(u,a['href']),'date':d.isoformat()})
    return stats('AGROSAVIA',u,rows,'Dated cards on news listing, which extends before the start of the window.')

def drupal(task):
    name,u=task;s=BeautifulSoup(get(u).text,'html.parser');rows=[]
    for t in s.select('time[datetime]'):
        # Find the containing view row/card with an article link.
        container=t
        for _ in range(7):
            container=container.parent
            links=[a for a in container.select('a[href]') if ('/noticia' in a['href'] or '/es-co/sala-de-prensa/' in a['href']) and len(a.get_text(strip=True))>10]
            if links:break
        else:raise ValueError('No link found for dated card')
        rows.append({'url':urljoin(u,links[0]['href']),'date':t['datetime'][:10]})
    return stats(name,u,rows,'Dated cards on news listing, which extends before the start of the window.')

def portafolio():
    u='https://www.portafolio.co/economia/agro';s=BeautifulSoup(get(u).text,'html.parser');rows=[]
    for c in s.select('.c-articulo__info'):
        d=c.select_one('.c-articulo__fecha');a=c.select_one('.c-articulo__titulo a[href]')
        if not d or not a:continue
        try:published=datetime.strptime(d.get_text(strip=True),'%d.%m.%Y').date()
        except ValueError:continue
        rows.append({'url':urljoin(u,a['href']),'date':published.isoformat()})
    return stats('Portafolio — Agro',u,rows,'Dated agriculture-section cards; no whole-site business/news count.')

def ica():
    u='https://www.ica.gov.co/noticias';rows=[];pages=[];older=False
    for page in range(1,13):
        request_url=u if page==1 else u+f'?page={page}'
        s=BeautifulSoup(get(request_url).text,'html.parser');pages.append(request_url);page_dates=[]
        for span in s.select('.post-date'):
            match=re.search(r'(\d+)\s+de\s+(\w+)\s+de\s+(\d{4})',span.get_text(' ',strip=True),re.I)
            if not match:continue
            day,month,year=match.groups();d=date(int(year),MONTHS[month.lower()],int(day))
            container=span.find_parent('div',class_='col-md-7');a=container.select_one('h3 a[href]') if container else None
            if not a:raise ValueError('Missing ICA article link')
            rows.append({'url':urljoin(u,a['href']),'date':d.isoformat()});page_dates.append(d)
        if page_dates and min(page_dates)<START:older=True;break
        time.sleep(.4)
    return stats('ICA',u,rows,'Paginated dated news cards; '+('reached dates before window.' if older else 'bounded pagination incomplete.'),{'pages_checked':pages,'complete_window_on_listing':older})

def main():
    tasks=[lambda:wordpress(('La Nación — Economía','https://www.lanacion.com.co',22)),lambda:wordpress(('Redagrícola — all countries','https://redagricola.com',None)),lambda:wordpress(('Redagrícola — Colombia category','https://redagricola.com',645)),agrosavia,lambda:drupal(('Agronet','https://agronet.gov.co/noticias')),lambda:drupal(('UPRA','https://upra.gov.co/es-co/sala-de-prensa/noticias')),portafolio,ica]
    def run(f):
        try:return f()
        except Exception as e:return {'error_type':type(e).__name__,'error':str(e)[:250]}
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,tasks))
    report={'checked_utc':datetime.now(timezone.utc).isoformat(),'start_inclusive':START.isoformat(),'end_exclusive':END.isoformat(),'days':14,'date_basis':'Publisher-reported publication date. WordPress queries use publisher-local dates; this is not a first-seen crawl log.','sources':results}
    (OUT/'observed-counts.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in x.items() if k not in ['rows','pages_checked','query_url','daily_counts']} for x in results],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
