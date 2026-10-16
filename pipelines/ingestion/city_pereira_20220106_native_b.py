"""PRIVATE exact Pereira Jan 6, 2022 native candidate; no production registration."""
import hashlib,io,json,zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from .city_pereira_local_hook_b import parse_verified_pdf
URL='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-06-01-2022.zip'
PARENT_SHA='0f53db2e11ac41c7646bc011209c1029c6ca3f9eee590d0438b64d9c0010a08f'
CHILD_SHA='a309fbd8b620b034da2d2627618469c4b4716e0c00b1a83e4f0b98363dda4da4'
ENTRY='Pereira, Mercasa 6-1-2022.pdf'
CRC=2849284751
PIN_SHA='c3e9ecc6f5791c29272290655c6ff94f19258c6b3d91ecfc21b4c77816c06456'
VERSION='city-v8:pereira-20220106-native-category-private-v2'
DAY=date(2022,1,6)

def _pin():
 raw=Path(__file__).with_name('city_pereira_20220106_pins_private.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=PIN_SHA:raise ValueError('Pereira independent oracle pin changed')
 value=json.loads(raw)
 if (value['source_url'],value['parent_sha256'],value['entry_name'],value['child_sha256'])!=(URL,PARENT_SHA,ENTRY,CHILD_SHA):
  raise ValueError('Pereira source identity pin changed')
 return value

def _row(row):
 return [v.isoformat() if isinstance(v,date) else format(v,'f') if isinstance(v,Decimal) else v for v in row]

def parse_exact_parent(source_url,parent_bytes):
 if source_url!=URL:return None
 if hashlib.sha256(parent_bytes).hexdigest()!=PARENT_SHA:raise ValueError('Pereira parent original changed')
 pin=_pin()
 with zipfile.ZipFile(io.BytesIO(parent_bytes)) as z:
  if z.namelist().count(ENTRY)!=1 or z.testzip() is not None:raise ValueError('Pereira ZIP entries/CRC changed')
  info=z.getinfo(ENTRY)
  if info.CRC!=CRC:raise ValueError('Pereira member CRC changed')
  child=z.read(info)
 if hashlib.sha256(child).hexdigest()!=CHILD_SHA:raise ValueError('Pereira PDF original changed')
 headings={(r['page'],r['table'],r['row']):(r['literal'],r['canonical']) for r in pin['source_heading_rows']}
 if headings!={(3,1,11):('Huevos y Lacteos','Huevos y lacteos'),(3,1,33):('Pescados y Mariscos','Pescados y mariscos')}:
  raise ValueError('Pereira source headings changed')
 rows=parse_verified_pdf(child,DAY)
 if len(rows)!=104 or len({r[0] for r in rows})!=104 or any(len(r)!=17 for r in rows):
  raise ValueError('Pereira complete native row set changed')
 blob=json.dumps([_row(r) for r in sorted(rows)],ensure_ascii=False,separators=(',',':')).encode()
 if hashlib.sha256(blob).hexdigest()!=pin['independent_poppler_full17_104_sha256']:
  raise ValueError('Pereira native rows diverged from independent Poppler 17-field oracle')
 if sum(r[5]=='Huevos y lacteos' for r in rows)!=1 or sum(r[5]=='Pescados y mariscos' for r in rows)!=7:
  raise ValueError('Pereira heading category counts changed')
 return {'parent_sha256':PARENT_SHA,'child_sha256':CHILD_SHA,'entry_name':ENTRY,
         'child_bytes':child,'rows':rows,'version':VERSION,'independent_oracle_sha256':pin['independent_poppler_full17_104_sha256']}
