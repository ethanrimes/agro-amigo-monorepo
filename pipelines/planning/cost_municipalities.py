"""Exact printed footers for five confirmed department-token false matches."""

import re
import unicodedata

# Source filename and physical page are part of the evidence identity. Display
# aliases in parentheses are retained in the expected footer, but do not make
# the department or an alternative name into an additional municipality.
FOOTERS = {
    ("cost-20231009_BolCostos_Cebolla.pdf", 10): (
        "Boyacá", "Cucaita, Chíquiza, Chivatá, Motavita, Samacá, Siachoque, Sora, Soracá, Toca, Tunja, Tuta, Ventaquemada"),
    ("cost-20231018_Ficha_papa_2023.pdf", 4): (
        "Boyacá", "Buenavista, Caldas, Chiquinquirá, Maripi, Pauna, Saboya, San Miguel de Sema"),
    ("cost-20231018_Ficha_papa_2023.pdf", 5): (
        "Boyacá", "Cómbita, Cucaita, Chíquiza, Chivatá, Motavita, Oicatá, Samacá, Siachoque, Sora, Soracá, Sotaquirá, Toca, Tunja, Tuta, Ventaquemada"),
    ("cost-20231018_Ficha_papa_2023.pdf", 6): (
        "Nariño", "Ancuya, Guaitarilla, Imués, La Llanada, Los Andes (Sotomayor), Mallama (Piedrancha), Ospina, Providencia, Samaniego, Santacruz (Guachavés), Sapuyes, Túquerres"),
    ("cost-20231222_Boletin_YUCA_Dic-2023_DG.pdf", 10): (
        "Sucre", "Sincelejo, Buenavista, Corozal, El Roble, Galeras, Palmito, Sampués, San Juan de Betulia, San Pedro, San Luis de Sincé"),
}


def _name(text):
    return " ".join(unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold().split())


def corrected_cost_municipalities(text, source, page, municipalities):
    if (source, page) not in FOOTERS:
        return None
    department, literal_names = FOOTERS[(source, page)]
    footers = re.findall(r"\*\s*Incluye(.*?)(?:\*\*|Fuente:|$)", text, re.S | re.I)
    expected = f"los municipios de {literal_names} ({department})."
    if len(footers) != 1 or _name(footers[0]) != _name(expected):
        raise ValueError("Changed verified cost municipality footer requires review")
    names = {_name(re.sub(r"\s*\([^)]*\)", "", name)) for name in literal_names.split(",")}
    matches = [(mid, _name(name)) for mid, name, dep in municipalities
               if _name(dep) == _name(department) and _name(name) in names]
    if len(matches) != len(names) or {name for _, name in matches} != names:
        raise ValueError("Unresolved exact cost municipality identity")
    return [mid for mid, _ in matches]
