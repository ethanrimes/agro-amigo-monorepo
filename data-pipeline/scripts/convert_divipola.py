"""Convert raw DANE DIVIPOLA CSV to TSV format expected by the upload-divipola loader."""
from pathlib import Path
import pandas as pd

src = Path(__file__).resolve().parents[2] / 'data' / 'divipola_raw.csv'
dst = Path(__file__).resolve().parents[2] / 'data' / 'divipola_municipios.tsv'

df = pd.read_csv(src, encoding='utf-8', dtype=str)
print('Source columns:', list(df.columns))

df = df.rename(columns={
    'Código Departamento': 'Código (Departamento)',
    'Nombre Departamento': 'Nombre (Departamento)',
    'Código Municipio':   'Código (Municipio)',
    'Nombre Municipio':   'Nombre (Municipio)',
    'Tipo: Municipio / Isla / Área no municipalizada': '"Municipio, Isla, Área no municipalizada"',
    'longitud': 'Longitud',
})

df['Longitud'] = df['Longitud'].str.replace(',', '.', regex=False)
df['Latitud']  = df['Latitud'].str.replace(',', '.', regex=False)

df.to_csv(dst, sep='\t', index=False, encoding='utf-8')
print('Wrote', dst, 'rows=', len(df))
print(df.head(3).to_string())
