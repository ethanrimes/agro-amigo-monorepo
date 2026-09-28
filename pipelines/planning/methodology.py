"""Render and archive the current explanatory method, preserving prior versions."""

import argparse
import hashlib
import io
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

VERSION = "2"
TITLE = "AgroAmigo - referencias históricas y trazabilidad"
PERIOD = "Versión 2 · septiembre de 2026"
SOURCE_URL = "https://agroamigo-demo-9a04.azurewebsites.net/sources"
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[2] / "output/pdf/planning-method-v2.pdf"
)

SECTIONS = [
    (
        "Historia, fechas y unidades",
        [
            "La aplicación conserva historia y originales. Las vistas recientes y las consultas de historia completa indican su alcance; no se limita toda la historia a los últimos 12 meses. Cada dato conserva su fecha, unidad, fuente y, cuando existe, hoja, fila o página. No se rellenan observaciones faltantes.",
            "Los precios mensuales DANE SIPSA se muestran en COP nominales por kilogramo y mercado; la fecha corresponde al cierre del mes. Las cotizaciones por presentación conservan su cantidad y unidad. Los porcentajes de variación son cambios, no precios. Una referencia mayorista no equivale a un pago en finca ni a una oferta de compra.",
            "La referencia nacional FNC se publica en COP por carga de 125 kg de café pergamino seco. Convertirla a COP/kg requiere dividir por 125. La referencia nacional, los factores y las tablas por lugar pueden tener fechas distintas y conservan sus fuentes propias.",
        ],
    ),
    (
        "Patrón estacional descriptivo",
        [
            "Se compara el mismo producto, mercado y unidad. Para cada año completo, se divide el precio de cada mes por el promedio de sus 12 precios mensuales y se multiplica por 100. El gráfico muestra, para cada mes, la mediana de los índices de los años válidos. Un índice de 100 equivale al promedio de ese año.",
            "Se requieren al menos 3 años completos y comparables, con 12 precios finitos y positivos. Si no los hay, se muestran los años disponibles sin generar un patrón. La tabla conserva los precios mensuales nominales y los enlaces a sus originales; no ajusta por inflación.",
            "El precio reciente se informa por separado: no multiplica los índices del gráfico. Este patrón describe historia; no calcula precios futuros, ingresos ni rentabilidad y no recomienda un mes para vender. No incorpora un pronóstico de clima, oferta o inflación.",
        ],
    ),
    (
        "Mi finca: referencias publicadas",
        [
            "Mi finca permite consultar ubicación, clima, cultivos, suelos, calendarios e información de costos de las fuentes disponibles. Las referencias de costos se muestran con su cultivo, región, unidad, año y documento. Se conservan los datos guardados de la finca; la vista actual no ofrece calculadoras manuales de presupuesto o rentabilidad.",
            "El rendimiento agregado EVA se obtiene de la producción municipal en toneladas multiplicada por 1.000 y dividida por el área cosechada en hectáreas, para la misma clasificación de cultivo. No es una predicción del rendimiento de una finca.",
            "Los calendarios departamentales muestran porcentajes históricos de siembra y cosecha del año publicado. La aptitud regional UPRA SIPRA y los resúmenes de muestras de suelo AGROSAVIA son referencias a su escala; no determinan por sí solos la aptitud, fertilización o fecha de siembra de un lote.",
        ],
    ),
    (
        "Otras herramientas y clima",
        [
            "Las ofertas guardadas conservan cantidades, precios, descuentos, gastos, vigencia y plazo. Sus resultados dependen de los valores ingresados y deben compararse con la misma variedad, calidad y presentación. No son cotizaciones verificadas por AgroAmigo.",
            "El clima identifica el proveedor, la ubicación y la fecha de consulta. El pronóstico de modelo y los avisos orientativos no sustituyen la observación del lote ni constituyen alertas oficiales. Cuando se muestra una respuesta guardada, su antigüedad debe permanecer visible.",
        ],
    ),
    (
        "Originales, revisiones y límites",
        [
            "Los originales y las versiones derivadas se conservan con identificadores SHA-256. Una nueva versión del archivo tiene otro identificador; no reemplaza sus bytes históricos. El visor distingue el original de la entidad, los extractos y documentos explicativos de AgroAmigo como este.",
            "Las tablas Excel y los PDF conservan acceso al archivo descargable. Los registros en revisión permanecen retenidos, con su motivo, y se excluyen de las cifras publicadas cuando su interpretación no es segura. La existencia de un original archivado no certifica la publicación de todas sus tablas.",
            "Este documento explica la presentación actual de las referencias. Las cifras, fechas y condiciones particulares deben comprobarse en el original enlazado junto a cada dato. Las versiones anteriores de este método permanecen archivadas y describen funciones de su momento.",
        ],
    ),
]


def render(path=DEFAULT_OUTPUT):
    """Generate deterministic bytes locally, without database or network access."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles["BodyText"].fontName = "Helvetica"
    styles["BodyText"].fontSize = 10
    styles["BodyText"].leading = 14
    styles["Heading2"].textColor = colors.HexColor("#164b35")
    story = [
        Paragraph("AgroAmigo | Referencias históricas y trazabilidad", styles["Title"]),
        Spacer(1, 10),
        Paragraph(
            PERIOD
            + ". Documento explicativo de AgroAmigo; no es una recomendación oficial de las entidades citadas.",
            styles["BodyText"],
        ),
        Spacer(1, 14),
    ]
    for title, paragraphs in SECTIONS:
        if title == "Mi finca: referencias publicadas":
            story.append(PageBreak())
        story.extend([Paragraph(title, styles["Heading2"]), Spacer(1, 5)])
        for paragraph in paragraphs:
            story.extend([Paragraph(paragraph, styles["BodyText"]), Spacer(1, 9)])

    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#526259"))
        canvas.drawString(
            42, 25, "AgroAmigo · Referencias y trazabilidad · Versión " + VERSION
        )
        canvas.drawRightString(570, 25, str(document.page))

    SimpleDocTemplate(
        str(path),
        pagesize=(612, 792),
        rightMargin=42,
        leftMargin=42,
        topMargin=38,
        bottomMargin=44,
        title=TITLE,
        author="AgroAmigo",
        invariant=1,
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def publish(cur, path=None):
    """Insert a new immutable PDF and retain the previous alias before switching.

    Caller owns the transaction and normal ingestion writer lock. Blob upload can
    precede this operation; source_document also retains the complete PDF bytes.
    """
    from psycopg.types.json import Jsonb

    path = Path(path) if path else render()
    data = path.read_bytes()
    did = hashlib.sha256(data).hexdigest()
    old = cur.execute(
        "SELECT document_id FROM document_alias WHERE alias='planning-method' FOR UPDATE"
    ).fetchone()
    prior = old[0] if old else None
    metadata = {
        "method_version": VERSION,
        "generated_by": "pipelines/planning/methodology.py",
        "note": "Current descriptive reference method; previous method documents remain immutable.",
    }
    if prior and prior != did:
        metadata["parents"] = [prior]
    cur.execute(
        """INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
        (
            did,
            TITLE,
            "AgroAmigo",
            SOURCE_URL,
            "application/pdf",
            "methodology",
            PERIOD,
            len(PdfReader(io.BytesIO(data)).pages),
            data,
            Jsonb(metadata),
        ),
    )
    if prior and prior != did:
        record = {
            "alias": "planning-method",
            "document_id": prior,
            "replacement_document_id": did,
            "reason": "Current descriptive seasonal index and read-only Mi finca reference method",
            "method_version": VERSION,
        }
        cur.execute(
            """INSERT INTO retained_record(table_name,fingerprint,record)
          VALUES('document_alias_revision',md5(%s::jsonb::text),%s) ON CONFLICT DO NOTHING""",
            (Jsonb(record), Jsonb(record)),
        )
    cur.execute(
        "INSERT INTO document_alias(alias,document_id) VALUES('planning-method',%s) ON CONFLICT(alias) DO UPDATE SET document_id=excluded.document_id",
        (did,),
    )
    return did


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = render(args.output)
    print(result, hashlib.sha256(result.read_bytes()).hexdigest())
