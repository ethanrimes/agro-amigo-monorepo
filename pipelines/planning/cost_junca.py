"""Native, table-local extraction of the three retained UPRA junca cost tables.

The first table continues across physical pages 9–10. All region/year/municipal
identities below are printed in that table or its own continuation, not inferred
from neighboring columns. Fertilizer quantities never become cost observations.
"""

import re
import unicodedata
from dataclasses import dataclass

SOURCE = "cost-20231221_Bolet%C3%ADn_Cebolla%20junca_final.pdf"
VERSION = "upra-cost-junca-v1"
TABLES = (
    (2, 9, 10, "Región centro (Nariño)",
     "Tabla 2. Costos de producción de la cebolla junca por hectárea, región centro*, Nariño, 2023",
     "*Incluye zona rural del municipio de Pasto (Nariño).", "Nariño", ("Pasto",)),
    (5, 12, 12, "Región oriente (Risaralda)",
     "Tabla 5. Costos de producción cebolla junca por hectárea, región oriente*, Risaralda, 2023",
     "*Incluye los municipios de Pereira y Santa Rosa de Cabal (Risaralda).", "Risaralda", ("Pereira", "Santa Rosa de Cabal")),
    (8, 15, 15, "Región oriente (Cauca)",
     "Tabla 8. Costos de producción de la cebolla junca por hectárea, región oriente*, Cauca, 2023",
     "*Incluye los municipios de Inzá, Jámbalo, Páez, Silvia y Toribio (Cauca).", "Cauca", ("Inzá", "Jámbalo", "Páez", "Silvia", "Toribio")),
)


@dataclass(frozen=True)
class JuncaTables:
    rows: tuple
    reviews: tuple


def _name(value):
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold().strip()


def _amount(text, label):
    values = re.findall(r"^\s*" + label + r"\s+([0-9][0-9.,]*)\s", text, re.M)
    if len(values) != 1 or not re.fullmatch(r"(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?", values[0]):
        raise ValueError(f"Missing or ambiguous junca cost field: {label}")
    return float(values[0].replace(".", "").replace(",", "."))


def parse_junca_tables(pages, municipalities):
    """Materialize all three verified single-period tables before publication."""
    result, reviews = [], []
    for table, first, last, region, heading, footer, department, names in TABLES:
        if len(pages) < last:
            raise ValueError("Incomplete junca publication")
        first_flat = " ".join(pages[first-1].split())
        if first_flat.count(heading) != 1:
            raise ValueError(f"Unverified junca table {table} region/year heading")
        if last != first and not " ".join(pages[last-1].split()).startswith("Actividad $ % "):
            raise ValueError("Unverified junca table continuation")
        text = "\n".join(pages[first-1:last])
        # Pypdf may wrap the heading. Locate the same explicit title in native
        # text, then stop before the following fertilizer/quantity table.
        match = re.search(r"\s+".join(re.escape(word) for word in heading.split()), text)
        if not match:
            raise ValueError("Missing native junca cost heading")
        text = re.split(r"\n\s*Tabla\s+\d+\.", text[match.end():], maxsplit=1)[0]
        if " ".join(text.split()).count(footer) != 1:
            raise ValueError("Unverified junca municipality footer")
        if not re.search(r"Rendimientos\s+t/ha", text):
            raise ValueError("Missing junca yield unit")
        total = _amount(text, "Costos totales")
        direct = _amount(text, "Costos directos")
        labor = _amount(text, "Mano de obra/maquinaria")
        inputs = _amount(text, "Insumos")
        harvest = _amount(text, "Cosecha")
        kg = round(_amount(text, "Producción total") * 1000, 6)
        indirect = _amount(text, r"Costos indirectos\*\*") if "Costos indirectos**" in text else 0
        residual = round(total - labor - inputs - indirect, 2)
        if min(total, labor, inputs, harvest, kg) <= 0 or labor < harvest or residual < 0:
            raise ValueError("Invalid junca costs or yield")
        expected = {_name(n) for n in names}
        matched = [(mid, _name(name)) for mid, name, dep in municipalities
                   if _name(dep) == _name(department) and _name(name) in expected]
        if len(matched) != len(expected) or {name for _, name in matched} != expected:
            raise ValueError("Unresolved or ambiguous junca municipality identity")
        if direct != labor+inputs or total != direct+indirect:
            reviews.append({
                "source_locator": f"PDF page {first}; table {table}",
                "parser_version": VERSION,
                "reason": "Printed cost subtotal disagrees with named components; no canonical cost template published",
                "record": {"crop": "Cebolla junca", "region": region, "reference_year": 2023,
                           "currency": "COP", "unit": "ha", "source_pages": list(range(first, last+1)),
                           "total": total, "direct": direct, "labor": labor, "inputs": inputs,
                           "harvest": harvest, "indirect": indirect, "yield_kg_ha": kg,
                           "direct_minus_components": round(direct-labor-inputs, 2),
                           "total_minus_direct_and_indirect": round(total-direct-indirect, 2)},
            })
            continue
        lines = [
            {"label": "Labores antes de cosecha", "amount": round(labor-harvest, 2), "timing": "before"},
            {"label": "Semilla e insumos", "amount": inputs, "timing": "before"},
            {"label": "Mano de obra de cosecha", "amount": harvest, "timing": "harvest"},
        ]
        if indirect:
            lines.append({"label": "Costos indirectos publicados", "amount": indirect, "timing": "before"})
        notes = ("Pesos nominales de 2023, sin actualización automática. Cebolla junca (cebolla de rama); "
                 "el estudio no se presenta como un calendario de pagos. "
                 f"Tabla {table}, " + (f"páginas {first}–{last}." if first != last else f"página {first}."))
        result.append({"id": f"cebolla-de-rama-2023-{first}", "crop": "Cebolla de rama",
                       "title": "Cebolla junca · " + region, "region": region,
                       "municipalities": [mid for mid, _ in matched], "reference_year": 2023,
                       "production_system": "Sistema regional de cebolla junca reportado por UPRA",
                       "yield_kg_ha": kg, "costs": lines, "source_page": first, "notes": notes})
    return JuncaTables(tuple(result), tuple(reviews))
