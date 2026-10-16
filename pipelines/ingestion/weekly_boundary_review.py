"""Exact-source Cuadro/article boundary for three retained 2013 bulletins."""
from itertools import groupby

BASE = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
REVIEWED = {
    (BASE + "Semana_20ago_23ago_2013.pdf",
     "5a8af3b10894d3241907e149a39451d09488bf827d79b52d3789e5a8cfa60f4d", 43),
    (BASE + "Semana_16nov_22nov_2013.pdf",
     "6fffa387e6644720dd066739de89d38ce604a3af4ae5c7271a3b20127aa199d7", 43),
    (BASE + "Semana_29nov_6dic_2013.pdf",
     "a4456cbe9dfb2d3a6c5cb5c91c453f5f43b15edece78da2e83c7aa5429b12809", 43),
    (BASE + "Semana_6dic_13dic_2013.pdf",
     "ab3f0d13a9440ae992a3bde558d3c4d2ca56024262d873a6b1ecf7f30472fdc1", 43),
    (BASE + "Semana_16jun_20jun_2014.pdf",
     "7c05255c9634e7f9fec2d482368c69bae544c027d49b20d7c4c99f2ac64f90a9", 43),
    (BASE + "Semana23_sep_27sep_2013.pdf",
     "ca2205284936795f03167c310ca401bb2beda72732c9db4d15a878134b378603", 43),
}


def _line(words, desired):
    hits = []
    for _, line_iter in groupby(sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])),
                                lambda w: round(w["top"], 1)):
        line = list(line_iter)
        for start in range(len(line) - len(desired) + 1):
            run = line[start:start + len(desired)]
            if [w["text"] for w in run] == desired:
                hits.append((run[0]["top"], max(w["bottom"] for w in run)))
    return hits


def reviewed_article_bottom(url, sha256, page_no, words, top, bottom):
    """End a verified Cuadro before the *separate* panela article on page 43.

    No generic conflicting-date suppression: any other hash, page or layout
    retains the ordinary parser's source-date mismatch/review behavior.
    """
    if (url, sha256, page_no) not in REVIEWED:
        return bottom
    trends = [w for w in words if w["text"] == "Tendencias:" and top < w["top"] < bottom]
    titles = [span for span in _line(words, ["Precios", "de", "la", "panela"])
              if top < span[0] < bottom]
    if len(trends) != 1 or len(titles) != 1:
        raise ValueError("Reviewed weekly Cuadro/article boundary changed")
    article_top = titles[0][0]
    if not trends[0]["bottom"] + 15 < article_top:
        raise ValueError("Reviewed weekly Cuadro/article order changed")
    # Prevent moving past a second price table if one ever appears in a
    # different rendition. Exact SHA already makes this a defense in depth.
    if any(w["text"] == "Cuadro" and top + 1 < w["top"] < article_top for w in words):
        raise ValueError("Another Cuadro precedes reviewed article")
    return min(bottom, article_top - 0.1)
