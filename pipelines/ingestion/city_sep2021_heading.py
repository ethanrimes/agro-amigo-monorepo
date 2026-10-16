"""Private source-bound heading experiment; does not publish or infer prices."""
import hashlib,json,pathlib,pdfplumber,re
EXPECTED_PARENT='cbd378bc2d1863439c9e0a806dcdaa5026ebdd9e920fbd9c63dc1473de589edf'
EXPECTED_MARKETS={
 'f5d39758d2921991b120381bafbfa2f3dd3cdd07cbbdfc8611f60d51c3a5dd93':'BOGOTÁ - CORABASTOS',
 'f74ba57880a0a199d6926b8fb5652b652926d7d6ec7bfd17efea320186de1b2c':'BARRANQUILLA, GRANABASTOS',
 '16381c4b870066c7f3f4aab8c0d732dc36187d3b088c68bb308a46ec6c33b463':'Bazurto, Cartagena',
 'd0403c415af395c5bca852a4dd6977dfb1d5a784e040d579d58d0d9f97efdbee':'MONTERÍA - Mercado del Sur',
 '36058d3e2ab35b83737c3379870dfc94cfc8f93798f6873101beb296f2bd68ad':'MEDELLÍN, CENTRAL MAYORISTA DE ANTIOQUIA',
 'eaaafa06421b7ffba4828df57827e90987d9e889bbd854d5174b88831a32148f':'Mercasa - Pereira',
 '301dff168ebe1cc357fd2bf0cc84409b28410e418ff57a43250c05b78a846e66':'Plaza de mercado del barrio Bolívar - Popayán',
 'cc58e5ce38fa751138de088436ece59fb35610fc14eca39d1811f76d2009bd78':'SANTA MARTA (MAGDALENA)',
 '32c73fee19652051a882222b51178105fd36e65098c9004992bfb971ead116fc':'SINCELEJO, NUEVO MERCADO',
 '479bb6418ba84694e41bdf3b6249761127dd88fa1227b5e2dd3e3975430d5aa6':'CENTRAL DE ABASTOS DE VILLAVICENCIO',
 '80009b21f92c47bac30d7a8d181605682fa3404c43a96610d93305b4cfbf1058':'Valledupar, Mercabastos',
}
def accepted(parent_sha, child_sha, raw_bytes, text):
 if parent_sha!=EXPECTED_PARENT or child_sha not in EXPECTED_MARKETS or hashlib.sha256(raw_bytes).hexdigest()!=child_sha: return None
 lines=[x.strip() for x in text.splitlines() if x.strip()]
 if len(lines)<7 or lines[:3]!=['PRECIOS DE VENTA MAYORISTA','PRODUTOS DE PRIMERA CALIDAD','1 de septiembre de 2021']:
  return None
 if lines[4:7]!=['Ronda 1 Ronda 2','Producto Presentación Unidades','Mínimo Máximo Mínimo Máximo']:
  return None
 return lines[3] if lines[3]==EXPECTED_MARKETS[child_sha] else None

