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

POSITIVE_FOOTERS = {
    ("cost-20231018_Ficha_papa_2023.pdf", 7): (
        "Antioquia", "los municipios de Abejorral, El Carmen de Viboral, Concepción, El Santuario, Granada, Guarne, La Ceja, Marinilla, Rionegro, San Vicente, Sonsón.",
        "Abejorral, El Carmen de Viboral, Concepción, El Santuario, Granada, Guarne, La Ceja, Marinilla, Rionegro, San Vicente, Sonsón",
        "Ficha 6. Costos de producción de papa por hectárea Región Oriente* (Antioquia), 2023"),
    ("cost-20231009_BolCostos_Frijol.pdf", 17): (
        "Antioquia", "los municipios de Abejorral, Alejandría, Argelia, El Carmen de Viboral, Cocorná, Concepción, El Peñol, El Retiro, El Santuario, Granada, Guarne, Guatapé, La Ceja, La Unión, Marinilla, Nariño, Rionegro, San Carlos, San Francisco, San Luis, San Vicente, Sonsón (Antioquia).",
        "Abejorral, Alejandría, Argelia, El Carmen de Viboral, Cocorná, Concepción, El Peñol, El Retiro, El Santuario, Granada, Guarne, Guatapé, La Ceja, La Unión, Marinilla, Nariño, Rionegro, San Carlos, San Francisco, San Luis, San Vicente, Sonsón", None),
    ("cost-20231019_BolCostos_Tomate.pdf", 19): (
        "Antioquia", "los municipios de Alejandría, Argelia, El Carmen de Viboral, Cocorná, Concepción, El Peñol, El Retiro, El Santuario, Granada, Guarne, Guatapé, La Ceja, Marinilla, Rionegro, San Rafael, San Vicente, Sonsón (Antioquia).",
        "Alejandría, Argelia, El Carmen de Viboral, Cocorná, Concepción, El Peñol, El Retiro, El Santuario, Granada, Guarne, Guatapé, La Ceja, Marinilla, Rionegro, San Rafael, San Vicente, Sonsón", None),
    ("cost-20231019_BolCostos_Tomate.pdf", 10): (
        "Huila", "los municipios de Aipe, Algeciras, Baraya, Campoalegre, Colombia, Hobo, Íquira, Neiva, Rivera, Santa María, Tello, Teruel, Villa vieja (Huila).",
        "Aipe, Algeciras, Baraya, Campoalegre, Colombia, Hobo, Íquira, Neiva, Rivera, Santa María, Tello, Teruel, Villa vieja", None),
    ("cost-01_FicCostPlat_20250310.pdf", 25): (
        "Meta", "El Castillo, El Dorado, Fuentedeoro, Granada, Lejanías, Mapiripán, Mesetas, Puerto Concordia, Puerto Lleras, Puerto Rico, San Juan de Arama, Uribe y Vistahermosa (Meta).",
        "El Castillo, El Dorado, Fuentedeoro, Granada, Lejanías, Mapiripán, Mesetas, Puerto Concordia, Puerto Lleras, Puerto Rico, San Juan de Arama, Uribe, Vistahermosa", None),
}

# DANE's 2016 municipality dictionary identifies 05674 as SAN VICENTE:
# https://microdatos.dane.gov.co/index.php/catalog/503/datafile/F7/V121
# Its CNPV2018 sheet identifies that same code as San Vicente Ferrer:
# https://sitios.dane.gov.co/cnpv/app/views/informacion/fichas/05674.pdf
# Peñol/Retiro are the official complete names, with the printed article kept in
# the source footer above. These are exact department-specific mappings.
PRINTED_ALIASES = {
    ("antioquia", "san vicente"): ("05674", "san vicente ferrer"),
    ("antioquia", "el peñol"): ("05541", "peñol"),
    ("antioquia", "el retiro"): ("05607", "retiro"),
}


def _name(text):
    return " ".join(unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold().split())


def corrected_cost_municipalities(text, source, page, municipalities):
    if (source, page) in POSITIVE_FOOTERS:
        return _positive_scope(text, source, page, municipalities)
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


def _positive_scope(text, source, page, municipalities):
    department, expected_footer, literal_names, expected_heading = POSITIVE_FOOTERS[(source, page)]
    footers = re.findall(r"\*\s*Incluye(.*?)(?:\*\*|Fuente:|$)", text, re.S | re.I)
    if len(footers) != 1 or _name(footers[0]) != _name(expected_footer):
        raise ValueError("Changed verified positive cost municipality footer")
    if expected_heading and _name(expected_heading) not in _name(text):
        raise ValueError("Missing explicit department in cost heading")
    aliases = {(_name(dep), _name(name)): (mid, _name(canonical))
               for (dep, name), (mid, canonical) in PRINTED_ALIASES.items()}
    found = []
    for literal in literal_names.split(","):
        key = (_name(department), _name(literal))
        alias = aliases.get(key)
        # Whitespace folding is restricted to these exact verified footer names:
        # Villa vieja/Villavieja and Fuentedeoro/Fuente de Oro are equivalent.
        candidates = [(mid, name) for mid, name, dep in municipalities
                      if _name(dep) == key[0] and
                      ((_name(name) == alias[1] and mid == alias[0]) if alias else
                       _name(name).replace(" ", "") == key[1].replace(" ", ""))]
        if len(candidates) != 1:
            raise ValueError("Unresolved or ambiguous positive cost municipality identity")
        found.append(candidates[0][0])
    if len(set(found)) != len(found):
        raise ValueError("Duplicate positive cost municipality identity")
    return sorted(found)
