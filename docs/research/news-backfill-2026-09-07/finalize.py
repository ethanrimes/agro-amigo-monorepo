"""Assemble this one-time, reviewed research collection; no network or publishing."""
import copy
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote
from validate import canonical, iso, validate

ROOT = Path(__file__).resolve().parent
NOW = datetime.now(timezone.utc)
STAMP = NOW.isoformat(timespec='seconds')

def read(name):
    return json.loads((ROOT / name).read_text())

def write(name, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

batch_names = ['luna-initial.json', 'more-discoveries.json', 'known-discoveries.json', 'remaining-known.json']
if (ROOT / 'regional-remaining.json').exists():
    batch_names.append('regional-remaining.json')
batches = [read(n) for n in batch_names]
stories = []
for name, batch in zip(batch_names, batches):
    for s in batch.get('stories', []):
        s['discovery_batch'] = name
        stories.append(s)

def add(source, url, date, label, category, relevance, departments=(), municipalities=(), crops=(), inputs=(), tags=(), **extra):
    stories.append(dict(
        canonical_url=url, source_name=source, source_type='comunicado oficial', title=None,
        factual_label_es=label, published_at=date+'T00:00:00-05:00', date_precision='date',
        updated_at=None, retrieved_at=STAMP, retrieval_time_precision='parent_audit_batch',
        decision='include', confidence='alta', primary_category=category, tags=list(tags),
        crops=list(crops), inputs=list(inputs), named_markets=[],
        geography=dict(countries=['Colombia'], departments=list(departments), municipalities=list(municipalities)),
        colombia_relevance_es=relevance, evidence_urls=[url],
        publication_evidence=dict(url=url, method='original-page publication date checked by parent', value=date),
        source_valid_until=None, rights_status='unverified', discovery_batch='parent_verified', **extra))

MIN = 'https://www.minagricultura.gov.co/el-ministerio/sala-de-p/noticias/'
add('Ministerio de Agricultura', MIN+'minagricultura-explora-alianza-con-inversionistas-internacionales-para-ampliar-la-produccion-industrial-de-harina-de-yuca-en-sucre-y-cordoba-y-de-maiz-en-valle-del-cauca-1', '2026-09-05',
    'MinAgricultura e Ingredion exploraron ampliar la producción industrial de yuca en Sucre y Córdoba y de maíz en Valle del Cauca.', 'abastecimiento_y_cosechas',
    'Conversaciones sobre demanda industrial colombiana; no constituyen una oferta de compra ni una inversión confirmada.',
    departments=['Sucre', 'Córdoba', 'Valle del Cauca'], crops=['yuca', 'maíz'], tags=['demanda industrial', 'alianza en estudio'])
add('Ministerio de Agricultura', MIN+'minagricultura-implementa-alianza-estrategica-para-poner-en-marcha-programa-jovenes-milagro-en-700-municipios', '2026-09-05',
    'MinAgricultura anunció una alianza para formación y proyectos productivos de jóvenes rurales, con una meta de 700 municipios.', 'apoyos_y_normativa',
    'Anuncio nacional de apoyo a jóvenes rurales; la página no confirma plazo de inscripción ni elegibilidad individual.', tags=['juventud rural', 'formación'])
AGRO = 'https://www.agrosavia.co/noticias/'
add('AGROSAVIA', AGRO+'agrosavia-y-la-comunidad-inga-de-santiago-putumayo-fortalecen-la-conservación-de-recursos-genéticos-y-las-casas-comunitarias-de-semillas', '2026-08-31',
    'AGROSAVIA y la comunidad Inga de Santiago trabajaron en conservación, almacenamiento y acceso comunitario a recursos genéticos y semillas.', 'investigacion_y_cultivos',
    'Experiencia de conservación de semillas en Putumayo; no anuncia disponibilidad comercial de variedades.', departments=['Putumayo'], municipalities=['Santiago'], inputs=['semillas'], tags=['agrobiodiversidad', 'comunidad Inga'])
add('AGROSAVIA', AGRO+'más-de-20-actores-fortalecen-la-innovación-agropecuaria-del-cesar-en-el-marco-de-la-mectia-impulsada-por-agrosavia', '2026-09-01',
    'La mesa de innovación agropecuaria del Cesar revisó iniciativas de ganadería sostenible, invernaderos y transferencia tecnológica.', 'investigacion_y_cultivos',
    'Contexto regional de investigación publicado en septiembre sobre reuniones del 23 de julio y 20 de agosto; no es una convocatoria vigente.', departments=['Cesar'], municipalities=['Valledupar', 'La Paz'], tags=['innovación', 'ganadería', 'agricultura protegida'], event_dates=['2026-07-23', '2026-08-20'])
add('AGROSAVIA', AGRO+'mujeres-que-cultivan-futuro-en-el-catatumbo', '2026-09-03',
    'Una experiencia cacaotera en San Calixto muestra mejoras en fermentación, secado y asociatividad con liderazgo de mujeres rurales.', 'investigacion_y_cultivos',
    'Caso de producción y poscosecha en Catatumbo; los precios relatados corresponden a la historia de una finca y no son cotizaciones actuales.', departments=['Norte de Santander'], municipalities=['San Calixto', 'Teorama'], crops=['cacao', 'plátano', 'yuca', 'maíz'], tags=['poscosecha', 'mujeres rurales', 'asociatividad'])
ICA = 'https://www.ica.gov.co/noticias/'
add('ICA', ICA+'ica-el-agro-actua-fenomenodeelnino', '2026-08-26',
    'La campaña El Agro Actúa del ICA recordó medidas de observación sanitaria, manejo responsable del agua y uso de material vegetal autorizado.', 'sanidad_agropecuaria',
    'Orientación preventiva general para Colombia, sin pronóstico meteorológico puntual ni brote nuevo confirmado.', inputs=['semillas', 'material vegetal'], tags=['prevención', 'agua', 'variabilidad climática'])
add('ICA', ICA+'ica-fortalece-bienestar-animal-laguajira', '2026-08-27',
    'El ICA capacitó a 13 productores de Albania en bienestar bovino y condiciones para avanzar hacia certificación de predios.', 'sanidad_agropecuaria',
    'Capacitación localizada en La Guajira; no equivale a certificar esos predios.', departments=['La Guajira'], municipalities=['Albania'], tags=['ganadería bovina', 'bienestar animal'])
add('ICA', ICA+'ica-certificacion-porcicultores-puertoasis', '2026-09-01',
    'ICA y SENA reconocieron la formación de 19 porcicultores de Puerto Asís en preparación de cortes de carne para venta minorista.', 'eventos_y_formacion',
    'Capacitación para agregar valor en la cadena porcícola de Putumayo; los certificados corresponden al curso, no a sanidad de predios.', departments=['Putumayo'], municipalities=['Puerto Asís'], tags=['porcicultura', 'valor agregado', 'formación'])

for s in stories:
    u = unquote(s['canonical_url'])
    s.setdefault('audit_notes', [])
    # Original six agent timestamps were assigned ahead of execution. Record the
    # completed parent audit instead, explicitly as a batch time, not exact fetch.
    if s['discovery_batch'] == 'luna-initial.json' and s.get('retrieved_at') == '2026-09-08T04:36:00Z':
        s['retrieved_at'] = STAMP
        s['retrieval_time_precision'] = 'parent_audit_batch'
        s['audit_notes'].append('Hora original del agente no fiable; se registra la finalización de la revisión de la página original por el asistente principal.')
    s.setdefault('retrieval_time_precision', 'agent_batch_reported')
    s.setdefault('geography', {}).setdefault('municipalities', [])
    s.setdefault('livestock', [])
    s.setdefault('secondary_categories', [])
    for term in ('ganadería', 'ganadería bovina', 'peces', 'camarón'):
        if term in s.get('crops', []):
            s['crops'].remove(term); s['livestock'].append(term)
    if 'terremoto' in u or 'ayuda-a-los-pequenos-ganaderos' in u:
        s['primary_category'] = 'apoyos_y_normativa'
        s['expiry_reason'] = 'Anuncio de apoyo o recuperación: 14 días editoriales; no es una alerta meteorológica en tiempo real.'
    if 'escucha-los-productores-de-arroz' in u:
        s['primary_category'] = 'apoyos_y_normativa'
        s['secondary_categories'] = ['precios_y_mercados']
        s['geography']['departments'] = []
        s['geography']['regions'] = ['Caribe', 'La Mojana', 'sur de Bolívar']
        s['inputs'] = ['semillas certificadas']
    if 'bacterias-' in u:
        s['primary_category'] = 'investigacion_y_cultivos'
        s['secondary_categories'] = ['sanidad_agropecuaria']
        s['inputs'] = []
        s['audit_notes'].append('Investigación de biocontrol, no producto comercial ni tratamiento de campo validado.')
    if 'pepsico-y-minagricultura' in u:
        s['factual_label_es'] = 'MinAgricultura y PepsiCo exploraron una alianza para papa, plátano y maíz amarillo, con atención al potencial de riego del Tolima.'
        s['colombia_relevance_es'] += ' Se trata de conversaciones; no es una oferta de compra abierta.'
    if 'fortalecen-la-produccion-de-cafe' in u:
        s['published_at'] = '2026-08-25T17:21:00-05:00'; s['date_precision'] = 'minute'
        s['inputs'] = ['compost', 'biofertilizantes']; s['livestock'] = ['cuyes']
    if 'incendios-han-arrasado' in u:
        s['published_at'] = '2026-08-27T12:56:00-05:00'; s['date_precision'] = 'minute'
        s['expiry_rule_hours'] = 48; s['expiry_reason'] = 'Reporte operativo de riesgo: 48 horas; conservar como noticia histórica.'
        s['event_group'] = 'incendios-narino-agosto-2026'
    if 'lleva-ayudas-a-50-familias' in u:
        s['published_at'] = '2026-09-03T21:12:00-05:00'; s['date_precision'] = 'minute'
        s['event_group'] = 'incendios-narino-agosto-2026'
        s['audit_notes'].append('Desarrollo posterior de recuperación, distinto del balance de daños del 27 de agosto.')
    if 'el-precio-del-cafe-colombiano' in u:
        s['published_at'] = '2026-08-27T00:35:00-05:00'; s['date_precision'] = 'minute'
        s['evidence_urls'] = [s['canonical_url']]; s['publication_evidence']['url'] = s['canonical_url']
        s['expiry_rule_hours'] = 48; s['expiry_reason'] = 'Cotización puntual: 48 horas; no usar como precio actual.'
        s['observation_period'] = '2026-08-26'
        s['attribution_chain'] = ['Diario del Sur', 'Caracol Radio', 'FNC (no verificado directamente en esta ejecución)']
    if s['source_name'] == 'Cenicafé':
        s['alternate_urls'] = [s['canonical_url']]
        s['canonical_url'] = 'https://publicaciones.cenicafe.org/index.php/boletin_agrometeorologico/article/view/5721'
        s['expiry_rule_hours'] = 48; s['expiry_reason'] = 'Pronóstico: 48 horas en el feed según la regla preparada; el documento mensual conserva utilidad como referencia fechada.'
        s['reference_period'] = '2026-09'
        s['license_note'] = 'CC BY-NC-ND 4.0 visible; los derechos de reutilización comercial no se establecieron.'
    if s['source_name'] == 'Fenalce':
        s['action_window'] = dict(start='2026-09-01', end='2026-09-15', applies_to='zonas productoras de Córdoba', evidence_url=s['canonical_url'])
        s['expiry_reason'] = 'Hasta el final de la ventana de siembra indicada por Fenalce para Córdoba, limitado a 14 días desde publicación.'
        s['audit_notes'].append('Orientación regional de Fenalce; requiere ajustarse a condiciones locales y acompañamiento técnico.')
    if s['source_name'] == 'Fedearroz':
        s['candidate_date_hint'] = '2026-09-05 (inicio del pronóstico, no fecha de publicación comprobada)'
        s['published_at'] = None; s['date_precision'] = 'unknown'; s['crops'] = ['arroz']
        s['display_expires_at'] = None; s['source_valid_until'] = None; s['review_at'] = None
        s['expiry_reason'] = 'Fecha de publicación sin comprobar; no entra al feed.'
    if 'alianzas-que-hacen-crecer' in u:
        s['crops'] = []; s['inputs'] = ['semillas']
    if 'desempleo-rural' in u:
        s['observation_period'] = '2026-07'
        s['audit_notes'].append('Estadística agregada basada en GEIH/DANE; no es un benchmark de costos de una finca.')
    if 'vigilancia-fitosanitaria-palmadeaceite' in u:
        s['colombia_relevance_es'] = 'Acompañamiento y vigilancia sanitaria de palma en Cesar; la nota no confirma un brote nuevo.'
    if 'encuentro-linkata-florencia' in u:
        s['crops'] = []; s['publication_evidence']['method'] = 'original-page publication date and body, checked by parent'
        s['publication_evidence']['value'] = 'Agosto 28, 2026'
        s['tags'] = ['bioeconomía', 'extensión', 'agroforestería']
    if 'bioinnova-páramos-y-bosques' in u:
        s['decision'] = 'include'; s['confidence'] = 'alta'; s.pop('review_reason', None)
        s['announcement_date'] = '2026-08-24'
        s['publication_evidence']['method'] = 'original-page publication header, checked by parent'
        s['publication_evidence']['value'] = 'Agosto 25, 2026'
        s['inputs'] = []
        s['audit_notes'].append('La página publica el 25 de agosto una comunicación fechada el 24: fechas distintas de publicación y anuncio. No se verificó un plazo de cierre; confirmar disponibilidad con AGROSAVIA.')
    if 'acompanamiento-tecnico-ica-isla' in u:
        s['crops'] = []; s['inputs'] = ['plántulas', 'material vegetal']
    if 'ica-impulsa-acuicultura' in u:
        s['inputs'] = []; s['tags'] = ['bioseguridad', 'acuicultura', 'formación']
    if s.get('date_precision') == 'minute' and s['source_name'] == 'Diario del Sur':
        s['publication_evidence']['value'] = s['published_at']
        s['publication_evidence']['method'] = 'original-page visible date and time, checked by parent'
        s['time_assumption'] = 'Hora visible interpretada en America/Bogota; zona horaria no declarada por la página.'
    elif s.get('date_precision') == 'date':
        s['time_assumption'] = 'Solo fecha publicada: se usa 00:00 America/Bogota para filtros y caducidad; no es una hora de publicación observada.'
    if s['decision'] == 'include':
        s.setdefault('expiry_rule_hours', 14 * 24)
        expiry = iso(s['published_at']) + timedelta(hours=s['expiry_rule_hours'])
        if s['source_name'] == 'Fenalce':
            expiry = min(expiry, iso('2026-09-15T23:59:59-05:00'))
        s['display_expires_at'] = expiry.isoformat()
        s['review_at'] = s['display_expires_at']
        s.setdefault('expiry_reason', 'Noticia general o referencia: 14 días desde publicación.')
        s['status'] = 'expired' if expiry <= NOW else 'active'
    s['rights_status'] = 'unverified'
    s['id'] = hashlib.sha256(canonical(s['canonical_url']).encode()).hexdigest()[:20]

# The batch files are raw agent output. This collection supersedes their counts,
# timing, tags, access claims and expiry decisions after review.
dedup = {}
for s in stories:
    k = canonical(s['canonical_url'])
    if k not in dedup:
        dedup[k] = s
    else:
        dedup[k].setdefault('alternate_urls', []).append(s['canonical_url'])
stories = sorted(dedup.values(), key=lambda s: (s.get('published_at') or '', s['source_name']), reverse=True)
included = [s for s in stories if s['decision'] == 'include']
counts = Counter(s['source_name'] for s in included)

catalog = json.loads((ROOT.parents[1] / 'automation/news-cloud-job.json').read_text())['sources']
coverage = {s['name']: dict(source=s['name'], url=s['url'], status='not_reviewed_catalog_candidate', checked_at=None, attempts=[]) for s in catalog}
for batch in batches:
    for c in batch.get('coverage', []):
        source = c.get('source', c.get('source_name'))
        if source not in coverage: continue
        if c.get('status') == 'not_reviewed_catalog_candidate': continue
        coverage[source]['attempts'].append(c)
        coverage[source].update({k: v for k, v in c.items() if k != 'source'})
for c in read('parent-discovery.json')['coverage']:
    row = coverage[c['source']]
    row['attempts'].append(c)
    row.update(status='search_attempted_no_verified_inclusion', checked_at=c['checked_at'], reason='Búsqueda parcial; no se comprobó un artículo original dentro de la ventana.')
for name in ['Fedepalma', 'Fedepapa', 'Asohofrucol']:
    coverage[name].update(status='search_attempted_no_verified_inclusion', checked_at=STAMP, checked_at_precision='parent_audit_batch', reason='Búsqueda de dominio realizada por el asistente principal: resultados antiguos o páginas sin fecha individual comprobada.')
for name, n in counts.items():
    if name in coverage:
        coverage[name].update(status='selected_originals_verified', checked_at=STAMP, checked_at_precision='audit_batch', included_count=n, reason='Fechas y contenido de páginas originales seleccionadas comprobados; cobertura parcial del archivo.')
coverage['Fedearroz'].update(status='original_read_publication_date_unresolved', reason='Se leyó el boletín pero el inicio del pronóstico no permite confirmar su fecha de publicación.')

outcomes = {}
for batch in batches:
    candidates = list(batch.get('candidate_outcomes', []))
    for c in batch.get('url_outcomes', []):
        candidates.append(dict(source=c['source_name'], url=c['canonical_url'],
            listing_date=c.get('listing_date'), checked_at=c.get('checked_at'),
            outcome='attempted_direct_open', result=c['outcome'], reason=c['reason'],
            final_decision='discard' if c['outcome'].startswith('accessible_discard') else 'unresolved'))
    for c in candidates:
        if c.get('result') == 'not_opened_in_final_pass':
            c.update(outcome='not_attempted', checked_at=None)
        outcomes[canonical(c['url'])] = c
for k, c in outcomes.items():
    if k in dedup:
        c['final_decision'] = dedup[k]['decision']
        c['final_story_id'] = dedup[k]['id']
    else:
        c.setdefault('final_decision', 'unresolved')
for name in ['La Nación', 'Redagrícola']:
    attempts = [c for c in outcomes.values() if c.get('source') == name]
    if attempts:
        coverage[name].update(status='selected_originals_attempted_no_inclusion', checked_at=STAMP,
            checked_at_precision='audit_batch', original_attempt_count=len(attempts),
            reason='Intentos de apertura original registrados por URL: sin inclusión tras revisión de acceso o relevancia para Colombia.')
reviews = []
for batch in batches:
    reviews.extend(batch.get('review', []))

data = dict(schema_version=2, run_at=STAMP, window_start=batches[0]['window_start'], window_end=batches[0]['window_end'],
    timezone='America/Bogota', window_note='25 de agosto–7 de septiembre de 2026, con corte al iniciar la recopilación (23:18 Colombia). El último día es parcial.',
    execution_mode='one_time_research_backfill', model='gpt-5.6-luna', review_by='parent_assistant', state_available=False,
    publication_state='local_research_only', scheduled_job_created=False, database_imported=False,
    content_policy='Etiquetas factuales breves en español, enlaces y metadatos. Sin cuerpos de artículos ni miniaturas. Derechos de uso comercial no establecidos.',
    expiry_policy='Caducidad editorial del feed, no vigencia legal ni resolución de emergencias: general 14 días; precio puntual y pronóstico/alerta operativa 48 horas; ventana de acción anterior prevalece.',
    coverage_limit='Búsquedas y páginas originales seleccionadas; no se agotaron todos los archivos ni se comprobó ausencia de noticias en fuentes sin resultados.',
    counts=dict(verified_stories=len(included), contributing_publishers=len(counts), feed_statuses=dict(Counter(s['status'] for s in included)), review_records=sum(s['decision']=='review' for s in stories), additional_review_candidates=len(reviews)),
    stories=stories, review=reviews, coverage=list(coverage.values()), candidate_outcomes=list(outcomes.values()),
    expired_or_corrected=[dict(story_id=s['id'], canonical_url=s['canonical_url'], status=s['status'], reason=s['expiry_reason']) for s in included if s['status']=='expired'],
    new_sources=[], input_batches=batch_names,
    audit_corrections=['Separación de publicación, fecha del acontecimiento y período observado.', 'Normalización y deduplicación de URLs; reparación del enlace de café.', 'Caducidad coherente con el tipo de noticia y la ventana de acción.', 'Corrección de metadatos de hora no fiables y de candidatos no intentados.', 'Semillas y plántulas en insumos; ganadería y acuicultura separadas de cultivos.'])
write('backfill.json', data)
result = validate(ROOT / 'backfill.json')
write('validation.json', result)

rows = ['# Noticias agropecuarias: recopilación del 25 de agosto al 7 de septiembre de 2026', '',
    f"Recopilación puntual con GPT-5.6 Luna y revisión del asistente principal. **{len(included)} publicaciones verificadas de {len(counts)} fuentes**. Corte: 7 de septiembre, 23:18, Colombia; último día parcial. Revisión terminada: {STAMP}.", '',
    f"Vigencia editorial al revisar: {sum(s['status']=='active' for s in included)} activas y {sum(s['status']=='expired' for s in included)} vencidas. Las vencidas permanecen en el histórico solicitado. Hay {data['counts']['review_records']} registros con revisión pendiente y {len(reviews)} candidatos adicionales sin verificación suficiente.", '',
    'La colección está guardada localmente; no se ha importado a Azure ni publicado en la aplicación. Esta ejecución no creó una tarea programada.', '',
    '## Archivos', '',
    '- [Colección final y trazabilidad](backfill.json).',
    '- [Resultado de validación](validation.json).',
    '- `luna-initial.json`, `more-discoveries.json`, `known-discoveries.json`, `remaining-known.json` y, si existe, `regional-remaining.json`: salidas intermedias del agente; sus recuentos y decisiones quedan reemplazados por la colección final.', '',
    '## Publicaciones verificadas', '',
    'Cada enlace abre la fuente original. Las descripciones son paráfrasis breves, no titulares copiados. Las fechas mostradas son de publicación, no necesariamente del acontecimiento.', '',
    '| Publicación | Descripción y fuente | Categoría | Estado del feed / caduca (Colombia) |',
    '|---|---|---|---|']
for s in included:
    expiry = iso(s['display_expires_at']).astimezone(timezone(timedelta(hours=-5))).strftime('%Y-%m-%d %H:%M')
    rows.append(f"| {s['published_at'][:10]} | {s['factual_label_es']} [{s['source_name']}]({s['canonical_url']}) | {s['primary_category']} | {'Activa' if s['status']=='active' else 'Vencida'} / {expiry} |")
rows += ['', '## Interpretación y caducidad', '',
    '- Una publicación general permanece 14 días en el feed. Cotizaciones puntuales y pronósticos o alertas operativas usan 48 horas según la regla preparada; esto no declara resuelta una emergencia.',
    '- El boletín de Cenicafé sigue siendo una referencia mensual fechada aunque haya vencido su exposición como noticia. Conviene separar boletines mensuales y alertas inmediatas antes de automatizar esta política.',
    '- La orientación de Fenalce se limita a Córdoba y a su ventana del 1 al 15 de septiembre. No se convierte en recomendación universal para cualquier finca.',
    '- BIOINNOVA: publicación web del 25 de agosto y comunicación fechada el 24. No se verificó un cierre de inscripciones; consultar la disponibilidad en la fuente.',
    '- Las reuniones con compradores industriales son conversaciones anunciadas, no ofertas firmes. La investigación de biocontrol del banano requiere validación de campo.',
    '- Las estadísticas laborales de julio y el precio cafetero del 26 de agosto conservan sus períodos originales. No se presentan como observaciones actuales.',
    '- Con fecha sin hora se usa medianoche de Colombia como convención explícita para filtrar y calcular caducidad.', '',
    '## Revisión pendiente', '']
for s in stories:
    if s['decision'] != 'include':
        rows.append(f"- [{s['source_name']}]({s['canonical_url']}): {s.get('review_reason', s.get('expiry_reason', 'Pendiente de revisión.'))}")
for r in reviews:
    rows.append(f"- [{r.get('source_name', 'Candidato')}]({r.get('url', r.get('canonical_url', ''))}): {r.get('reason', 'Pendiente de revisión.')}")
rows += ['', '## Cobertura y límites', '',
    'Se documenta el estado de las 71 fuentes del catálogo: búsqueda parcial, originales seleccionados, acceso bloqueado o exclusión por restricciones. Una búsqueda sin resultados comprobados no demuestra que el medio no publicara noticias. El archivo JSON conserva los resultados por URL y los candidatos pendientes; no se cuentan como artículos recopilados.', '',
    'FNC y Agronegocios se omitieron en el rastreo automático por las restricciones ya registradas. No se eludieron bloqueos de acceso. La colección no mide el total diario de noticias agrícolas colombianas.', '',
    'No se guardan cuerpos completos ni miniaturas. Los derechos para mostrar contenido en una aplicación comercial siguen sin verificar por fuente. Cenicafé muestra CC BY-NC-ND 4.0; esa licencia no establece permiso de reutilización comercial.', '',
    'La validación automática comprueba estructura, fechas, caducidad, URLs únicas y contabilización de fuentes. La verificación del contenido se basa en las páginas originales leídas; la validación técnica no certifica la veracidad del editor ni permisos de reutilización.', '',
    '| Fuente | Publicaciones verificadas |', '|---|---|']
for source, n in counts.most_common(): rows.append(f'| {source} | {n} |')
(ROOT / 'report.md').write_text('\n'.join(rows) + '\n')
print(json.dumps({'counts': data['counts'], 'validation_passed': result['passed'], 'errors': result['errors']}, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['passed'] else 1)
