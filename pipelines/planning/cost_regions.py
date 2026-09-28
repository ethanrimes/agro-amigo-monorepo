"""Region evidence for the independently checked UPRA aggregate cost tables."""

import re
import unicodedata


ARVEJA_SOURCE = "cost-01_BolCostArv_20240925.pdf"
# Physical PDF page, printed table number, and literal heading. These are three
# single-period tables; input-quantity and multi-year tables are not cost rows.
ARVEJA_HEADINGS = {
    9: (2, "Sabana Occidente", "en Sabana Occidente* en 2024"),
    12: (5, "Sur de Nariño", "en el Sur de Nariño*, en 2024"),
    14: (8, "Sugamuxi", "en Sugamuxi*, 2024"),
}
ARVEJA_FOOTERS = {
    9: ("Cundinamarca", "Bojacá, El Rosal, Facatativá, Funza, Madrid, Subachoque, Zipacón"),
    12: ("Nariño", "Aldana, Contadero, Córdoba, Cuaspud Carlosama, Funes, Gualmatán, Iles, Ipiales, Potosí, Puerres, Pupiales"),
    14: ("Boyacá", "Aquitania, Cuítiva, Firavitoba, Gámeza, Iza, Mongua, Monguí, Nobsa, Pesca, Sogamoso, Tibasosa, Tópaga, Tota"),
}


def _name(value):
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold().strip()


def arveja_municipalities(text, page, municipalities):
    """Match complete printed names, keeping the department out of that list."""
    if page not in ARVEJA_FOOTERS:
        raise ValueError("Unverified Arveja municipality footer")
    flat = " ".join(text.split())
    footers = re.findall(r"\*Incluye los municipios de (.*?)\(([^()]+)\)\.", flat)
    department, names = ARVEJA_FOOTERS[page]
    expected = {_name(n) for n in names.split(",")}
    if len(footers) != 1:
        raise ValueError("Missing or ambiguous Arveja municipality footer")
    actual_names, actual_department = footers[0]
    actual = [_name(n.strip(" .")) for n in actual_names.split(",")]
    if _name(actual_department) != _name(department) or set(actual) != expected or len(actual) != len(expected):
        raise ValueError("Unverified Arveja municipality list or department")
    matches = [(mid, _name(name)) for mid, name, dep in municipalities
               if _name(dep) == _name(department) and _name(name) in expected]
    if len(matches) != len(expected) or {name for _, name in matches} != expected:
        raise ValueError("Unresolved or ambiguous Arveja municipality identity")
    return [mid for mid, _ in matches]


def cost_region(text, source_name, page, crop, year):
    """Return only a region explicitly attached to this page's cost heading.

    The 2024 Arveja publication omits the word Región. Accept its verified
    headings exactly, including the publication period and table identity.
    Changed or additional cost tables require review rather than guessed scope.
    Other previously supported publications keep their existing extraction.
    """
    if source_name == ARVEJA_SOURCE:
        if crop != "Arveja" or year != 2024 or page not in ARVEJA_HEADINGS:
            raise ValueError("Unverified Arveja cost table identity or period")
        table, region, suffix = ARVEJA_HEADINGS[page]
        flat = " ".join(text.split())
        headings = re.findall(
            r"Tabla \d+\. Costos de producción .*?(?= Actividad)", flat
        )
        expected = (
            f"Tabla {table}. Costos de producción de arveja por hectárea {suffix}"
        )
        if headings != [expected]:
            raise ValueError("Unverified Arveja cost heading, region or period")
        if expected + " Actividad ($) (%)" not in flat:
            raise ValueError("Missing Arveja table-local monetary header")
        return region

    heading = re.search(
        r"(?:Ficha|Tabla)\s+\d+\.\s*Costos de producci[oó]n.*?"
        r"((?:Región|región).*?)(?:20\d{2}|Actividad|para el año)",
        text,
        re.S,
    )
    if not heading:
        return None
    region = " ".join(heading[1].replace("*", "").strip(" ,").split())
    return region if len(region) <= 130 else None
