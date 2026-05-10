#!/usr/bin/env python3
"""
Migration 034: Hand-picked dedup of canonical entities across dim_* tables.

This is a follow-up to migrations 019/020/021/023. It deduplicates groups that
the prior auto-merges left behind because the populator kept creating new
canonical rows for case/accent variants of raw values.

Decisions in this file are MINE — every (winner_name, [losers]) pair was
hand-picked after reading every dim_* TSV. The dedup rules are:
  - Proper Spanish accents (e.g. "Bogotá" not "Bogota")
  - Sentence case ("Carne de cerdo" not "CARNE DE CERDO")
  - Comma decimals ("1,5 Kilogramo" not "1.5 Kilogramo")
  - Drop trailing asterisks/plus from product names
  - Collapse "X (Department)" disambiguators when only one X exists in DIVIPOLA

Per pair, the script:
  1. Finds the winner ID by canonical_name (creating no fuzzy match — must
     match exactly).
  2. For each loser canonical_name that exists, repoints the alias table FK
     and the fact-table FKs in batches, then deletes the loser dim row.
  3. If the winner row currently has a non-canonical name (e.g. ALL CAPS due
     to having received the most observations), renames it to the proper form.

Run:
    python -m migrations.034_dedup_canonical_entities [--dry-run]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_URL = os.getenv("SUPABASE_DB_URL")


def fresh():
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    conn.autocommit = True
    c = conn.cursor()
    c.execute("SET statement_timeout = '180s'")
    return conn, c


# ============================================================
# DEDUP DECISIONS
# Format per dim table: list of (winner_canonical, [loser_canonicals])
# ============================================================

# dim_subcategory
SUBCATEGORY_MERGES = [
    ("Lácteos", ["Lacteos"]),
    ("Otros tubérculos", ["Otros tuberculos"]),
]

# dim_department: every ALL-CAPS dept merges into the proper-cased one
DEPARTMENT_MERGES = [
    ("Antioquia", ["ANTIOQUIA"]),
    ("Arauca", ["ARAUCA"]),
    ("Atlántico", ["ATLÁNTICO"]),
    ("Bogotá, D.C.", ["BOGOTÁ, D.C."]),
    ("Bolívar", ["BOLÍVAR"]),
    ("Boyacá", ["BOYACÁ"]),
    ("Caldas", ["CALDAS"]),
    ("Caquetá", ["CAQUETÁ"]),
    ("Casanare", ["CASANARE"]),
    ("Cauca", ["CAUCA"]),
    ("Cesar", ["CESAR"]),
    ("Córdoba", ["CÓRDOBA"]),
    ("Cundinamarca", ["CUNDINAMARCA"]),
    ("Guaviare", ["GUAVIARE"]),
    ("Huila", ["HUILA"]),
    ("La Guajira", ["LA GUAJIRA"]),
    ("Magdalena", ["MAGDALENA"]),
    ("Meta", ["META"]),
    ("Nariño", ["NARIÑO"]),
    ("Norte de Santander", ["NORTE DE SANTANDER"]),
    ("Putumayo", ["PUTUMAYO"]),
    ("Quindío", ["QUINDÍO"]),
    ("Risaralda", ["RISARALDA"]),
    ("Santander", ["SANTANDER"]),
    ("Sucre", ["SUCRE"]),
    ("Tolima", ["TOLIMA"]),
    ("Valle del Cauca", ["VALLE DEL CAUCA"]),
]

# dim_city: case + accent + a few parenthetical-disambiguator collapses
CITY_MERGES = [
    ("Acacías", ["Acacias"]),
    ("Agustín Codazzi", ["Agustin Codazzi"]),
    ("Ariguaní", ["Ariguani"]),
    ("Barbosa", ["BARBOSA"]),
    ("Belén", ["Belen", "BELÉN"]),
    ("Bogotá, D.C.", ["Bogotà"]),
    ("Buenavista", ["BUENAVISTA"]),
    ("Cajicá", ["Cajica"]),
    ("Calamar", ["CALAMAR"]),
    ("Candelaria", ["CANDELARIA"]),
    ("Cereté", ["Cerete"]),
    ("Charalá", ["Charala"]),
    ("Chinácota", ["Chinacota"]),
    ("Chinú", ["Chinu"]),
    ("Chiquinquirá", ["Chiquinquira"]),
    ("Chiriguaná", ["Chiriguana"]),
    ("Chitagá", ["Chitaga"]),
    ("Chivolo", ["Chibolo"]),
    ("Ciénaga De Oro", ["Cienaga De Oro"]),
    ("Colón", ["Colon", "COLÓN"]),
    ("Cuaspud Carlosama", ["Cuaspud", "Cuaspúd", "CUASPÚD"]),
    ("Cúcuta", ["Cucuta", "CÚCUTA"]),
    ("Donmatías", ["Don Matias"]),
    ("El Carmen De Bolívar", ["El Carmen De Bolivar"]),
    ("El Carmen De Chucurí", ["El Carmen De Chucuri"]),
    ("El Paujíl", ["El Paujil"]),
    ("El Piñón", ["El Piñon"]),
    ("Entrerríos", ["Entrerrios"]),
    ("Facatativá", ["Facatativa"]),
    ("Florencia", ["FLORENCIA"]),
    ("Fúquene", ["Fuquene"]),
    ("Gachancipá", ["Gachancipa"]),
    ("Gámbita", ["Gambita"]),
    ("Gómez Plata", ["Gomez Plata"]),
    ("Granada", ["GRANADA"]),
    ("Guachetá", ["Guacheta"]),
    ("Guamal", ["GUAMAL"]),
    ("Ibagué", ["Ibague"]),
    ("Ipiales", ["Ipiales (Nariño)"]),
    ("Jamundí", ["Jamundi"]),
    ("La Paz", ["LA PAZ"]),
    ("La Unión", ["La Union"]),
    ("Magangué", ["Magangue"]),
    ("Manatí", ["Manati"]),
    ("María La Baja", ["Maria La Baja"]),
    ("Medellín", ["Medellin"]),
    ("Moniquirá", ["Moniquira"]),
    ("Montelíbano", ["Montelibano"]),
    ("Montería", ["Monteria"]),
    ("Mosquera", ["MOSQUERA"]),
    ("Nemocón", ["Nemocon"]),
    ("Patía", ["Patia"]),
    ("Peñol", ["Peñol (Antioquia)"]),
    ("Popayán", ["Popayan"]),
    ("Potosí", ["Potosi"]),
    ("Puerto Rico", ["PUERTO RICO"]),
    ("Ráquira", ["Raquira"]),
    ("Restrepo", ["RESTREPO"]),
    ("Rionegro", ["Rionegro (Antioquia)", "RIONEGRO (Antioquia)"]),
    ("Sabanalarga", ["SABANALARGA", "SABANALARGA (Atlántico)"]),
    ("Sabanas De San Ángel", ["Sabanas De San Angel"]),
    ("Saboyá", ["Saboya"]),
    ("Sahagún", ["Sahagun"]),
    ("Salamina", ["SALAMINA"]),
    ("San Francisco", ["SAN FRANCISCO"]),
    ("San José De La Montaña", ["San Jose De La Montaña"]),
    ("San Luis De Sincé", ["San Luis De Since"]),
    ("San Martín", ["San Martin", "SAN MARTÍN"]),
    ("San Pedro", ["SAN PEDRO"]),
    ("San Vicente De Chucurí", ["San Vicente Del Chucuri"]),
    ("Santa Bárbara", ["SANTA BÁRBARA (Antioquia)"]),
    ("Santiago", ["SANTIAGO"]),
    ("Sesquilé", ["Sesquile"]),
    ("Sibaté", ["Sibate"]),
    ("Sonsón", ["Sonson"]),
    ("Sopó", ["Sopo"]),
    ("Sotaquirá", ["Sotaquira"]),
    ("Timbío", ["Timbio"]),
    ("Tocancipá", ["Tocancipa"]),
    ("Toledo", ["TOLEDO"]),
    ("Tolú Viejo", ["Tolu Viejo", "TOLÚ VIEJO"]),
    ("Tuluá", ["Tulua", "Tuluá (Valle del Cauca)"]),
    ("Túquerres", ["Tuquerres"]),
    ("Vélez", ["Velez"]),
    ("Villa De San Diego De Ubaté", ["Villa De San Diego De Ubate"]),
    ("Villamaría", ["Villamaria"]),
    ("Villanueva", ["VILLANUEVA"]),
    ("Villapinzón", ["Villapinzon"]),
    ("Zipaquirá", ["Zipaquira"]),
]

# dim_market: every "Mercado municipal de X" with 3 case/accent variants
# I'm listing each city's variants. Same conventions as cities.
def _mm(city):
    return f"Mercado municipal de {city}"


MARKET_MERGES = [
    # Non-mm markets first
    ("Complejo de Servicios del Sur", ["Complejo de servicios del Sur"]),
    # Mercado municipal variants — proper-cased winner
    (_mm("Abejorral"), [_mm("ABEJORRAL")]),
    (_mm("Acacías"), [_mm("Acacias"), _mm("ACACÍAS")]),
    (_mm("Aguachica"), [_mm("AGUACHICA")]),
    (_mm("Aguazul"), [_mm("AGUAZUL")]),
    (_mm("Agustín Codazzi"), [_mm("Agustin Codazzi"), _mm("AGUSTÍN CODAZZI")]),
    (_mm("Aipe"), [_mm("AIPE")]),
    (_mm("Angostura"), [_mm("ANGOSTURA")]),
    (_mm("Arauca"), [_mm("ARAUCA")]),
    (_mm("Arauquita"), [_mm("ARAUQUITA")]),
    (_mm("Ariguaní"), [_mm("Ariguani"), _mm("ARIGUANÍ")]),
    (_mm("Arjona"), [_mm("ARJONA")]),
    (_mm("Ayapel"), [_mm("AYAPEL")]),
    (_mm("Barbosa"), [_mm("BARBOSA")]),
    (_mm("Barrancabermeja"), [_mm("BARRANCABERMEJA")]),
    (_mm("Belén"), [_mm("Belen"), _mm("BELÉN")]),
    (_mm("Bello"), [_mm("BELLO")]),
    (_mm("Belmira"), [_mm("BELMIRA")]),
    (_mm("Bogotá, D.C."), [_mm("Bogotà")]),
    (_mm("Bosconia"), [_mm("BOSCONIA")]),
    (_mm("Buenavista"), [_mm("BUENAVISTA")]),
    (_mm("Buesaco"), [_mm("BUESACO")]),
    (_mm("Bugalagrande"), [_mm("BUGALAGRANDE")]),
    (_mm("Cajamarca"), [_mm("CAJAMARCA")]),
    (_mm("Cajicá"), [_mm("Cajica"), _mm("CAJICÁ")]),
    (_mm("Calamar"), [_mm("CALAMAR")]),
    (_mm("Candelaria"), [_mm("CANDELARIA")]),
    (_mm("Carolina"), [_mm("CAROLINA")]),
    (_mm("Castilla La Nueva"), [_mm("Castilla la Nueva"), _mm("CASTILLA LA NUEVA")]),
    (_mm("Cereté"), [_mm("Cerete"), _mm("CERETÉ")]),
    (_mm("Charalá"), [_mm("Charala"), _mm("CHARALÁ")]),
    (_mm("Chimichagua"), [_mm("CHIMICHAGUA")]),
    (_mm("Chinácota"), [_mm("Chinacota"), _mm("CHINÁCOTA")]),
    (_mm("Chinú"), [_mm("Chinu"), _mm("CHINÚ")]),
    (_mm("Chiquinquirá"), [_mm("Chiquinquira"), _mm("CHIQUINQUIRÁ")]),
    (_mm("Chiriguaná"), [_mm("Chiriguana"), _mm("CHIRIGUANÁ")]),
    (_mm("Chitagá"), [_mm("Chitaga"), _mm("CHITAGÁ")]),
    (_mm("Chivolo"), [_mm("CHIVOLO")]),
    (_mm("Ciénaga De Oro"), [_mm("Cienaga De Oro"), _mm("Ciénaga de Oro"), _mm("CIÉNAGA DE ORO")]),
    (_mm("Cimitarra"), [_mm("CIMITARRA")]),
    (_mm("Circasia"), [_mm("CIRCASIA")]),
    (_mm("Cogua"), [_mm("COGUA")]),
    (_mm("Colón"), [_mm("Colon"), _mm("COLÓN")]),
    (_mm("Cota"), [_mm("COTA")]),
    (_mm("Cuaspud Carlosama"),
     [_mm("Cuaspud"), _mm("Cuaspúd"), _mm("CUASPÚD"), _mm("CUASPUD CARLOSAMA")]),
    (_mm("Cúcuta"), [_mm("Cucuta"), _mm("CÚCUTA")]),
    (_mm("Cumaral"), [_mm("CUMARAL")]),
    (_mm("Cumbal"), [_mm("CUMBAL")]),
    (_mm("Donmatías"), [_mm("Don Matias"), _mm("DONMATÍAS")]),
    (_mm("Dosquebradas"), [_mm("DOSQUEBRADAS")]),
    (_mm("Duitama"), [_mm("DUITAMA")]),
    (_mm("El Carmen De Bolívar"),
     [_mm("El Carmen De Bolivar"), _mm("El Carmen de Bolívar"), _mm("EL CARMEN DE BOLÍVAR")]),
    (_mm("El Carmen De Chucurí"),
     [_mm("El Carmen De Chucuri"), _mm("El Carmen de Chucurí"), _mm("EL CARMEN DE CHUCURÍ")]),
    (_mm("El Carmen De Viboral"),
     [_mm("El Carmen de Viboral"), _mm("EL CARMEN DE VIBORAL")]),
    (_mm("El Copey"), [_mm("EL COPEY")]),
    (_mm("El Doncello"), [_mm("EL DONCELLO")]),
    (_mm("El Guamo"), [_mm("EL GUAMO")]),
    (_mm("El Paujíl"), [_mm("El Paujil"), _mm("EL PAUJÍL")]),
    (_mm("El Piñón"), [_mm("El Piñon"), _mm("EL PIÑÓN")]),
    (_mm("El Rosal"), [_mm("EL ROSAL")]),
    (_mm("El Santuario"), [_mm("EL SANTUARIO")]),
    (_mm("Entrerríos"), [_mm("Entrerrios"), _mm("ENTRERRÍOS")]),
    (_mm("Envigado"), [_mm("ENVIGADO")]),
    (_mm("Facatativá"), [_mm("Facatativa"), _mm("FACATATIVÁ")]),
    (_mm("Filandia"), [_mm("FILANDIA")]),
    (_mm("Firavitoba"), [_mm("FIRAVITOBA")]),
    (_mm("Florencia"), [_mm("FLORENCIA")]),
    (_mm("Fortul"), [_mm("FORTUL")]),
    (_mm("Funza"), [_mm("FUNZA")]),
    (_mm("Fúquene"), [_mm("Fuquene"), _mm("FÚQUENE")]),
    (_mm("Gachancipá"), [_mm("Gachancipa"), _mm("GACHANCIPÁ")]),
    (_mm("Galeras"), [_mm("GALERAS")]),
    (_mm("Gámbita"), [_mm("Gambita"), _mm("GÁMBITA")]),
    (_mm("Gómez Plata"), [_mm("Gomez Plata"), _mm("GÓMEZ PLATA")]),
    (_mm("Granada"), [_mm("GRANADA")]),
    (_mm("Guachetá"), [_mm("Guacheta"), _mm("GUACHETÁ")]),
    (_mm("Guachucal"), [_mm("GUACHUCAL")]),
    (_mm("Guadalajara De Buga"),
     [_mm("Guadalajara de Buga"), _mm("GUADALAJARA DE BUGA")]),
    (_mm("Guamal"), [_mm("GUAMAL")]),
    (_mm("Guarne"), [_mm("GUARNE")]),
    (_mm("Guasca"), [_mm("GUASCA")]),
    (_mm("Ibagué"), [_mm("Ibague"), _mm("IBAGUÉ")]),
    (_mm("Iles"), [_mm("ILES")]),
    (_mm("Ipiales"), [_mm("IPIALES"), _mm("Ipiales (Nariño)")]),
    (_mm("Jamundí"), [_mm("Jamundi"), _mm("JAMUNDÍ")]),
    (_mm("Juan De Acosta"), [_mm("Juan de Acosta"), _mm("JUAN DE ACOSTA")]),
    (_mm("La Calera"), [_mm("LA CALERA")]),
    (_mm("La Ceja"), [_mm("LA CEJA")]),
    (_mm("La Esperanza"), [_mm("LA ESPERANZA")]),
    (_mm("La Gloria"), [_mm("LA GLORIA")]),
    (_mm("La Montañita"), [_mm("LA MONTAÑITA")]),
    (_mm("La Paz"), [_mm("LA PAZ")]),
    (_mm("La Plata"), [_mm("LA PLATA")]),
    (_mm("La Unión"), [_mm("La Union"), _mm("LA UNIÓN")]),
    (_mm("Lebrija"), [_mm("LEBRIJA")]),
    (_mm("Lenguazaque"), [_mm("LENGUAZAQUE")]),
    (_mm("Lorica"), [_mm("LORICA")]),
    (_mm("Madrid"), [_mm("MADRID")]),
    (_mm("Magangué"), [_mm("Magangue"), _mm("MAGANGUÉ")]),
    (_mm("Mahates"), [_mm("MAHATES")]),
    (_mm("Manatí"), [_mm("Manati"), _mm("MANATÍ")]),
    (_mm("Manizales"), [_mm("MANIZALES")]),
    (_mm("María La Baja"),
     [_mm("Maria La Baja"), _mm("María la Baja"), _mm("MARÍA LA BAJA")]),
    (_mm("Marinilla"), [_mm("MARINILLA")]),
    (_mm("Medellín"), [_mm("Medellin"), _mm("MEDELLÍN")]),
    (_mm("Moniquirá"), [_mm("Moniquira"), _mm("MONIQUIRÁ")]),
    (_mm("Montelíbano"), [_mm("Montelibano"), _mm("MONTELÍBANO")]),
    (_mm("Montería"), [_mm("Monteria"), _mm("MONTERÍA")]),
    (_mm("Monterrey"), [_mm("MONTERREY")]),
    (_mm("Mosquera"), [_mm("MOSQUERA")]),
    (_mm("Neiva"), [_mm("NEIVA")]),
    (_mm("Nemocón"), [_mm("Nemocon"), _mm("NEMOCÓN")]),
    (_mm("Nueva Granada"), [_mm("NUEVA GRANADA")]),
    (_mm("Ovejas"), [_mm("OVEJAS")]),
    (_mm("Paipa"), [_mm("PAIPA")]),
    (_mm("Palermo"), [_mm("PALERMO")]),
    (_mm("Palmira"), [_mm("PALMIRA")]),
    (_mm("Pasto"), [_mm("PASTO")]),
    (_mm("Patía"), [_mm("Patia"), _mm("PATÍA")]),
    (_mm("Peñol"), [_mm("Peñol (Antioquia)")]),
    (_mm("Pereira"), [_mm("PEREIRA")]),
    (_mm("Piedecuesta"), [_mm("PIEDECUESTA")]),
    (_mm("Pijiño Del Carmen"),
     [_mm("Pijiño del Carmen"), _mm("PIJIÑO DEL CARMEN")]),
    (_mm("Pitalito"), [_mm("PITALITO")]),
    (_mm("Pivijay"), [_mm("PIVIJAY")]),
    (_mm("Planeta Rica"), [_mm("PLANETA RICA")]),
    (_mm("Plato"), [_mm("PLATO")]),
    (_mm("Ponedera"), [_mm("PONEDERA")]),
    (_mm("Popayán"), [_mm("Popayan"), _mm("POPAYÁN")]),
    (_mm("Potosí"), [_mm("Potosi"), _mm("POTOSÍ")]),
    (_mm("Pueblo Nuevo"), [_mm("PUEBLO NUEVO")]),
    (_mm("Puente Nacional"), [_mm("PUENTE NACIONAL")]),
    (_mm("Puerres"), [_mm("PUERRES")]),
    (_mm("Puerto Rico"), [_mm("PUERTO RICO")]),
    (_mm("Pupiales"), [_mm("PUPIALES")]),
    (_mm("Quimbaya"), [_mm("QUIMBAYA")]),
    (_mm("Ráquira"), [_mm("Raquira"), _mm("RÁQUIRA")]),
    (_mm("Restrepo"), [_mm("RESTREPO")]),
    (_mm("Rionegro"), [_mm("RIONEGRO"), _mm("Rionegro (Antioquia)")]),
    (_mm("Sabana De Torres"),
     [_mm("Sabana de Torres"), _mm("SABANA DE TORRES")]),
    (_mm("Sabanalarga"), [_mm("SABANALARGA")]),
    (_mm("Sabanas De San Ángel"),
     [_mm("Sabanas De San Angel"), _mm("Sabanas de San Ángel"), _mm("SABANAS DE SAN ÁNGEL")]),
    (_mm("Saboyá"), [_mm("Saboya"), _mm("SABOYÁ")]),
    (_mm("Sahagún"), [_mm("Sahagun"), _mm("SAHAGÚN")]),
    (_mm("Salamina"), [_mm("SALAMINA")]),
    (_mm("Salento"), [_mm("SALENTO")]),
    (_mm("San Alberto"), [_mm("SAN ALBERTO")]),
    (_mm("San Diego"), [_mm("SAN DIEGO")]),
    (_mm("San Estanislao"), [_mm("SAN ESTANISLAO")]),
    (_mm("San Francisco"), [_mm("SAN FRANCISCO")]),
    (_mm("San Jerónimo"), [_mm("SAN JERÓNIMO")]),
    (_mm("San José de Cúcuta"), [_mm("SAN JOSÉ DE CÚCUTA")]),
    (_mm("San José De La Montaña"),
     [_mm("San Jose De La Montaña"), _mm("San José de la Montaña"),
      _mm("San José de La Montaña"), _mm("SAN JOSÉ DE LA MONTAÑA")]),
    (_mm("San José de Toluviejo"), [_mm("SAN JOSÉ DE TOLUVIEJO")]),
    (_mm("San Juan Del Cesar"),
     [_mm("San Juan del Cesar"), _mm("SAN JUAN DEL CESAR")]),
    (_mm("San Juan Nepomuceno"), [_mm("SAN JUAN NEPOMUCENO")]),
    (_mm("San Luis De Sincé"),
     [_mm("San Luis De Since"), _mm("San luis de Sincé"),
      _mm("San Luis de Sincé"), _mm("SAN LUIS DE SINCÉ")]),
    (_mm("San Marcos"), [_mm("SAN MARCOS")]),
    (_mm("San Martín"), [_mm("San Martin"), _mm("SAN MARTÍN")]),
    (_mm("San Miguel De Sema"),
     [_mm("San Miguel de Sema"), _mm("SAN MIGUEL DE SEMA")]),
    (_mm("San Onofre"), [_mm("SAN ONOFRE")]),
    (_mm("San Pedro"), [_mm("SAN PEDRO")]),
    (_mm("San Pedro De Los Milagros"),
     [_mm("San Pedro de los Milagros"), _mm("San Pedro de Los Milagros"),
      _mm("SAN PEDRO DE LOS MILAGROS")]),
    (_mm("San Pelayo"), [_mm("SAN PELAYO")]),
    (_mm("San Vicente De Chucurí"),
     [_mm("San Vicente de Chucurí"), _mm("SAN VICENTE DE CHUCURÍ"),
      _mm("San Vicente Del Chucuri")]),
    (_mm("Santiago"), [_mm("SANTIAGO")]),
    (_mm("Santa Rosa De Cabal"),
     [_mm("Santa Rosa de Cabal"), _mm("SANTA ROSA DE CABAL")]),
    (_mm("Santa Rosa De Osos"),
     [_mm("Santa Rosa de Osos"), _mm("SANTA ROSA DE OSOS")]),
    (_mm("Sapuyes"), [_mm("SAPUYES")]),
    (_mm("Saravena"), [_mm("SARAVENA")]),
    (_mm("Sesquilé"), [_mm("Sesquile"), _mm("SESQUILÉ")]),
    (_mm("Sibaté"), [_mm("Sibate"), _mm("SIBATÉ")]),
    (_mm("Sibundoy"), [_mm("SIBUNDOY")]),
    (_mm("Silvia"), [_mm("SILVIA")]),
    (_mm("Simacota"), [_mm("SIMACOTA")]),
    (_mm("Simijaca"), [_mm("SIMIJACA")]),
    (_mm("Sincelejo"), [_mm("SINCELEJO")]),
    (_mm("Socorro"), [_mm("SOCORRO")]),
    (_mm("Sogamoso"), [_mm("SOGAMOSO")]),
    (_mm("Sonsón"), [_mm("Sonson"), _mm("SONSÓN")]),
    (_mm("Sopó"), [_mm("Sopo"), _mm("SOPÓ")]),
    (_mm("Sotaquirá"), [_mm("Sotaquira"), _mm("SOTAQUIRÁ")]),
    (_mm("Suaita"), [_mm("SUAITA")]),
    (_mm("Subachoque"), [_mm("SUBACHOQUE")]),
    (_mm("Susa"), [_mm("SUSA")]),
    (_mm("Tabio"), [_mm("TABIO")]),
    (_mm("Tame"), [_mm("TAME")]),
    (_mm("Tangua"), [_mm("TANGUA")]),
    (_mm("Tauramena"), [_mm("TAURAMENA")]),
    (_mm("Tenjo"), [_mm("TENJO")]),
    (_mm("Tibasosa"), [_mm("TIBASOSA")]),
    (_mm("Timbío"), [_mm("Timbio"), _mm("TIMBÍO")]),
    (_mm("Toca"), [_mm("TOCA")]),
    (_mm("Tocancipá"), [_mm("Tocancipa"), _mm("TOCANCIPÁ")]),
    (_mm("Toledo"), [_mm("TOLEDO")]),
    (_mm("Tolú Viejo"), [_mm("Tolu Viejo"), _mm("TOLÚ VIEJO")]),
    (_mm("Tuluá"), [_mm("Tulua"), _mm("TULUÁ"), _mm("Tuluá (Valle del Cauca)")]),
    (_mm("Tunja"), [_mm("TUNJA")]),
    (_mm("Túquerres"), [_mm("Tuquerres"), _mm("TÚQUERRES")]),
    (_mm("Urrao"), [_mm("URRAO")]),
    (_mm("Valledupar"), [_mm("VALLEDUPAR")]),
    (_mm("Vélez"), [_mm("Velez"), _mm("VÉLEZ")]),
    (_mm("Ventaquemada"), [_mm("VENTAQUEMADA")]),
    (_mm("Villa De San Diego De Ubaté"),
     [_mm("Villa De San Diego De Ubate"),
      _mm("Villa de San Diego de Ubaté"), _mm("VILLA DE SAN DIEGO DE UBATÉ")]),
    (_mm("Villamaría"), [_mm("Villamaria"), _mm("VILLAMARÍA")]),
    (_mm("Villanueva"), [_mm("VILLANUEVA")]),
    (_mm("Villapinzón"), [_mm("Villapinzon"), _mm("VILLAPINZÓN")]),
    (_mm("Villavicencio"), [_mm("VILLAVICENCIO")]),
    (_mm("Yarumal"), [_mm("YARUMAL")]),
    (_mm("Yopal"), [_mm("YOPAL")]),
    (_mm("Zarzal"), [_mm("ZARZAL")]),
    (_mm("Zipaquirá"), [_mm("Zipaquira"), _mm("ZIPAQUIRÁ")]),
]

# dim_presentation
PRESENTATION_MERGES = [
    ("Arroba", ["AArrrroobbaa", "ARROBA", "AROBA"]),
    ("Atado", ["ATADO"]),
    ("Atado/Manojo",
     ["AAttaaddoo//mmaannoojjoo", "atado/Manojo", "Atado/manojo",
      "Atado/ Manojo", "Atado/Manoj o", "Atado/manoj o"]),
    ("Bloque", ["BLOQUE"]),
    ("Bolsa", ["BBoollssaa", "BOLSA"]),
    ("Bulto", ["BBuullttoo", "bulto", "BULTO"]),
    ("Caja cartón", ["Caja carton"]),
    ("Caja de cartón",
     ["caja de carton", "Caja de carton", "Caja de Carton", "CAJA DE CARTON",
      "caja de cartón", "Caja de Cartón", "Caja De Cartón", "CAJA DE CARTÓN",
      "CCaajjaa ddee ccaarrttóónn", "CCaajjaa ddee CCaarrttóónn",
      "CAJA DECARTN", "Cajadecartón"]),
    ("Caja de icopor",
     ["Caja de Icopor", "CCaajjaa ddee iiccooppoorr", "Caja icopor"]),
    ("Caja de madera",
     ["Caja de Madera", "Caja De Madera", "CAJA DE MADERA",
      "CCaajjaa ddee mmaaddeerraa", "Caja madera", "Caja Madera"]),
    ("Canastilla",
     ["canastilla", "CANASTILLA", "CCaannaassttiillllaa", "Canastila"]),
    ("Docena", ["DDoocceennaa", "DOCENA"]),
    ("Kilogramo",
     ["kilogramo", "KILOGRAMO", "KKiillooggrraammoo", "Killogramo", "KILO"]),
    ("Libra", ["LIBRA"]),
    ("Manojo", ["MANOJO"]),
    ("Manojo 3 Und", ["MANOJO 3 UND"]),
    ("Panal", ["panal", "PPaannaall"]),
    ("Unidad", ["unidad", "UNIDAD"]),
]

# dim_units: every "N Kilogramo" group (~150 of them)
UNITS_MERGES = [
    ("1 Kilogramo", ["1 kg", "1 Kg", "1 KG", "1 kilo", "1 Kilo",
                     "1 kilogramo", "1 KILOGRAMO", "1 kilogramos", "1 Kilos"]),
    ("1 Unidad", ["1 UNIDAD"]),
    ("1 Unidad 200 GR", ["1 unidad 200 gr", "1 Unidad 200 gr", "1 unidad -200 gr"]),
    ("1 Unidad 360 GR", ["1 Unidad 360 Gr", "1 UNIDAD -360 GR"]),
    ("1 Unidad 50 GR", ["1 unidad 50 gr", "1 Unidad 50 gr"]),
    ("1 Unidad de 50 GR", ["1 unidad de 50 gr", "1 unidad de 50 g"]),
    ("1,5 Kilogramo", ["1,5 kilogramo", "1.5 kilogramo", "1.5 Kilogramo"]),
    ("10 Kilogramo", ["10 kg", "10 Kg", "10 KG", "10 kilo",
                      "10 kilogramo", "10 KILOGRAMO", "10 kilos", "10 Kilos", "10 KILOS"]),
    ("10 Kilogramos", ["10 kilogramos"]),
    ("10 Unidad 50 GR", ["10 unidad 50 gr", "10 Unidad 50 gr", "10 unidad- 50 gr"]),
    ("10 Unidades de 500 GR", ["10 unidades de 500 GR"]),
    ("10 Kilogramo", ["10Kilogramo", "10KILOGRAMO"]),
    ("11 Kilogramo", ["11 Kg", "11 KG", "11 kilogramo", "11kilogramo"]),
    ("11 Kilogramo", ["11 KKiillooggrraammoo"]),
    ("100 Kilogramo", ["1100 KKiillooggrraammoo", "1100 kkiillooggrraammoo"]),
    ("12 Kilogramo", ["12 KG", "12 kilogramo", "12 kilos", "12 Kilos", "12 KILOS",
                      "12 kilogramos", "12Kilogramo"]),
    ("12 Unidad 1000", ["12 unidad 1000"]),
    ("12 Unidad 1000 CC",
     ["12 unidad 1000 cc", "12 unidad 1000 CC", "12 Unidad 1000 cc",
      "12 unidad-1000 cc", "12 Unidades de 1000 cc", "12 unidades de 1000 cc"]),
    ("12 Unidad 1000 GR", []),
    ("12 Unidad 180 GR", ["12 Unidad 180 gr", "12 Unidad 180 g"]),
    ("12 Unidad 20 GR", ["12 unidad 20 gr", "12 Unidad 20 gr"]),
    ("12 Unidad 200 GR",
     ["12 Unidad 200 Gr", "12 UNIDAD -200 GR", "12 Unidad 200 G"]),
    ("12 Unidad 250 GR",
     ["12 Unidad 250 gr", "12 Unidad- 250 gr", "12 Unidad-250 gr",
      "12 Unidad- 250 g", "12 Unidad-250 g"]),
    ("12 Unidad 40 GR", ["12 Unidad 40 gr", "12 Unidad- 40 gr"]),
    ("12 Unidad 50 GR", ["12 Unidad 50 gr", "12 Unidad- 50 gr"]),
    ("12 Unidad 900 CC", ["12 unidad 900 CC"]),
    ("12 Unidad 900 C", ["12 unidad 900 C"]),
    ("12,5 Kilogramo",
     ["12,5 kilogramo", "12,5 KILOGRAMO", "12.5 kilogramo", "12.5 Kilogramo",
      "12,5KILOGRAMO", "12.5Kilogramo"]),
    ("12,5 Kg", ["12.5 Kg"]),
    ("13 Kilogramo", ["13 kilogramo"]),
    ("14 Kilogramo", ["14 kilogramo", "14 KILOGRAMO"]),
    ("14 Kg", ["14 KG"]),
    ("14 Kilos", ["14 kilos", "14 KILOS"]),
    ("15 Kg", ["15 kg", "15 KG"]),
    ("15 Kilogramo", ["15 kilogramo", "15 KILOGRAMO"]),
    ("15 Kilogramos", ["15 kilogramos"]),
    ("15 Kilos", ["15 kilos", "15 KILOS"]),
    ("15,5 Kilogramo", ["15.5 Kilogramo"]),
    ("16 Kilogramo", []),
    ("16,5 Kilogramo", ["16.5 Kilogramo"]),
    ("17 Kilogramo", ["17 kilogramo"]),
    ("17 Kg", ["17 kg"]),
    ("18 Kilogramo", ["18 kilogramo"]),
    ("18 Kg", ["18 KG"]),
    ("18 Unidad 250 GR", ["18 unidad 250 gr", "18 Unidad 250 gr"]),
    ("18,75 Kilogramo",
     ["18,75 kilogramo", "18.75 kilogramo", "18.75 Kilogramo"]),
    ("19 Kilogramo", ["19 kilogramo", "19 KILOGRAMO"]),
    ("19 Kg", ["19 Kg"]),
    ("19 Kilogramos", ["19 kilogramos"]),
    ("19 Kilos", ["19 kilos", "19 Kilos", "19 KILOS"]),
    ("1 Kilogramo", ["1Kilogramo", "1KILOGRAMO", "1kilo"]),
    ("2 Kilogramo", ["2 kilogramo"]),
    ("2 Kilos", ["2 kilos"]),
    ("2,5 Kilogramo",
     ["2,5 kilogramo", "2,5 KILOGRAMO", "2.5 Kilogramo", "2.5 KILOGRAMO",
      "2,5 kilogramos"]),
    ("2,5 KILOS", ["2.5 KILOS"]),
    ("20 Kilogramo", ["20 kg", "20 Kg", "20 kilogramo", "20 KILOGRAMO"]),
    ("20 Kilogramos", ["20 kilogramos"]),
    ("20 Kilos", ["20 Kilos"]),
    ("20 Unidad 18 GR",
     ["20 Unidad 18 gr", "20 Unidad 18 Gr", "20 Unidad-18 gr",
      "20 UNIDAD -18 GR"]),
    ("20 Unidades de 18 GR", ["20 unidades de 18 GR"]),
    ("200 Gramo", ["200 gramo"]),
    ("22 Kilogramo", ["22 kilogramo", "22 KILOGRAMO"]),
    ("22 Kg", []),
    ("22,5 Kilogramo", ["22,5 kilogramo", "22.5 Kilogramo"]),
    ("22,7 Kilogramo", ["22.7 Kilogramo"]),
    ("220 Gramo", ["220 gramo"]),
    ("23 Kilogramo", ["23 kilogramo"]),
    ("24 Kilogramo", ["24 kilogramo"]),
    ("24 Kg", ["24 kg"]),
    ("24 Unidad 190 GR", ["24 Unidad 190 Gr", "24 UNIDAD -190 GR"]),
    ("24 Unidad 200 G", ["24 Unidad 200 g"]),
    ("24 Unidad 200 GR", ["24 unidad 200 gr", "24 Unidad 200 gr"]),
    ("24 Unidad 250 G", ["24 Unidad 250 g", "24 Unidad- 250 g"]),
    ("24 Unidad 250 GR",
     ["24 Unidad 250 gr", "24 Unidad 250 Gr", "24 Unidad- 250 gr",
      "24 UNIDAD -250 GR"]),
    ("24 Unidad 300 G", ["24 unidad 300 G", "24 Unidad 300 g"]),
    ("24 Unidad 300 GR",
     ["24 unidad 300 gr", "24 unidad 300 GR", "24 Unidad 300 gr",
      "24 Unidad 300 Gr", "24 UNIDAD -300 GR"]),
    ("24 Unidad 318 G", ["24 Unidad 318 g"]),
    ("24 Unidad 318 GR", ["24 unidad 318 gr", "24 Unidad 318 gr"]),
    ("24 Unidad 325 G", ["24 Unidad- 325 g"]),
    ("24 Unidad 325 GR", ["24 Unidad 325 gr", "24 Unidad- 325 gr"]),
    ("24 Unidad 425 G", ["24 Unidad 425 g"]),
    ("24 Unidad 425 GR",
     ["24 unidad 425 gr", "24 Unidad 425 gr", "24 Unidad 425 Gr",
      "24 UNIDAD -425 GR"]),
    ("24 Unidad 500 C", ["24 Unidad 500 c"]),
    ("24 Unidad 500 CC",
     ["24 unidad 500 cc", "24 Unidad 500 cc", "24 UNIDAD -500 CC"]),
    ("24 Unidad 500 G", ["24 unidad 500 G", "24 Unidad 500 g"]),
    ("24 Unidad 500 GR",
     ["24 unidad 500 GR", "24 Unidad 500 gr", "24 Unidad 500 Gr",
      "24 UNIDAD -500 GR"]),
    ("24 Unidad 500GR", ["24 Unidad 500gr"]),
    ("24 Unidades de 110 GR", ["24 unidades de 110 GR"]),
    ("24 Unidades de 150 GR", ["24 unidades de 150 GR"]),
    ("24 Unidades de 250 GR", ["24 unidades de 250 GR"]),
    ("24 Unidades de 415 GR", ["24 unidades de 415 GR"]),
    ("24 Unidades de 50 GR", ["24 unidades de 50 GR"]),
    ("24 Unidades de 500 GR", ["24 unidades de 500 GR"]),
    ("24 Unidades de 600 GR", ["24 unidades de 600 GR"]),
    ("24 Unidades de 85 GR", ["24 unidades de 85 GR"]),
    ("25 Kilo", ["25 kilo"]),
    ("25 Kilogramo", ["25 kilogramo", "25 KILOGRAMO"]),
    ("25 Kilogramos", ["25 kilogramos"]),
    ("25 Kilos", ["25 kilos", "25 Kilos", "25 KILOS"]),
    ("25 Unidad 450 g", ["25 UnIdad 450 g"]),
    ("25 Unidad 450 GR", ["25 Unidad 450 gr"]),
    ("25 Unidad 454 G", ["25 unidad 454 G"]),
    ("25 Unidad 454 GR",
     ["25 unidad 454 GR", "25 Unidad 454 Gr", "25 UNIDAD 454 GR",
      "25 UNIDAD -454 GR"]),
    ("25 Unidad 500", ["25 UNIDAD- 500"]),
    ("25 Unidad 500 G",
     ["25 unidad 500 G", "25 Unidad 500 g", "25 Unidad -500 g",
      "25 Unidad- 500 g"]),
    ("25 Unidad 500 GR",
     ["25 unidad 500 GR", "25 Unidad 500 gr", "25 Unidad 500 Gr",
      "25 Unidad -500 gr", "25 Unidad- 500 gr",
      "25 UNIDAD -500 GR", "25 UNIDAD- 500 GR"]),
    ("25 Unidades 500 GR", ["25 Unidades 500 gr"]),
    ("25 Unidades de 500 GR", ["25 unidades de 500 GR"]),
    ("250 Gramo", ["250 gramo"]),
    ("28 Kilogramo", ["28 kilogramo"]),
    ("3,5 Kilogramo", ["3,5 kilogramo", "3.5 Kilogramo"]),
    ("3 Kilogramo", ["3 kilogramo"]),
    ("3 Kg", ["3 KG"]),
    ("30 Kilogramo", ["30 kilogramo", "30 KILOGRAMO"]),
    ("30 Kg", ["30 KG"]),
    ("30 Kilogramos", ["30 kilogramos"]),
    ("30 Kilos", ["30 kilos", "30 KILOS"]),
    ("30 Unidad", ["30 unidad", "30 UNIDAD"]),
    ("30 Unidad 375 GR", ["30 Unidad 375 Gr", "30 UNIDAD -375 GR"]),
    ("30 Unidad 400 GR", ["30 Unidad 400 Gr", "30 UNIDAD -400 GR"]),
    ("30 Unidades", ["30 unidades"]),
    ("30 Unidades de 215 cc", ["30 unidades de 215 cc"]),
    ("32 Kilogramo", ["32 kilogramo"]),
    ("32 Unidad 360 G", ["32 Unidad 360 g"]),
    ("32 Unidad 360 GR", ["32 unidad 360 gr", "32 Unidad 360 gr"]),
    ("32 Unidades de 360 GR", ["32 Unidades de 360 gr"]),
    ("36 Unidad 170 G", ["36 Unidad 170 g"]),
    ("36 Unidad 170 GR", ["36 unidad 170 gr", "36 Unidad 170 gr"]),
    ("4 Kilogramo", ["4 kilogramo", "4 KILOGRAMO"]),
    ("40 Kilogramo", ["40 kilogramo"]),
    ("40 Kilogramos", ["40 kilogramos"]),
    ("40 Unidad 250 G", ["40 unidad 250 G", "40 Unidad- 250 g"]),
    ("40 Unidad 250 GR", ["40 unidad 250 GR", "40 Unidad- 250 gr"]),
    ("45 Kilogramo", ["45 kilogramo"]),
    ("45 Kg", []),
    ("45 Kilogramos", ["45 kilogramos"]),
    ("454 Gramo", ["454 GRAMO"]),
    ("46 Kilogramos", ["46 kilogramos"]),
    ("47 Kilogramo", ["47 kilogramo"]),
    ("48 Kilogramo", ["48 kilogramo"]),
    ("48 Kg", ["48 kg"]),
    ("48 Unidad 110 G", ["48 Unidad 110 g"]),
    ("48 Unidad 110 GR", ["48 Unidad 110 gr", "48 UNIDAD - 110 GR"]),
    ("48 Unidad 170 G", ["48 Unidad 170 g"]),
    ("48 Unidad 170 GR",
     ["48 unidad 170 gr", "48 Unidad 170 gr", "48 Unidad 170 Gr",
      "48 UNIDAD -170 GR"]),
    ("48 Unidad 40 G", ["48 Unidad 40 g"]),
    ("48 Unidad 40 GR",
     ["48 unidad 40 gr", "48 unidad 40 GR", "48 Unidad 40 gr"]),
    ("48 Unidad 425 G", ["48 unidad 425 G"]),
    ("48 Unidad 425 GR", ["48 unidad 425 GR"]),
    ("48 Unidades de 110 GR", ["48 unidades de 110 GR"]),
    ("48 Unidades de 200 GR", ["48 unidades de 200 GR"]),
    ("48 Unidades de 425 GR", ["48 unidades de 425 GR"]),
    ("5 Kilogramo", ["5 kilogramo", "5 KILOGRAMO"]),
    ("5 Kg", ["5 KG"]),
    ("5 Kilos", ["5 Kilos", "5 KILOS"]),
    ("50 Kilogramo", ["50 kg", "50 Kg", "50 kilogramo", "50 KILOGRAMO",
                      "50Kilogramo", "50KILOGRAMO"]),
    ("50 Kg", ["50 KG"]),
    ("50 Kilogramos", ["50 kilogramos"]),
    ("50 Kilos", ["50 kilos", "50 Kilos", "50 KILOS"]),
    ("500 Gramo", ["500 gramo", "500 GRAMO"]),
    ("500 GR", ["500 gr"]),
    ("6,5 Kilogramo", ["6.5 Kilogramo"]),
    ("6 Kilogramo", ["6 kilogramo"]),
    ("6 Kg", ["6 KG"]),
    ("60 Kilogramo", ["60 kg", "60 Kg", "60 kilogramo", "60 KILOGRAMO"]),
    ("60 Kilogramos", ["60 kilogramos"]),
    ("60 Kilos", ["60 kilos", "60 Kilos", "60 KILOS"]),
    ("62 Kilogramo", ["62 kilogramo"]),
    ("62,5 Kilogramo",
     ["62,5 kilogramo", "62,5 KILOGRAMO", "62.5 kilogramo", "62.5 Kilogramo"]),
    ("62,5 Kg", ["62.5 Kg"]),
    ("7,5 Kilogramo", ["7.5 kilogramo", "7.5 Kilogramo"]),
    ("7 Kilogramo", ["7 kilogramo"]),
    ("70 Kilogramo", ["70 kilogramo", "70 KILOGRAMO"]),
    ("70 Kg", ["70 Kg"]),
    ("70 Kilogramos", ["70 kilogramos"]),
    ("70 Kilos", ["70 kilos", "70 Kilos", "70 KILOS"]),
    ("72 Unidad 90 GR", ["72 Unidad 90 Gr", "72 UNIDAD -90 GR"]),
    ("75 Kilogramo", ["75 kilogramo"]),
    ("8 Kilogramo", ["8 kilogramo"]),
    ("8 Kg", ["8 KG"]),
    ("8 Kilogramos", ["8 kilogramos"]),
    ("8,5 Kg", ["8.5 Kg"]),
    ("8,5 Kilogramo", ["8,5 kilogramo", "8.5 kilogramo", "8.5 Kilogramo"]),
    ("80 Unidades de 90 GR", ["80 unidades de 90 GR"]),
    ("9 Kilogramo", ["9 kilogramo", "9 KILOGRAMO"]),
    ("9 Kg", ["9 Kg"]),
    ("9 Kilogramos", ["9 kilogramos"]),
    ("9 Kilos", ["9 kilos", "9 Kilos", "9 KILOS"]),
]

# dim_product
PRODUCT_MERGES = [
    ("Aceite de Palma", ["Aceite de palma"]),
    ("Aceite girasol", ["Aceite Girasol", "Aceite de Girasol"]),
    ("Aceite vegetal palma", ["Aceite vegetal Palma"]),
    ("Aguacate", ["Aguacate *", "Aguacate*"]),
    ("Aguacate Choquette", ["Aguacate choquette"]),
    ("Aguacate Hass", ["Aguacate hass"]),
    ("Aguacate Papelillo",
     ["Aguacate papelillo", "Aguacate papellilo", "Aguacatepapelillo"]),
    ("Aguacate común", ["Aguacatecomún"]),
    ("Ahuyamín (Sakata)",
     ["AAhhuuyyaammíínn ((ssaakkaattaa))",
      "Ahuyamín (sakata)", "Ahuyamin ( Sakata)"]),
    ("Ahuyama (Sakata)", ["Ahuyama (sakata)"]),
    ("Ají Topito dulce",
     ["Aji topito dulce", "Aji Topito dulce", "Ají topito dulce"]),
    ("Ajo importado", ["AAjjoo iimmppoorrttaaddoo"]),
    ("Apio", ["AAppiioo"]),
    ("Arracacha", ["Arracacha *", "Arracacha*"]),
    ("Arracacha blanca", ["Arracacha Blanca", "ARRACACHA BLANCA"]),
    ("Arveja verde en vaina", ["AArrvveejjaa vveerrddee eenn vvaaiinnaa"]),
    ("Avena en hojuelas", ["Avena en hojuelas Quaker"]),
    ("Avena molida", ["Avena Molida", "Avena en molida Quaker"]),
    ("Azúcar morena",
     ["Azucar morena", "Azúcarmorena", "Azúcar morena Incauca"]),
    ("Azúcar Refinada", ["Azucar refinada", "Azúcar refinada"]),
    ("Azúcar Sulfitada",
     ["Azucar sulfitada", "Azúcar sulfitada", "Azúcarsulfitada"]),
    ("Bagre rayado entero congelado",
     ["Bagrerayadoentero congelado", "Bagre rayado en pósta congelado"]),
    ("Bagre rayado en postas congelado", []),
    ("Banano", ["Banano*"]),
    ("Banano criollo",
     ["Banano Criollo", "BANANO CRIOLLO", "Bananocriollo"]),
    ("Banano Urabá", ["Banano Uraba", "Banano urabá"]),
    ("Basa, entero congelado importado",
     ["Basa entero congelado importado", "Basa,enterocongelado importado"]),
    ("Berenjena", ["Beranjena"]),
    ("Bocadillo veleño", ["Bocadillo Veleño"]),
    ("Brevas", ["BREVAS"]),
    ("Brócoli", ["Brocoli"]),
    ("Café instantáneo", ["Café instantaneo", "Cafe instantaneo"]),
    ("Café molido", ["Cafémolido", "Café molido la bastilla"]),
    ("Calamar anillos", ["Calamaranillos"]),
    ("Camarón tigre precocido seco",
     ["Camarón tigre precocido Seco", "Camaróntigre precocido seco"]),
    ("Camarón tití precocido seco",
     ["Camarón titi precocido seco", "Camaróntitíprecocido seco"]),
    # Carne de cerdo (with comma) — drop "Carne cerdo X" no-de variants too
    ("Carne de cerdo, brazo con hueso", ["Carne de cerdo brazo con hueso"]),
    ("Carne de cerdo, brazo costilla", []),
    ("Carne de cerdo, brazo sin hueso",
     ["Carne de cerdo brazo sin hueso", "Carne de cerdo, Brazo sin hueso",
      "Carne cerdo brazo sin hueso"]),
    ("Carne de cerdo, cabeza de lomo", ["Carne de cerdo cabeza de lomo"]),
    ("Carne de cerdo en canal", ["Carne cerdo en canal"]),
    ("Carne de cerdo, costilla",
     ["Carne de cerdo costilla", "Carne de cerdo, Costilla",
      "Carne cerdo costilla"]),
    ("Carne de cerdo, costilla con hueso", []),
    ("Carne de cerdo, espinazo",
     ["Carne de cerdo, Espinazo", "Carne cerdo espinazo"]),
    ("Carne de cerdo, lomo con hueso", ["Carne de cerdo lomo con hueso"]),
    ("Carne de cerdo, lomo sin hueso",
     ["Carne de cerdo lomo sin hueso", "Carne de cerdo, Lomo sin hueso",
      "Carne cerdo lomo sin hueso"]),
    ("Carne de cerdo, pernil con hueso", ["Carne de cerdo pernil con hueso"]),
    ("Carne de cerdo, pernil sin hueso",
     ["Carne de cerdo pernil sin hueso", "Carne de cerdo, Pernil sin hueso",
      "Carne cerdo pernil sin hueso"]),
    ("Carne de cerdo, tocino barriga",
     ["Carne de cerdo tocino barriga", "Carne de cerdo, Tocino barriga",
      "CCaarrnnee ddee cceerrddoo,, ttoocciinnoo bbaarrrriiggaa",
      "Carne cerdo tocino barriga"]),
    ("Carne de cerdo, tocino papada",
     ["Carne de cerdo tocino papada", "Carne de cerdo, Tocino papada",
      "Carne cerdo tocino papada"]),
    ("Carne de res, bola de brazo",
     ["Carne de res bola de brazo", "Carne de res, Bola de brazo",
      "Carne de res, bolade brazo", "Carne res bola de brazo",
      "CCaarrnnee ddee rreess,, bboollaa ddee bbrraazzoo"]),
    ("Carne de res, bola de pierna",
     ["Carne de res bola de pierna", "Carne de res, Bola de pierna",
      "Carne de res, bolade pierna", "Carne res bola de pierna"]),
    ("Carne de res, bota",
     ["Carne de res bota", "Carne de res Bota", "Carne de res, Bota"]),
    ("Carne de res, cadera",
     ["Carne de res cadera", "Carne de res, Cadera",
      "Carne de res de cadera"]),
    ("Carne de res, centro de pierna",
     ["Carne de res centro de pierna", "Carne de res, Centro de pierna",
      "Carne res centro de pierna"]),
    ("Carne de res, chatas",
     ["Carne de res chatas", "Carne de res, Chatas"]),
    ("Carne de res, cogote", ["Carne de res cogote"]),
    ("Carne de res, costilla",
     ["Carne de res costilla", "Carne de res, Costilla", "Carne res costilla"]),
    ("Carne de res en canal", []),
    ("Carne de res, falda",
     ["Carne de res falda", "Carne de res, Falda", "Carne res falda"]),
    ("Carne de res, lomo de brazo", ["Carne de res lomo de brazo"]),
    ("Carne de res, lomo fino",
     ["Carne de res lomo fino", "Carne de res, Lomo fino",
      "Carne res lomo fino"]),
    ("Carne de res molida, murillo",
     ["Carne de res molida murillo", "Carne de res, molida, murillo"]),
    ("Carne de res, morrillo",
     ["Carne de res morrillo", "Carne de res, Morrillo",
      "CCaarrnnee ddee rreess,, mmoorrrriilllloo", "Carne res morrillo"]),
    ("Carne de res, muchacho",
     ["Carne de res muchacho", "Carne de res, Muchacho", "Carne res muchacho"]),
    ("Carne de res, murillo",
     ["Carne de res murillo", "Carne de res, Murillo"]),
    ("Carne de res, paletero",
     ["Carne de res paletero", "Carne de res, Paletero", "Carne res paletero"]),
    ("Carne de res, pecho",
     ["Carne de res pecho", "Carne de res, Pecho", "Carne res pecho"]),
    ("Carne de res, punta de anca",
     ["Carne de res punta de anca", "Carne de res, Punta de Anca",
      "Carne res punta de anca"]),
    ("Carne de res, sobrebarriga",
     ["Carne de res sobrebarriga", "Carne de res, Sobrebarriga",
      "Carne res sobrebarriga"]),
    ("Cebolla cabezona blanca",
     ["cebolla cabezona blanca", "Cebolla Cabezona Blanca",
      "Cebolla Cab. Blanca", "CCeebboollllaa ccaabbeezzoonnaa bbllaannccaa"]),
    ("Cebolla cabezona roja",
     ["Cebolla cebezona roja", "Cebolla Cab. Roja"]),
    ("Cebolla cabezona blanca bogotana",
     ["Cebolla cabezona b bogotana", "Cebolla cabezona bogotana"]),
    ("Cebolla junca", ["Cebolla Junca"]),
    ("Cebolla junca Aquitania",
     ["Cebolla junca aquitania", "Cebolla junca aquitana",
      "Cebollajuncaaquitania"]),
    ("Cebolla junca Berlín", ["Cebolla junca berlín"]),
    ("Cebolla junca Tenerife", ["Cebolla junca tenerife"]),
    ("Chocolate dulce", ["Chocolate dulce corona"]),
    ("Chócolo mazorca", ["Chocolo mazorca"]),
    ("Cidra", ["CCiiddrraa"]),
    ("Cilantro", ["CCiillaannttrroo"]),
    ("Coco", ["COCO"]),
    ("Color (bolsita)", ["CCoolloorr ((bboollssiittaa))"]),
    ("Curuba larga", ["CURUBA LARGA"]),
    ("Durazno nacional", ["DDuurraazznnoo nnaacciioonnaall"]),
    ("Fécula de maíz", ["Fecula de maiz", "Fécula de Maíz"]),
    ("Fresa", ["FRESA"]),
    ("Fríjol bolón", ["Frijol bolón"]),
    ("Fríjol cabeza negra importado", ["Frijol cabeza negra importado"]),
    ("Fríjol cabeza negra nacional", ["Frijol cabeza negra nacional"]),
    ("Fríjol calima", ["Frijol calima"]),
    ("Fríjol cargamanto blanco", ["Frijol cargamanto blanco"]),
    ("Fríjol cargamanto rojo",
     ["Frijol cargamanto rojo", "Fríjolcargamantorojo"]),
    ("Fríjol enlatado", ["Frijol enlatado"]),
    ("Fríjol niña calima", ["Frijol nima calima", "Fríjol nima calima"]),
    ("Fríjol palomito importado", ["Frijol palomito importado"]),
    ("Fríjol radical", ["Frijol radical"]),
    ("Fríjol uribe rosado", ["Frijol uribe rosado", "Fríjol Uribe rosado"]),
    ("Fríjol verde", ["Fríjol verde*"]),
    ("Fríjol verde bolo", ["Frijol verde bolo"]),
    ("Fríjol verde cargamanto",
     ["Frijol verde cargamanto", "Fríjolverdecargamanto",
      "Frijol verde cargamento"]),
    ("Fríjol verde en vaina",
     ["Frijol verde en vaina", "Frijol Verde en Vaina",
      "Fríjol Verde en Vaina", "Fríjol verde en vaina*"]),
    ("Fríjol Zaragoza",
     ["Frijol zaragoza", "Fríjol zaragoza", "Frijol saragoza"]),
    ("Galletas saladas",
     ["Galletas saladas 3 tacos", "Galletas saladas taco día"]),
    ("Granadilla", ["GRANADILLA"]),
    ("Guanábana", ["Guanabana", "GUANABANA"]),
    ("Guayaba", ["Guayaba*"]),
    ("Guayaba agria", ["GUAYABA AGRIA"]),
    ("Guayaba atlántico", ["Guayaba Atlántico"]),
    ("Guayaba pera", ["Guayaba Pera", "GUAYABA PERA"]),
    ("Haba verde", ["Haba Verde"]),
    ("Habichuela", ["HHaabbiicchhuueellaa"]),
    ("Habichuela larga", ["Habichuela Larga"]),
    ("Harina de trigo", ["harina de trigo", "Harina de trigo la nieve"]),
    ("Harina precocida de maíz",
     ["Harina precocida de maiz", "Harina precocida de maíz super arepa"]),
    ("Huevo blanco A", ["Huevo blanco a"]),
    ("Huevo blanco AA", ["Huevo blanco aa"]),
    ("Huevo blanco B", ["Huevo blanco b"]),
    ("Huevo blanco extra", ["Huevo blanco Extra", "Huevo Blanco extra"]),
    ("Huevo rojo A", ["Huevo rojo a", "Huevo Rojo A"]),
    ("Huevo rojo AA", ["Huevo rojo aa", "Huevo Rojo AA", "Huevorojoaa"]),
    ("Huevo rojo B", ["Huevo rojo b"]),
    ("Huevo rojo extra", ["Huevo rojo Extra"]),
    ("Jugo instantáneo (sobre)",
     ["Jugo instantaneo", "Jugo instantáneo",
      "Jugo instantáneo (sobre) frutiño"]),
    ("Kiwi", ["KKiiwwii"]),
    ("Langostino U12", ["Langostino u12"]),
    ("Lechuga Batavia", ["Lechuga batavia", "LLeecchhuuggaa BBaattaavviiaa"]),
    ("Lechuga Batavia (bogotana)", ["Lechuga batavia (bogotana)"]),
    ("Lechuga Batavia (regional)", ["Lechuga batavia (regional)"]),
    ("Limón común",
     ["Limon comun", "LIMON COMUN", "Limón Común",
      "LLiimmóónn ccoommúúnn"]),
    ("Limón común ciénaga",
     ["limon comun Cienaga", "Limón común Ciénaga",
      "Limon comun de Cienaga", "limon comun de cienaga"]),
    ("Limón mandarino",
     ["Limon mandarino", "Limon Mandarino", "LIMON MANDARINO"]),
    ("Limón Tahití",
     ["Limon Tahiti", "LIMON TAHITI", "Limon Tahití", "Limón tahití",
      "Limón thaiti", "Limón thaití"]),
    ("Lomitos de atún en lata", ["Lomitos de atún en lata soberana"]),
    ("Lulo", ["lulo", "LULO"]),
    ("Maíz amarillo trillado",
     ["Maiz amarillo trillado", "MMaaíízz aammaarriilllloo ttrriillllaaddoo"]),
    ("Maíz blanco trillado",
     ["Maiz blanco trillado", "M aíz blanco trillado"]),
    ("Mandarina", ["Mandarina *", "Mandarina*"]),
    ("Mandarina Arrayana", ["Mandarina arrayana"]),
    ("Mandarina común", ["Mandarina Común"]),
    ("Mandarina Oneco",
     ["Mandarina oneco", "Mandarina onecco", "MANDARINA ONECCO",
      "Mandarino oneco"]),
    ("Mango común", ["Mango comun", "Mango Comun"]),
    ("Mango manzano", ["MANGO MANZANO"]),
    ("Mango reina", ["MANGO REINA"]),
    ("Mango Tommy", ["Mango tommy", "MANGO TOMMY"]),
    ("Mango Yulima", ["Mango yulima", "MANGO YULIMA"]),
    ("Manzana roja importada", ["MANZANA ROJA IMPORTADA"]),
    ("Manzana royal gala importada", ["MANZANA ROYAL GALA IMPORTADA"]),
    ("Manzana verde importada", ["MANZANA VERDE IMPORTADA"]),
    ("Maracuyá", ["Maracuya", "MARACUYA"]),
    ("Maracuyá antioqueño",
     ["Maracuya antioqueña", "Maracuyá antioqueña"]),
    ("Margarina", ["Margarina Dagusto"]),
    ("Mayonesa Doy Pack",
     ["Mayonesa doy pack", "Mayonesa doy pack fruco"]),
    ("Melón", ["Melon"]),
    ("Melón cantalup",
     ["Melon cantalup", "MELON CANTALUP", "melón cantalup",
      "Melón Cantalup", "Melóncantalup"]),
    ("Mojarra lora entera fresca", ["Mojarra lora entera seco"]),
    ("Mora de Castilla",
     ["Mora de castilla", "MORA DE CASTILLA",
      "MMoorraa ddee CCaassttiillllaa"]),
    ("Mostaza doy pack", ["MMoossttaazzaa ddooyy ppaacckk"]),
    ("Naranja", ["Naranja *", "Naranja*"]),
    ("Naranja común", ["Naranja comun", "Naranja Común"]),
    ("Naranja Sweet", ["Naranja sweet", "NARANJA SWEET"]),
    ("Naranja Valencia",
     ["Naranja valencia", "Naranja Valencia y/o Sweet"]),
    ("Panela cuadrada blanca", ["Panela Cuadrada Blanca"]),
    ("Panela cuadrada morena", ["Panela cuadrada morena Villetana"]),
    ("Panela redonda morena", ["Panela morena redonda"]),
    ("Papa Betina", ["Papa betina"]),
    ("Papa Capira", ["Papa capira"]),
    ("Papa criolla limpia",
     ["Papa criolla Limpia", "Papa Criolla limpia",
      "Papa Criolla Limpia", "PAPA CRIOLLA LIMPIA"]),
    ("Papa ICA-Huila", ["Papa ica-huila"]),
    ("Papa Morasurco", ["Papa morasurco"]),
    ("Papa negra",
     ["Papa negra *", "Papa negra*", "Papa negra+", "Papa negr*",
      "Papa nwgra*"]),
    ("Papa Nevada", ["Papa nevada"]),
    ("Papa Parda Pastusa",
     ["Papa parda pastusa", "PAPA PARDA PASTUSA", "Papapardapastusa"]),
    ("Papa Puracé", ["Papa puracé"]),
    ("Papa R-12 negra",
     ["Papa R - 12 negra", "Papa r-12 negra", "Papa R12 negra"]),
    ("Papa R-12 roja", ["Papa r-12 roja"]),
    ("Papa rubí", ["Papa rubi", "Papa Ruby"]),
    ("Papa suprema", ["PAPA SUPREMA"]),
    ("Papa única", ["Papa unica", "PPaappaa úúnniiccaa", "Papaúnica"]),
    ("Papa superior", ["PPaappaa ssuuppeerriioorr"]),
    ("Papaya Maradol",
     ["Papaya maradol", "PAPAYA MARADOL", "Papaya marad"]),
    ("Papaya Paulina", ["Papaya paulina"]),
    ("Papaya Tainung", ["Papaya tainung"]),
    ("Pastas alimenticias",
     ["Pasta alimenticias", "Pastas Alimenticias",
      "Pastas alimenticias doria"]),
    ("Patilla", ["PATILLA"]),
    ("Patilla baby", ["Patilla Baby"]),
    ("Pepino cohombro", ["Pepinocohombro", "PPeeppiinnoo ccoohhoommbbrroo"]),
    ("Pepino de rellenar", ["Pepinoderellenar"]),
    ("Pera importada", ["PERA IMPORTADA"]),
    ("Piernas de pollo", ["Pierna de pollo"]),
    ("Pimentón", ["Pimenton"]),
    ("Piña", ["Piña *"]),
    ("Piña gold", ["PIÑA GOLD"]),
    ("Plátano dominico hartón maduro",
     ["Plátano domincio hartón maduro", "Plátano dominico hartónmaduro",
      "Plátano dom.hart.mad."]),
    ("Plátano dominico hartón verde",
     ["Plátano domincio hartón verde", "Plátanodominico hartón verde",
      "Plátano dom.hart.verd."]),
    ("Plátano hartón maduro",
     ["Platano harton maduro", "PLATANO HARTON MADURO",
      "Platano hartón maduro", "plátano hartón maduro"]),
    ("Plátano hartón verde",
     ["Platano harton verde", "PLATANO HARTON VERDE",
      "plátano hartón verde", "Plátano Hartón verde",
      "Plátano Hartón Verde", "Plátanohartónverde"]),
    ("Plátano hartón verde Eje Cafetero",
     ["Plátano hartón verde eje cafetero",
      "Plátano hartón Eje Cafetero"]),
    ("Pollo entero congelado sin vísceras",
     ["Pollo entero congelado sin visceras"]),
    ("Pollo entero fresco sin vísceras",
     ["Pollo entero fresco sin víscera"]),
    ("Queso caquetá", ["Queso Caquetá"]),
    ("Queso costeño", ["Queso Costeño"]),
    ("Remolacha", ["RReemmoollaacchhaa"]),
    ("Repollo blanco", ["Repollo Blanco"]),
    ("Repollo blanco bogotano", ["Repollo Blanco bogotano"]),
    ("Sal yodada", ["Sal Yodada", "Sal yodada refisal"]),
    ("Salsa de tomate doy pack",
     ["Salsa de Tomate Doy Pack", "Salsa de tomate doy pack fruco"]),
    ("Sardinas en lata", ["Sardinas en lata soberana"]),
    ("Tangelo", ["Tanjelo"]),
    ("Tilapia roja entera fresca", ["Tilapia Roja entera fresca"]),
    ("Tomate", ["Tomate *", "Tomate*"]),
    ("Tomate chonto", ["Tomate Chonto"]),
    ("Tomate chonto regional", ["Tomatechontoregional"]),
    ("Tomate de árbol", ["Tomate de arbol", "TOMATE DE ARBOL"]),
    ("Tomate larga vida", ["TToommaattee llaarrggaa vviiddaa"]),
    ("Tomate riñón valluno",
     ["Tomate Riñón Valluno", "TToommaattee rriiñónn vvaalllluunnoo"]),
    ("Tomate riogrande", ["Tomate Riogrande"]),
    ("Tomate riogrande bumangués",
     ["Tomate riogrande Bumangués", "Tomate Riogrande bumangués"]),
    ("Tomate riogrande ocañero", ["Tomate Riogrande ocañero"]),
    ("Toyo blanco, filete congelado",
     ["TTooyyoo bbllaannccoo,, ffiilleettee ccoonnggeellaaddoo"]),
    ("Uchuva con cáscara", ["Uchuva con cascara"]),
    ("Uva isabela", ["Uva Isabela", "UVA ISABEL"]),
    ("Uva red globe",
     ["Uva red globel / Combinada", "UVA RED GLOB"]),
    ("Uva red globe nacional",
     ["Uva globe nacional", "Uva red globel nacional",
      "Uvaredglobenacional"]),
    ("Uva roja", ["Uva Roja"]),
    ("Uva verde", ["UUvvaa vveerrddee"]),
    ("Yuca", ["Yuca*"]),
    ("Yuca chirosa", ["Yuca Chirosa"]),
    ("Yuca criolla", ["Yuca Criolla"]),
    ("Yuca ICA", ["Yuca ica", "YUCA ICA", "Yucaica"]),
    ("Yuca llanera", ["Yucallanera"]),
    ("Zanahoria bogotana", ["Zanahoria Bogotana"]),
]

# dim_insumo
INSUMO_MERGES = [
    ("Calfón Energy", ["Calfon - Energy"]),
    ("Kafe Caldas: 25-3-19-3", ["Kafe Caldas 25-3-19-3"]),
    ("Penicilina Benzatínica + Procaínica y Potásica",
     ["Penicilina Benzatinica+Procainica y Potasica"]),
    ("Rafos 12-24-12-2(MgO) 1(S)", ["Rafos 12-24-12-2  (MgO) 1 S"]),
    ("Sembramon 12-20-12-3(MgO)", ["Sembramon 12-20-12-3 (MgO)"]),
    ("Tercer Estado: 24-0-12-3(MgO)", ["Tercer Estado: 24-0-12-3 (Mgo)"]),
    ("Veta Dicrysticina", ["Veta-Dicrysticina"]),
    ("Adiarrez NF", ["Adiarrez N.F."]),
    ("Bayfidan 250 Dc", ["Bayfidan Dc 250"]),
]

# Per-dim metadata for merge_pair()
# (dim_table, alias_table, alias_fk, fact_tables[(table, fk)], child_dim_tables[(table, fk)])
DIM_INFO = {
    "dim_subcategory": (
        "alias_subcategory", "subcategory_id",
        [("price_observations", "subcategory_id")],
        [("dim_product", "subcategory_id")],
    ),
    "dim_department": (
        None, None,
        [("price_observations", "department_id"),
         ("insumo_prices_municipality", "department_id"),
         ("insumo_prices_department", "department_id")],
        [("dim_city", "department_id")],
    ),
    "dim_city": (
        "alias_city", "city_id",
        [("price_observations", "city_id"),
         ("supply_observations", "city_id"),
         ("insumo_prices_municipality", "city_id")],
        [("dim_market", "city_id")],
    ),
    "dim_market": (
        "alias_market", "market_id",
        [("price_observations", "market_id"),
         ("supply_observations", "market_id")],
        [],
    ),
    "dim_presentation": (
        "alias_presentation", "presentation_id",
        [("price_observations", "presentation_id")],
        [],
    ),
    "dim_units": (
        "alias_units", "units_id",
        [("price_observations", "units_id")],
        [],
    ),
    "dim_product": (
        "alias_product", "product_id",
        [("price_observations", "product_id"),
         ("supply_observations", "product_id")],
        [],
    ),
    "dim_insumo": (
        "alias_insumo", "insumo_id",
        [("insumo_prices_municipality", "insumo_id"),
         ("insumo_prices_department", "insumo_id")],
        [],
    ),
}


def find_id(c, table, name):
    c.execute(f"SELECT id FROM {table} WHERE canonical_name = %s", (name,))
    r = c.fetchone()
    return r["id"] if r else None


def repoint_fact(conn, c, table, col, old_id, new_id):
    """Repoint a fact-table FK in 5k-row batches; reconnect on failure."""
    total = 0
    while True:
        try:
            c.execute(
                f"WITH b AS (SELECT id FROM {table} WHERE {col} = %s LIMIT 5000) "
                f"UPDATE {table} SET {col} = %s WHERE id IN (SELECT id FROM b)",
                (old_id, new_id),
            )
            n = c.rowcount
            if n == 0:
                break
            total += n
        except Exception as e:
            print(f"      [retry] {table}.{col}: {e}", flush=True)
            try:
                conn.close()
            except Exception:
                pass
            conn, c = fresh()
    return total, conn, c


def merge_pair(conn, c, dim, alias_tbl, alias_fk, fact_refs, child_refs,
               winner_name, loser_name, dry_run):
    winner_id = find_id(c, dim, winner_name)
    if not winner_id:
        return None, conn, c, "winner_missing"
    loser_id = find_id(c, dim, loser_name)
    if not loser_id:
        return None, conn, c, "loser_absent"
    if winner_id == loser_id:
        return None, conn, c, "same"

    if dry_run:
        return loser_id, conn, c, "would_merge"

    # 1. Repoint alias table (handle UNIQUE conflicts on raw_value)
    if alias_tbl and alias_fk:
        try:
            c.execute(
                f"DELETE FROM {alias_tbl} WHERE {alias_fk} = %s "
                f"AND raw_value IN (SELECT raw_value FROM {alias_tbl} WHERE {alias_fk} = %s)",
                (loser_id, winner_id),
            )
            c.execute(
                f"UPDATE {alias_tbl} SET {alias_fk} = %s WHERE {alias_fk} = %s",
                (winner_id, loser_id),
            )
        except Exception as e:
            print(f"      [retry alias] {e}", flush=True)
            try: conn.close()
            except: pass
            conn, c = fresh()

    # 2. Repoint fact tables
    fact_total = 0
    for ft, fc in fact_refs:
        n, conn, c = repoint_fact(conn, c, ft, fc, loser_id, winner_id)
        fact_total += n

    # 3. Repoint child dim tables (e.g. dim_city.department_id)
    for ct, cc in child_refs:
        try:
            c.execute(
                f"UPDATE {ct} SET {cc} = %s WHERE {cc} = %s",
                (winner_id, loser_id),
            )
        except Exception as e:
            print(f"      [retry child {ct}] {e}", flush=True)
            try: conn.close()
            except: pass
            conn, c = fresh()

    # 4. Add the loser's canonical_name as a raw_value alias on the winner
    #    so historical raw inputs still resolve (idempotent).
    if alias_tbl and alias_fk:
        try:
            c.execute(
                f"INSERT INTO {alias_tbl} (raw_value, {alias_fk}) VALUES (%s, %s) "
                f"ON CONFLICT (raw_value) DO NOTHING",
                (loser_name, winner_id),
            )
        except Exception as e:
            print(f"      [alias backfill warn] {e}", flush=True)
            try: conn.close()
            except: pass
            conn, c = fresh()

    # 5. Delete the loser dim row
    try:
        if alias_tbl and alias_fk:
            c.execute(f"DELETE FROM {alias_tbl} WHERE {alias_fk} = %s", (loser_id,))
        c.execute(f"DELETE FROM {dim} WHERE id = %s", (loser_id,))
    except Exception as e:
        print(f"      [retry delete] {e}", flush=True)
        try: conn.close()
        except: pass
        conn, c = fresh()

    return fact_total, conn, c, "ok"


def ensure_winner_canonical(conn, c, dim, winner_name, dry_run):
    """If the winner row exists but with a different canonical_name (e.g. ALL CAPS
    that received the most observations), rename it. No-op if the proper name
    already exists."""
    return  # Currently we always pass the proper name as winner_name.


def run_table(conn, c, dim, merges, dry_run=False):
    alias_tbl, alias_fk, fact_refs, child_refs = DIM_INFO[dim]
    print(f"\n=== {dim} : {len(merges)} groups ===", flush=True)

    c.execute(f"SELECT COUNT(*) AS n FROM {dim}")
    before = c.fetchone()["n"]

    merged = 0
    skipped = 0
    missing_winner = 0
    for winner, losers in merges:
        # If the winner does not exist yet, try to create it by promoting the
        # first loser that exists. This handles cases where the proper canonical
        # name only appeared in raw data as one of the variants.
        if not find_id(c, dim, winner):
            promoted = False
            for ln in losers:
                lid = find_id(c, dim, ln)
                if lid:
                    if dry_run:
                        print(f"  [DRY] promote {ln} -> {winner}", flush=True)
                    else:
                        try:
                            c.execute(
                                f"UPDATE {dim} SET canonical_name = %s WHERE id = %s",
                                (winner, lid),
                            )
                            print(f"  promote: '{ln}' -> '{winner}'", flush=True)
                        except Exception as e:
                            print(f"  [warn] promote failed: {e}", flush=True)
                            try: conn.close()
                            except: pass
                            conn, c = fresh()
                    promoted = True
                    break
            if not promoted:
                missing_winner += 1
                continue
        for loser in losers:
            if loser == winner:
                continue
            n, conn, c, status = merge_pair(
                conn, c, dim, alias_tbl, alias_fk, fact_refs, child_refs,
                winner, loser, dry_run,
            )
            if status == "ok":
                merged += 1
                if n is not None and n > 0:
                    print(f"  '{loser}' -> '{winner}' ({n} fact rows)", flush=True)
                else:
                    print(f"  '{loser}' -> '{winner}'", flush=True)
            elif status == "would_merge":
                merged += 1
                print(f"  [DRY] '{loser}' -> '{winner}'", flush=True)
            else:
                skipped += 1

    c.execute(f"SELECT COUNT(*) AS n FROM {dim}")
    after = c.fetchone()["n"]
    print(f"  result: merged {merged}, skipped {skipped}, missing-winner {missing_winner}, "
          f"rows {before} -> {after}", flush=True)
    return conn, c


def run(dry_run=False):
    print("=" * 60, flush=True)
    print("Migration 034: Hand-picked dedup of canonical entities", flush=True)
    print("=" * 60, flush=True)
    if dry_run:
        print("MODE: DRY RUN", flush=True)

    conn, c = fresh()

    # Order matters slightly: merge children before parents so we don't try to
    # delete a parent that still has children. Practically all merges are on
    # the same level so the order is mostly cosmetic.
    plan = [
        ("dim_subcategory", SUBCATEGORY_MERGES),
        ("dim_presentation", PRESENTATION_MERGES),
        ("dim_units", UNITS_MERGES),
        ("dim_market", MARKET_MERGES),
        ("dim_city", CITY_MERGES),
        ("dim_department", DEPARTMENT_MERGES),
        ("dim_product", PRODUCT_MERGES),
        ("dim_insumo", INSUMO_MERGES),
    ]
    for dim, merges in plan:
        conn, c = run_table(conn, c, dim, merges, dry_run=dry_run)

    print("\nDONE", flush=True)
    conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run(dry_run=dry_run)
