"""Bounded scheduling with independent lanes for indexes and actual price files."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import time

import psycopg
from psycopg.types.json import Jsonb
from . import city_corabastos_ocr_proof as corabastos_proof
from .city_valledupar_partial import REVIEW_STEP as VALLEDUPAR_EXACT_REVIEW_STEP


@dataclass(frozen=True)
class BoundedSelectionResult:
    """Complete rows from one bounded queue read, or a defer diagnostic."""

    rows: tuple
    diagnostic: dict | None = None


def bounded_selection(db, lane, callback, *, deadline=None, max_ms=15000):
    """Run one read-only candidate selector under an independent timeout.

    The callback is invoked only when there is time left. Its rows are fully
    materialized inside a transaction so a canceled statement cannot leak a
    partial selection. QueryCanceled rolls that transaction back and becomes
    an explicit lane diagnostic; other connection and query errors propagate.
    SET LOCAL restores the connection's prior statement timeout on success.
    ``deadline`` is a monotonic-clock deadline, matching worker RUN_DEADLINE.
    """
    max_ms = int(max_ms)
    if max_ms <= 0:
        raise ValueError("max_ms must be positive")
    remaining_ms = max_ms
    if deadline is not None:
        remaining_seconds = deadline - time.monotonic()
        remaining_ms = min(max_ms, int(remaining_seconds * 1000))
        if remaining_ms <= 0:
            return BoundedSelectionResult((), {
                "lane": str(lane),
                "status": "deferred",
                "reason": "deadline_exhausted",
            })

    try:
        with db.transaction():
            db.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (f"{remaining_ms}ms",),
            )
            rows = tuple(callback())
    except psycopg.errors.QueryCanceled as exc:
        return BoundedSelectionResult((), {
            "lane": str(lane),
            "status": "deferred",
            "reason": "statement_timeout",
            "error": type(exc).__name__,
            "sqlstate": exc.sqlstate,
        })
    return BoundedSelectionResult(rows)

ARMENIA_EXACT_URL = 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-11-01-2022.zip'
ARMENIA_EXACT_SHA = '343f20fb88142be933f1fbc537257f427d40aecd6f59fdb69589b5c05da1c6ed'
ARMENIA_EXACT_VERSION = 'city-v8:jan2022-native-geometry-v1'
ARMENIA_EXACT_STEP = 'city-member:86d7d8d13a80ce8648bd8696f6a5667be666ea3de27dc3dc88c215f94bdc511c'
VALLEDUPAR_EXACT_URL = 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-07-01-2022.zip'
ARMENIA_OCR_URL = 'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-25ene2024.zip'
ARMENIA_OCR_SHA = '503a044d44069e1bbb39d18f5082c86cc1489ad697c823c1345920cda56b8a2b'
ARMENIA_OCR_VERSION = 'city-v8:armenia-jan2024-ocr-whole-v1'
ARMENIA_OCR_STEP = 'city-member:5528499113340025810e47cd1d0d3768c2dbfe8b09bc045c9372fe7f8d89f242'
VALLEDUPAR_EXACT_SHA = '3e3e990d35d925f102ecab674c674fd65135222117f0bbd268b2201f91a1be9a'
VALLEDUPAR_EXACT_VERSION = 'city-v8:valledupar-jan2022-partial-v1'
VALLEDUPAR_EXACT_STEP = 'city-member:b0202df54554c23641abc6e70c65a09dcb3c8ce5f7d50702911fb2b425f3952e'


# Exact retained originals with independently verified parser corrections.
# A changed source document loses priority; normal source validation still
# handles its distinct immutable revision.
PRIORITY_SOURCE_REPAIRS = (
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_04_2020.pdf",
     "daily-pdf", "9d73376d4a1297c7654bb7ccb0e865c099822843f4900be2fdeec1e3cfd3bf4a"),
    ("https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-21ago2026.pdf",
     "daily-pdf", "2b9cd5e40d5b888bd965eedf0ce3f4e347698d80713795f841aea07c7e89769f"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_01abr_al_05abr_2023.pdf",
     "dane-weekly-pdf", "ec95dc1b92689e54b52000a621dc87bad18d54392522bce748a56ce6003688e0"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_09jul_al_15jul_2022.pdf",
     "dane-weekly-pdf", "2ab314d876e586aafd8017a50d26762a1a96cbb489a57cc45a51007d63158304"),
    ("https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSASemanal-23mar-27mar-2024.pdf",
     "dane-weekly-pdf", "218d83958d650f3b3035e008a35828aff6a6b2a0098d8ba84adc07596a26ca7e"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_21ene_27ene_2017.pdf",
     "dane-weekly-pdf", "95072bb4d5c98fbb2b2635c8aa3dd50c22b4e3ab9c40abcb441662868b5f062e"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_02jul_al_08jul_2022.pdf",
     "dane-weekly-pdf", "9f428bddcef7ede04ba7d91b7e39d2a89413a70f4b132d1f516f4577330c271c"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_21feb_27feb_2015.xls",
     "dane-weekly-xlsx", "30d900d3c1d2ee3ca4f32bd09649b682b16f9bd23a177c7200de518b8dc2bcbd"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_18_2019.pdf",
     "daily-pdf", "4e0ddac5f22c1c852be933d1056a66c45b67a63886aab9a2cbd7fba688a1b3ac"),
    ("https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSALeche-nov2024.pdf",
     "milk-pdf", "7bdeb21148f0ae14ef55259f30cd7f4806689bd67a149e4ccff59de226057343"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/BolSipsaLeche_jun_2022.pdf",
     "milk-pdf", "a8e27086128ff3f2a3c67147dfa6782a947a6e3ad6c94b52af4c2d3537d1ab63"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/BolSipsaLeche_jul_2022.pdf",
     "milk-pdf", "4cf84658353b236e022d39c737e16975d94e22e5cde92dd96f308d3e042f6e0e"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_abr_2016.pdf",
     "inputs-pdf", "6cba3d6b39f171d2ae0f6e13b8afb7ab468e6dc4d2d807febc1f2a1c2731b2fc"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_feb_2016.pdf",
     "inputs-pdf", "cb2289b8dad52378bc04a9787c7560a93a1feccfd47c64a41e010a33a499f5ab"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_1_2015.xls",
     "daily", "bbb69b2938848e95c9728a34c9204dd9fb19e720d54b05dd2f9b8289079a0f0f"),
    ("https://porkcolombia.co/wp-content/uploads/2024/09/Semana36de2024.pdf",
     "colombia-pork-pdf", "3b9009dd742d30db945636b203a20729df4d7aec19b5ffad64173f6cdba62084"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_septiembre_5_2016.xls",
     "daily", "dde84100bdbe8f0eb0521361d4724ce8481cd3ecd5032dfd64de0b82b1ad47fe"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/anexo_abastecimiento_ene23.xlsx",
     "supply-reference", "c8b702262cbb28612b3f4741cca307029eef5a295b11dfc3a42bb090b348b5a6"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana4_junio_2012.pdf",
     "dane-weekly-pdf", "dd059a09eecb1fa01cadb24a4f21a7768d97d9e31684dee6a57222c536faf6a8"),
    # Keep these after the historical daily/weekly positional pins above.
    # Exact retained January 2022 city ZIPs contain four native unit-glyph
    # spill children previously held for review. Changed bytes lose priority.
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-03-01-2022.zip",
     "city-zip", "9b7bbbcefbbddd8c023a100ea3db3032214050f44a9cef2bc9a20aabfb953878"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-04-01-2022.zip",
     "city-zip", "6af11307e0ffdb6c98b36071ef134ad32110e07a4c82d6e72f2313537d23029f"),
    # Thirteen native PDFs print February10/2022 inside this 2021-named ZIP.
    # The exact source-date review binds every original and complete typed grid.
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-10-02-2021.zip",
     "city-zip", "2ca39b0eacb32edb497e0be527f93e581de9edecdd5364cda7b7ba7b381a1857"),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_16nov_22nov_2013.pdf',
     'dane-weekly-pdf', '6fffa387e6644720dd066739de89d38ce604a3af4ae5c7271a3b20127aa199d7'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_29nov_6dic_2013.pdf',
     'dane-weekly-pdf', 'a4456cbe9dfb2d3a6c5cb5c91c453f5f43b15edece78da2e83c7aa5429b12809'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_6dic_13dic_2013.pdf',
     'dane-weekly-pdf', 'ab3f0d13a9440ae992a3bde558d3c4d2ca56024262d873a6b1ecf7f30472fdc1'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_16jun_20jun_2014.pdf',
     'dane-weekly-pdf', '7c05255c9634e7f9fec2d482368c69bae544c027d49b20d7c4c99f2ac64f90a9'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_20_2017.xls',
     'daily', '58541524d801feadbce7be1059f9e6d924c58b668785ab3023a2725d5114ac4d'),
    (ARMENIA_EXACT_URL, 'city-zip', ARMENIA_EXACT_SHA),
    # One source omits Coco's numeric quantity. Only its other 35 complete
    # rows can be appended; Coco and the parent retain explicit review.
    (VALLEDUPAR_EXACT_URL, 'city-zip', VALLEDUPAR_EXACT_SHA),
    # Only a whole-source reviewed 59-row OCR child is eligible. Its other
    # 29 source members and the parent remain in their original review state.
    (ARMENIA_OCR_URL, 'city-zip', ARMENIA_OCR_SHA),
    # Source-bound three-page Corabastos OCR recovery; unrelated 27 ZIP
    # members continue through the normal publisher.
    ('https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-19oct2023.zip',
     'city-zip', 'c9ecd972491184f1bb1df8b8df556f1aa9ee6d70a0a28336dcdf8d07dad82cd7'),
    # The literal PDF typo is corrected only after its complete native grid
    # matches the independently reviewed workbook and all 47 market prices.
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos31_abr_2015.pdf',
     'inputs-pdf', '58b12b179a9293e584e22473f60a97fab1b632cee35f27318953dc7de10e866c'),
    ('https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-31may2024.zip',
     'city-zip', '535debd86950b07758ea32115a5b6906b52885726a314b54af471572f5f7c5f5'),
    ('https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-20oct2023.zip',
     'city-zip', '51c4a6fdf9440ffdf95daab2c8f81afe092f956f366dea493181604ef784855b'),
    ('https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-30mar2024.zip',
     'city-zip', '584bc4da5ed1c9f5fa44cf93f7a2e1a8c2e2606616aa1bb7024e99db55e07dda'),
    ('https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-17may2024.zip',
     'city-zip', '563c1c05f36a3db36404d85ddefe974c595d0c4833ec8b485c14bde7cf7bf785'),
    # Whole retained 48/19 child grids have only exact reviewed category
    # spellings; every other sibling continues through the ordinary city-v8
    # publisher. Changed parent bytes lose this priority.
    ('https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-7ene2025.zip',
     'city-zip', '11123eb2b38ce43b133b076c65542015f27507fbafaa3a8dea10993d7b604c8f'),
    ('https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-17jul2024.zip',
     'city-zip', '3910c7199e7c5545863d4f35f8a5d09632f1e4d2ed8aabe8391044724f5a328f'),
    # Only this retained Jan-3 source/child has a reviewed whole image grid.
    # Corabastos from the same ZIP remains on its independent review path.
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol-reg-03-01-2023.zip',
     'city-zip', '220e0d23060a337f4307b5f93e729fa4f777e89e4373228cb6552a68b8da2c04'),
    # Exact printed continuation typo on one 2019 weekly original only.
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_02nov_2019__08nov_2019.pdf',
     'dane-weekly-pdf', '4f038cbc3d2e2c55d1b3cbf09f22782ef451225c73dded1f7e987e3a0eca2134'),
    # Three printed Armenia (Quindio) rows are absent from the old v14 parse.
    # Replay only the exact 76-page retained original and preserve raw history.
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_sep_2014.pdf',
     'inputs-pdf', '14784c8d8f7e4c25b9715d2c2828ae2568aebfda6ce14f615f56288c97f61c3f'),
    # The 7-13 January 2017 original prints a separate unpriced Medellín
    # lead beside a prior priced market. Preserve all old quotes and replay
    # only this exact source under its source-local quote revision.
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_7ene_2017_13ene_2017.pdf',
     'dane-weekly-pdf', '2075ff73d374815709ea72927d5981c81823c066a01a6dc9557cefa409902440'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_29oct_04nov_2016.pdf',
     'dane-weekly-pdf', '1a6d6a31c9beda79688b41bf72443c1ec28dcd42ab724c49673736703b82c177'),
    # Exact retained v14 context-PDF originals; only the matching SHA
    # outranks the ordinary six-hour historical repair queue.
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_feb_2014.pdf',
     'inputs-pdf', '3e1265bdbff25420d9be9b44c4db0aa7564585270cdc93878810c68ebae46dc3'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mar_2014.pdf',
     'inputs-pdf', '2befda0f1d3d4740b7a82e3a9d5ca3e6c9d2e213193ccf011ddadf9d8d729403'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_may_2014.pdf',
     'inputs-pdf', 'db08213afe320e1a1101d2c8311565c924f4a2c82aef56d98a3971e26a1c9d62'),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_08ago_14ago_2015.pdf", "dane-weekly-pdf", "3660829203a4608502a1f0656cc7fdd7fe0ac6ad7ecf3fed8cd1ffa7d4e7e777"),
    # Exact May 2013 original: queue its source-local heading revision only
    # while the retained original has this independently verified digest.
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_18may_24may_2013.pdf",
     "dane-weekly-pdf", "d7bbfdb46fcba969ebcdbad7f17960b8fdc7ba1df8e376cd89883f692330cd04"),
    # Exact long input-PDF witnesses; these run in the existing reserved repair
    # lane so native extraction can use work_deadline rather than the 90s lane.
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_sep_2018.pdf",
     "inputs-pdf", "f37ddee1c655810d1e6a6ea7746bd1a429337fd22deda2b3db8c52762780a2fb"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_%20Insumos_ene_2019.pdf",
     "inputs-pdf", "849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_ Insumos_ene_2019.pdf",
     "inputs-pdf", "849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_feb_2019.pdf",
     "inputs-pdf", "8c5e95de023a6fafd71484dc476c40083aa886d05ca00f90ada498cac05043f7"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_nov_2018.pdf",
     "inputs-pdf", "79b2dadcad9c2387648b64620d92a896b5ef5d8f9a2d366e522021ff62d7cbb3"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_dic_2018.pdf",
     "inputs-pdf", "7b33370ff3eb28f8567fb36528dc8c2c619aad1629c1aaf761f7448269ceb293"),
    # A ZIP-named official download contains this exact verified RAR5 body.
    # Its native fallback has an independent source-local decoder/publication
    # revision; all ordinary ZIP originals retain their existing versions.
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol-reg-19-08-2022.zip",
     "city-zip", "f8a481a767495427ecc056cbb150745c44d920b7143fde7e2e7b495b5812542a"),
    # Exact legacy XLS originals whose only safe output is the retained
    # source-local unpriced period/unit review.
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb8_2014.xls",
     "dane-weekly-xlsx", "011380f52918f5af902d1742f14182e3258f7bda665bc56df51aeb85f677d33a"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb15_2014.xls",
     "dane-weekly-xlsx", "4a0cdfc8e3a6253de3f96b2bf5f8687fff32e704fd01e7fb0867086ae99ac899"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb22_2014.xls",
     "dane-weekly-xlsx", "0c5d68740b40d56b0001ed85b3c46897fb135e3bedc75741802043c0c5117f26"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana23_sep_27sep_2013.pdf",
     "dane-weekly-pdf", "ca2205284936795f03167c310ca401bb2beda72732c9db4d15a878134b378603"),
    # Exact December 2, 2019 daily workbook with a native month-label typo;
    # replay is pinned by exact URL, workbook SHA and source-local version.
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_02_2019.xlsx",
     "daily", "10a85133075b7e2c334bf472bda70df5d99ccdaec6640594ee7ac494d283a316"),
    # Exact retained Nov16/2021 ZIP with its reviewed unit/category parser.
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-16-11-2021.zip",
     "city-zip", "e4a8aa221892eb1d7eebb80e23e6d5419d406b87fa4243f205ee1f32b1fa8d10"),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_07_2020.xlsx', 'daily', '73e9e87255acfdae1c851920d084f00ed90d21baf754f848c88da6112971fe72'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_08_2020.xlsx', 'daily', '74f03719c5227c25c219b4b7475740b0382e61b911d025aeb5f13d71abaa81a1'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_09_2020.xlsx', 'daily', 'fe7ca4b678001889d58d945d2098a88877e53e35c77c74bbda0af6ea2123b7a3'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_10_2020.xlsx', 'daily', '4632f2426dda197ff7115c7801e28bfbf8eebcf012b6343e656ac1bfdff1e538'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_13_2020.xlsx', 'daily', 'eca65a7f770f62021b338f94aae46d96f6421ee5d2337f1db93de013a8c06d2b'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_14_2020.xlsx', 'daily', '872320bb98111d27365140203675f28bfbaf8856d437d977aee87de53ddfd5fb'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_15_2020.xlsx', 'daily', 'd0eea326eb44186c3ac0be8796da460897d9b78cee3f5f885784cc42d2353219'),
    ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_16_2020.xlsx', 'daily', '83885449eb25388a124efeed3fa7e642ce487cbd68a11051e6daba3ee460f787'),
)


def _exact_aug2013_completed_article_repair(db):
    """Exact retained M-source gate for the article-only source revision."""
    from . import dane_weekly, worker
    from .retained_pdf_upgrade import retained_aug2013_page43_original

    url = dane_weekly.AUG2013_PAGE43_URL
    kind = "dane-weekly-pdf"
    body = retained_aug2013_page43_original(
        db, url, kind,
        worker.asset_parser_version(kind, url),
        worker.parser_version(kind, url),
    )
    if body is None:
        return None
    return (url, kind, date(2013, 8, 23))


def _with_aug2013_repair_slot(rows, candidate, limit):
    """Use one existing slot, preserving the first selected weekly repair."""
    rows = list(rows)
    if candidate is None or candidate in rows or limit <= 0:
        return rows
    first_weekly = next(
        (index for index, (_, kind, _) in enumerate(rows)
         if kind == "dane-weekly-pdf"),
        None,
    )
    if first_weekly is None:
        return [candidate, *rows[:max(0, limit - 1)]]
    weekly = rows[first_weekly]
    if limit == 1:
        return [weekly]
    # Promote the first weekly repair and Aug together if needed. This avoids
    # starvation when the weekly row was last in a full lane, while preserving
    # the relative order of all remaining rows.
    remaining = rows[:first_weekly] + rows[first_weekly + 1:]
    return [weekly, candidate, *remaining[:max(0, limit - 2)]]


def repair_candidates(db, limit=8):
    """Reserve one stale archived original per kind ahead of ordinary backlog.

    Exact audited repairs lead their kind only while their URL, kind, SHA and
    parser version still match. Other stale originals advance oldest-checked
    first, so repeated current/pending assets cannot starve historical fixes.
    """
    limit = max(0, min(int(limit), 8))
    if not limit:
        return []
    aug2013_article = _exact_aug2013_completed_article_repair(db)
    from .retained_pdf_upgrade import (
        JUL2022_PENDING_URL, JUL2022_OLD_ASSET_VERSION,
        JUL2022_NEW_ASSET_VERSION, JUL2022_QUOTE_VERSION,
        JUL2022_PENDING_ERRORS, WEEKLY_NATIVE_PENDING_ORIGINALS,
        AUG2015_PENDING_URL, AUG2015_OLD_VERSION, AUG2015_NEW_VERSION,
        WEEKLY_COMPLETED_ORIGINALS,
    )
    # Probe the exact July 2022 pending continuation by PK first. The main
    # repair query also checks completion for exact pending 2013 bulletins,
    # so private TEMP fixtures must include ingestion_checkpoint.
    pending = db.execute(
        "SELECT status FROM ingestion_asset WHERE url=%s", (JUL2022_PENDING_URL,)
    ).fetchone()
    resume_checkpoint_open = False
    if pending is not None and pending[0] == 'pending':
        resume_checkpoint_open = not bool(db.execute(
            "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'",
            (WEEKLY_NATIVE_PENDING_ORIGINALS[JUL2022_PENDING_URL], JUL2022_QUOTE_VERSION),
        ).fetchone())
    values = ",".join("(%s,%s,%s)" for _ in PRIORITY_SOURCE_REPAIRS)
    rows = db.execute(
        f"""WITH config AS (SELECT %s::jsonb AS versions),
        pinned(url,kind,document_id) AS (VALUES {values}),
        source_bound_documents AS MATERIALIZED (
          SELECT a.url,a.document_id
          FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
          WHERE a.kind='inputs-pdf' AND d.kind='original'
            AND ((a.processor_version='inputs-pdf-v14' AND a.status IN ('complete','pending'))
              OR (a.processor_version='inputs-pdf-v17' AND a.status IN ('failed','pending')))
            AND d.media_type='application/pdf'
            AND d.metadata->>'retention'='permanent'
            AND d.metadata->>'ingestion_kind'='context-pdf'
            AND octet_length(d.content) BETWEEN 1 AND 33554432
            AND a.url ~ '^https://www[.]dane[.]gov[.]co/files/investigaciones/agropecuario/sipsa/(insumos_factores_de_produccion_[A-Za-z0-9_%%.-]+|Bol_(%%20| )?Insumos[A-Za-z0-9_%% .-]+)[.]pdf$'
            AND (d.source_url=a.url OR
              (a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_ Insumos_ene_2019.pdf'
               AND a.document_id='849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb'
               AND d.source_url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_%%20Insumos_ene_2019.pdf'))
            AND d.metadata->>'original_filename'=CASE
              WHEN a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_ Insumos_ene_2019.pdf'
              THEN 'Bol_%%20Insumos_ene_2019.pdf' ELSE regexp_replace(a.url,'^.*/','') END
            AND d.title='DANE - '||(d.metadata->>'original_filename')
            AND d.publisher='DANE'
            AND d.page_count BETWEEN 1 AND 256
            AND (a.url NOT IN (
                  'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_%%20Insumos_ene_2019.pdf',
                  'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_ Insumos_ene_2019.pdf')
                 OR (a.document_id='849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb'
                     AND a.observed_on='2019-01-31'::date AND a.records=14458
                     AND d.page_count=206 AND octet_length(d.content)=3681233
                     AND d.reference_period='Serie histórica completa'))
            AND (d.reference_period=a.observed_on::text OR
              (a.document_id='849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb'
               AND a.observed_on='2019-01-31'::date
               AND d.reference_period='Serie histórica completa'))
        ), source_bound_cohorts AS MATERIALIZED (
          SELECT h.document_id,count(*) AS raw_rows,
            count(*) FILTER (WHERE h.series='dane-inputs-pdf') AS typed_rows,
            count(*) FILTER (WHERE h.series='dane-inputs-pdf-unresolved') AS unresolved_rows
          FROM historical_price h JOIN
            (SELECT DISTINCT document_id FROM source_bound_documents) d USING (document_id)
          WHERE h.details->>'parser_version'='inputs-pdf-v14'
          GROUP BY h.document_id
        ), jan2019_v17_cohort AS MATERIALIZED (
          SELECT count(*) AS raw_rows,
            count(*) FILTER (WHERE h.series='dane-inputs-pdf') AS typed_rows,
            count(*) FILTER (WHERE h.series='dane-inputs-pdf-unresolved') AS unresolved_rows
          FROM historical_price h
          WHERE h.document_id='849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb'
            AND EXISTS (SELECT 1 FROM source_bound_documents d
              WHERE d.document_id='849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb')
            AND h.details->>'parser_version'='inputs-pdf-v17'
        ), long_input_retry_assets AS MATERIALIZED (
          SELECT a.url,a.document_id,a.records
          FROM ingestion_asset a JOIN pinned p ON (p.url,p.kind,p.document_id)=
            (a.url,a.kind,a.document_id)
          WHERE a.kind='inputs-pdf' AND a.processor_version='inputs-pdf-v17'
            AND ((a.status='failed'
                  AND a.error='ValueError: Retained input PDF page count mismatch')
              OR (a.status='pending'
                  AND a.error='PDF page checkpoint retained; extraction will resume within the next run budget')
              OR (a.status IN ('failed','pending')
                  AND a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_nov_2018.pdf'
                  AND a.observed_on='2018-11-30'::date AND a.records=15241
                  AND a.error='ValueError: Retained input old publication checkpoint changed')
              OR (a.status IN ('failed','pending')
                  AND a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_dic_2018.pdf'
                  AND a.observed_on='2018-12-31'::date AND a.records=13906
                  AND a.error='ValueError: Retained input old publication checkpoint changed'))
            AND NOT EXISTS (SELECT 1 FROM ingestion_checkpoint done
              WHERE done.document_id=a.document_id AND done.processor_version='inputs-pdf-v17'
                AND done.step='inputs-pdf:published')
        ), long_v14_cohorts AS MATERIALIZED (
          SELECT h.document_id,count(*) AS raw_rows,
            count(*) FILTER (WHERE h.series='dane-inputs-pdf') AS typed_rows,
            count(*) FILTER (WHERE h.series='dane-inputs-pdf-unresolved') AS unresolved_rows
          FROM historical_price h JOIN long_input_retry_assets a USING (document_id)
          WHERE h.document_id IN (
            'f37ddee1c655810d1e6a6ea7746bd1a429337fd22deda2b3db8c52762780a2fb',
            '8c5e95de023a6fafd71484dc476c40083aa886d05ca00f90ada498cac05043f7',
            '79b2dadcad9c2387648b64620d92a896b5ef5d8f9a2d366e522021ff62d7cbb3',
            '7b33370ff3eb28f8567fb36528dc8c2c619aad1629c1aaf761f7448269ceb293')
            AND h.details->>'parser_version'='inputs-pdf-v14'
          GROUP BY h.document_id
        ), long_input_retries AS MATERIALIZED (
          SELECT a.url,a.document_id
          FROM ingestion_asset a JOIN pinned p ON (p.url,p.kind,p.document_id)=
            (a.url,a.kind,a.document_id)
          JOIN source_document d ON d.id=a.document_id
          JOIN long_v14_cohorts h ON h.document_id=a.document_id
          JOIN ingestion_checkpoint old ON old.document_id=a.document_id
            AND old.processor_version='inputs-pdf-v14'
            AND old.step='inputs-pdf:published' AND old.records=h.typed_rows
          WHERE a.kind='inputs-pdf' AND a.processor_version='inputs-pdf-v17'
            AND ((a.status='failed'
                  AND a.error='ValueError: Retained input PDF page count mismatch')
              OR (a.status='pending'
                  AND a.error='PDF page checkpoint retained; extraction will resume within the next run budget')
              OR (a.status IN ('failed','pending')
                  AND a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_nov_2018.pdf'
                  AND a.document_id='79b2dadcad9c2387648b64620d92a896b5ef5d8f9a2d366e522021ff62d7cbb3'
                  AND a.observed_on='2018-11-30'::date AND a.records=15241
                  AND a.error='ValueError: Retained input old publication checkpoint changed')
              OR (a.status IN ('failed','pending')
                  AND a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_dic_2018.pdf'
                  AND a.document_id='7b33370ff3eb28f8567fb36528dc8c2c619aad1629c1aaf761f7448269ceb293'
                  AND a.observed_on='2018-12-31'::date AND a.records=13906
                  AND a.error='ValueError: Retained input old publication checkpoint changed'))
            AND h.raw_rows=a.records AND h.raw_rows=h.typed_rows+h.unresolved_rows
            AND NOT EXISTS (SELECT 1 FROM ingestion_checkpoint done
              WHERE done.document_id=a.document_id AND done.processor_version='inputs-pdf-v17'
                AND done.step='inputs-pdf:published')
            AND d.kind='original' AND d.media_type='application/pdf'
            AND d.metadata->>'retention'='permanent'
            AND d.metadata->>'ingestion_kind'='inputs-pdf'
            AND d.publisher='DANE'
            AND ((a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_sep_2018.pdf'
                  AND a.document_id='f37ddee1c655810d1e6a6ea7746bd1a429337fd22deda2b3db8c52762780a2fb'
                  AND a.observed_on='2018-09-30'::date AND a.records=15344
                  AND d.source_url=a.url AND d.page_count=201 AND octet_length(d.content)=4430044
                  AND d.reference_period='2018-09-30'
                  AND d.title='DANE - Bol_Insumos_sep_2018.pdf'
                  AND d.metadata->>'original_filename'='Bol_Insumos_sep_2018.pdf'
                  AND (h.raw_rows,h.typed_rows,h.unresolved_rows)=(15344,15339,5))
              OR (a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_feb_2019.pdf'
                  AND a.document_id='8c5e95de023a6fafd71484dc476c40083aa886d05ca00f90ada498cac05043f7'
                  AND a.observed_on='2019-02-28'::date AND a.records=14366
                  AND d.source_url=a.url AND d.page_count=209 AND octet_length(d.content)=3976584
                  AND d.reference_period='2019-02-28'
                  AND d.title='DANE - Bol_Insumos_feb_2019.pdf'
                  AND d.metadata->>'original_filename'='Bol_Insumos_feb_2019.pdf'
                  AND (h.raw_rows,h.typed_rows,h.unresolved_rows)=(14366,14363,3))
              OR (a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_nov_2018.pdf'
                  AND a.document_id='79b2dadcad9c2387648b64620d92a896b5ef5d8f9a2d366e522021ff62d7cbb3'
                  AND a.observed_on='2018-11-30'::date AND a.records=15241
                  AND d.source_url=a.url AND d.page_count=195 AND octet_length(d.content)=2806034
                  AND d.reference_period='2018-11-30'
                  AND d.title='DANE - Bol_Insumos_nov_2018.pdf'
                  AND d.metadata->>'original_filename'='Bol_Insumos_nov_2018.pdf'
                  AND (h.raw_rows,h.typed_rows,h.unresolved_rows)=(15241,15215,26))
              OR (a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_dic_2018.pdf'
                  AND a.document_id='7b33370ff3eb28f8567fb36528dc8c2c619aad1629c1aaf761f7448269ceb293'
                  AND a.observed_on='2018-12-31'::date AND a.records=13906
                  AND d.source_url=a.url AND d.page_count=180 AND octet_length(d.content)=2627644
                  AND d.reference_period='2018-12-31'
                  AND d.title='DANE - Bol_Insumos_dic_2018.pdf'
                  AND d.metadata->>'original_filename'='Bol_Insumos_dic_2018.pdf'
                  AND (h.raw_rows,h.typed_rows,h.unresolved_rows)=(13906,13888,18)))
        ), source_bound_context AS MATERIALIZED (
          SELECT d.url,d.document_id
          FROM source_bound_documents d JOIN source_bound_cohorts h USING (document_id)
          CROSS JOIN jan2019_v17_cohort j
          JOIN ingestion_asset a ON (a.url,a.document_id)=(d.url,d.document_id)
          JOIN ingestion_checkpoint old ON old.document_id=d.document_id
            AND old.processor_version='inputs-pdf-v14'
            AND old.step='inputs-pdf:published' AND old.records=h.typed_rows
          WHERE h.raw_rows=a.records
            AND h.raw_rows=h.typed_rows+h.unresolved_rows
            AND ((a.processor_version='inputs-pdf-v14'
                  AND a.status IN ('complete','pending'))
              OR (a.processor_version='inputs-pdf-v17'
                  AND a.status IN ('failed','pending')
                  AND (a.error IN (
                    'ValueError: Retained input original identity/bytes mismatch',
                    'PDF page checkpoint retained; extraction will resume within the next run budget')
                    OR (d.document_id='849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb'
                        AND a.error='ValueError: Retained input PDF page count mismatch'))
                  AND (NOT EXISTS (SELECT 1 FROM ingestion_checkpoint done
                    WHERE done.document_id=d.document_id
                      AND done.processor_version='inputs-pdf-v17'
                      AND done.step='inputs-pdf:published')
                    OR (d.document_id='849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb'
                        AND a.url IN (
                          'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_%%20Insumos_ene_2019.pdf',
                          'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_ Insumos_ene_2019.pdf')
                        AND EXISTS (SELECT 1 FROM ingestion_checkpoint done
                          WHERE done.document_id=d.document_id
                            AND done.processor_version='inputs-pdf-v17'
                            AND done.step='inputs-pdf:published'
                            AND done.records=14443)
                        AND (j.raw_rows,j.typed_rows,j.unresolved_rows)=(14458,14443,15)))))
        ), eligible AS (
          SELECT a.url,a.kind,a.observed_on,a.checked_at,
            CASE WHEN p.url IS NOT NULL OR cx.url IS NOT NULL OR li.url IS NOT NULL THEN 0 ELSE 1 END AS pin,
            row_number() OVER (PARTITION BY a.kind ORDER BY
              CASE WHEN a.url IN (
                'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_sep_2018.pdf',
                'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_%%20Insumos_ene_2019.pdf',
                'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_ Insumos_ene_2019.pdf',
                'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_feb_2019.pdf',
                'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_nov_2018.pdf',
                'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_dic_2018.pdf'
              ) THEN 0 WHEN cx.url IS NOT NULL THEN 1 ELSE 2 END,
              CASE WHEN a.url=%s AND a.status='pending' THEN 0 ELSE 1 END,
              CASE WHEN p.url IS NULL THEN 1 ELSE 0 END,
              a.checked_at ASC NULLS FIRST,a.observed_on ASC NULLS LAST,a.url) AS turn
          FROM ingestion_asset a CROSS JOIN config c
          LEFT JOIN pinned p ON (p.url,p.kind,p.document_id)=(a.url,a.kind,a.document_id)
          LEFT JOIN source_bound_context cx ON (cx.url,cx.document_id)=(a.url,a.document_id)
          LEFT JOIN long_input_retries li ON (li.url,li.document_id)=(a.url,a.document_id)
          JOIN source_document d ON d.id=a.document_id AND d.kind='original'
            AND (d.metadata->>'ingestion_kind'=a.kind OR p.url IS NOT NULL OR cx.url IS NOT NULL)
          WHERE (a.status IN ('complete','failed','review')
                 OR (a.kind='inputs-pdf' AND a.status='pending'
                     AND a.url IN (
                       'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_feb_2014.pdf',
                       'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mar_2014.pdf',
                       'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_may_2014.pdf')
                     AND p.document_id IS NOT NULL
                     AND (a.url,a.observed_on,a.records) IN (
                       ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_feb_2014.pdf','2014-02-28'::date,4794),
                       ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mar_2014.pdf','2014-03-31'::date,5706),
                       ('https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_may_2014.pdf','2014-05-31'::date,5977))
                     AND a.processor_version='inputs-pdf-v14'
                     AND d.source_url=a.url AND d.media_type='application/pdf'
                     AND d.metadata->>'ingestion_kind'='context-pdf'
                     AND EXISTS (SELECT 1 FROM ingestion_checkpoint old
                       WHERE old.document_id=d.id AND old.processor_version='inputs-pdf-v14'
                         AND old.step='inputs-pdf:published'))
                 OR cx.url IS NOT NULL OR li.url IS NOT NULL
                 OR (a.url=%s AND a.kind='city-zip' AND a.status='pending'
                     AND a.observed_on=%s AND p.document_id=%s
                     AND d.source_url=a.url AND d.media_type='application/zip'
                     AND d.metadata->>'ingestion_kind'='city-zip'
                     AND EXISTS (SELECT 1 FROM ingestion_checkpoint child
                       WHERE child.document_id=a.document_id
                         AND child.processor_version=%s AND child.step=%s
                         AND child.records=196))
                 OR (a.url IN (
                       'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_16nov_22nov_2013.pdf',
                       'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_29nov_6dic_2013.pdf',
                       'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_6dic_13dic_2013.pdf')
                     AND a.kind='dane-weekly-pdf' AND a.status='pending'
                     AND a.records=0 AND a.processor_version IN ('', 'official-v2:dane-weekly-v24')
                     AND p.document_id IS NOT NULL
                     AND d.source_url=a.url AND d.media_type='application/pdf'
                     AND d.metadata->>'ingestion_kind'='dane-weekly-pdf'
                     AND (a.error IS NULL
                       OR a.error='ValueError: Weekly PDF page 43 has conflicting printed periods'
                       OR a.error IN (
                         'Official source validated; committed quote batches will resume',
                         'Official quote batches retained; catalog completion will resume')
                       OR a.error ~ '^Official catalog refresh deferred after [0-9]+ of [0-9]+ identities$')
                     AND NOT EXISTS (SELECT 1 FROM ingestion_checkpoint done
                       WHERE done.document_id=a.document_id
                         AND done.processor_version='official-v2:dane-weekly-v24'
                         AND done.step='official:complete'))
                 OR (a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_18_2019.pdf'
                     AND a.kind='daily-pdf' AND a.status='awaiting-ocr'
                     AND p.document_id='4e0ddac5f22c1c852be933d1056a66c45b67a63886aab9a2cbd7fba688a1b3ac'
                     AND d.source_url=a.url AND d.media_type='application/pdf')
                 OR (a.url=ANY(%s::text[]) AND a.kind='dane-weekly-pdf'
                     AND a.status='awaiting-ocr' AND a.records=0
                     AND p.document_id IS NOT NULL AND d.source_url=a.url
                     AND d.media_type='application/pdf'
                     AND d.metadata->>'ingestion_kind'='dane-weekly-pdf'
                     AND a.processor_version='official-v2:dane-weekly-v23')
                 OR (a.url=%s AND a.kind='dane-weekly-pdf'
                     AND a.status='pending' AND a.records=0
                     AND p.document_id IS NOT NULL AND d.source_url=a.url
                     AND d.media_type='application/pdf'
                     AND d.metadata->>'ingestion_kind'='dane-weekly-pdf'
                     AND a.processor_version=%s
                     AND coalesce(c.versions->>('url:'||a.url),c.versions->>a.kind)=%s
                     AND (a.error=ANY(%s::text[]) OR
                          a.error ~ '^Official catalog refresh deferred after [0-9]+ of [0-9]+ identities$')
                     AND %s::boolean)
                 OR (a.url=%s AND a.kind='dane-weekly-pdf'
                     AND a.status='pending' AND p.document_id=%s
                     AND a.processor_version=ANY(%s::text[])
                     AND c.versions->>('url:'||a.url)=%s
                     AND d.source_url=a.url AND d.media_type='application/pdf'
                     AND d.metadata->>'ingestion_kind'='dane-weekly-pdf'
                     AND (a.error IN (
                       'Official source validated; committed quote batches will resume',
                       'Official quote batches retained; catalog completion will resume',
                       'Committed official batches retained; next work deferred')
                       OR a.error ~ '^Official catalog refresh deferred after [0-9]+ of [0-9]+ identities$')
                     AND NOT EXISTS (SELECT 1 FROM ingestion_checkpoint done
                       WHERE done.document_id=a.document_id
                         AND done.processor_version=%s
                         AND done.step='official:complete'))
                 OR (a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_18_2019.pdf'
                     AND a.kind='daily-pdf' AND a.status='processed' AND a.records=0
                     AND p.document_id='4e0ddac5f22c1c852be933d1056a66c45b67a63886aab9a2cbd7fba688a1b3ac'
                     AND a.processor_version='daily-pdf-v6:supply-daily-pdf-summary-v1:feb2019-verified-cover-v1'
                     AND d.source_url=a.url AND d.media_type='application/pdf')
                 OR (a.url=ANY(%s::text[]) AND a.kind='daily-pdf'
                     AND a.status='processed' AND a.records=0
                     AND p.document_id IS NOT NULL AND d.source_url=a.url
                     AND d.media_type='application/pdf'
                     AND d.metadata->>'ingestion_kind'='daily-pdf')
                 OR (a.url=%s AND a.kind='city-zip' AND a.status='pending'
                     AND p.document_id=%s AND a.observed_on=%s
                     AND a.processor_version IN ('city-v8',%s)
                     AND d.source_url=a.url AND d.media_type='application/zip'
                     AND d.metadata->>'ingestion_kind'='city-zip'
                     AND EXISTS (SELECT 1 FROM ingestion_checkpoint done
                       WHERE done.document_id=a.document_id
                         AND done.processor_version=%s
                         AND done.step=%s AND done.records=59)))
            AND a.kind NOT LIKE '%%-index'
            AND (a.processor_version IS DISTINCT FROM
                   coalesce(c.versions->>('url:'||a.url),c.versions->>a.kind,'source-v1')
              OR (a.url=%s AND a.kind='city-zip' AND p.document_id=%s
                  AND a.status IN ('review','failed') AND a.observed_on=%s
                  AND a.processor_version=%s
                  AND d.source_url=a.url AND d.media_type='application/zip'
                  AND d.metadata->>'ingestion_kind'='city-zip'
                  AND NOT EXISTS (SELECT 1 FROM ingestion_checkpoint done
                    WHERE done.document_id=a.document_id
                      AND done.processor_version=a.processor_version
                      AND done.step=%s AND done.records=53))
              OR (a.url=%s AND a.kind='city-zip' AND p.document_id=%s
                  AND a.status IN ('review','failed') AND a.observed_on=%s
                  AND a.processor_version=%s
                  AND d.source_url=a.url AND d.media_type='application/zip'
                  AND d.metadata->>'ingestion_kind'='city-zip'
                  AND (NOT EXISTS (SELECT 1 FROM ingestion_checkpoint done
                    WHERE done.document_id=a.document_id
                      AND done.processor_version=a.processor_version
                      AND done.step=%s AND done.records=35)
                    OR NOT EXISTS (SELECT 1 FROM ingestion_checkpoint review
                      WHERE review.document_id=a.document_id
                        AND review.processor_version=a.processor_version
                        AND review.step=%s AND review.records=0)
                    OR (SELECT count(*) FROM ingestion_checkpoint cp
                      WHERE cp.document_id=a.document_id
                        AND cp.processor_version=a.processor_version
                        AND cp.step LIKE 'city-member:%%')<>18
                    OR (SELECT coalesce(sum(records),0) FROM ingestion_checkpoint cp
                      WHERE cp.document_id=a.document_id
                        AND cp.processor_version=a.processor_version
                        AND cp.step LIKE 'city-member:%%')<>1418))
              OR (a.url=%s AND a.kind='city-zip' AND p.document_id=%s
                  AND a.status IN ('review','failed','pending') AND a.observed_on=%s
                  AND a.processor_version=%s
                  AND d.source_url=a.url AND d.media_type='application/zip'
                  AND d.metadata->>'ingestion_kind'='city-zip')
              OR (a.url=%s AND a.kind='city-zip' AND p.document_id=%s
                  AND a.status='review' AND a.observed_on=%s AND a.records=0
                  AND a.attempts<3 AND a.processor_version=%s
                  AND a.error=%s AND d.source_url=a.url
                  AND d.media_type='application/zip'
                  AND d.metadata->>'retention'='permanent'
                  AND d.metadata->>'ingestion_kind'='city-zip'
                  AND d.metadata->>'original_filename'='bol-reg-03-01-2023.zip')
              OR cx.url IS NOT NULL OR li.url IS NOT NULL)

            AND (a.checked_at IS NULL OR a.checked_at<now()-interval '6 hours'
                 OR (a.url=%s AND p.url IS NOT NULL AND a.status='failed'
                     AND a.processor_version=%s AND a.error=%s
                     AND d.source_url=a.url
                     AND d.media_type='application/vnd.ms-excel'
                     AND d.metadata->>'ingestion_kind'='dane-weekly-xlsx')
                 OR (a.url=%s AND p.url IS NOT NULL AND a.status='processed'
                     AND a.records=0 AND a.processor_version=%s
                     AND d.source_url=a.url AND d.media_type='application/pdf'
                     AND d.metadata->>'ingestion_kind'='daily-pdf')
                 OR (a.url=%s AND p.url IS NOT NULL AND a.status='failed'
                     AND a.processor_version=%s AND a.error=%s
                     AND d.source_url=a.url
                     AND d.media_type='application/vnd.ms-excel'
                     AND d.metadata->>'ingestion_kind'='daily')
                 OR (a.url IN (
                       'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb8_2014.xls',
                       'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb15_2014.xls',
                       'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb22_2014.xls')
                     AND p.url IS NOT NULL AND a.kind='dane-weekly-xlsx'
                     AND a.status='failed' AND a.records=0
                     AND a.observed_on IS NULL AND a.attempts<=3
                     AND a.processor_version=c.versions->>'dane-weekly-xlsx'
                     AND ((a.url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb8_2014.xls'
                           AND a.error ~ '^HTTP 429 from www[.]dane[.]gov[.]co; retry after 20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?[+]00:00$')
                       OR (a.url IN (
                           'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb15_2014.xls',
                           'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb22_2014.xls')
                           AND a.error='ValueError: Weekly grouped workbook has no explicit period in cells or URL'))
                     AND d.id=p.document_id AND d.source_url=a.url
                     AND d.title='DANE · SIPSA - '||regexp_replace(a.url,'^.*/','')
                     AND d.publisher='DANE · SIPSA' AND d.kind='original'
                     AND d.media_type='application/vnd.ms-excel'
                     AND d.reference_period='Serie histórica completa'
                     AND d.page_count IS NULL
                     AND d.metadata->>'retention'='permanent'
                     AND d.metadata->>'ingestion_kind'='dane-weekly-xlsx'
                     AND d.metadata->>'original_filename'=regexp_replace(a.url,'^.*/','')
                     AND octet_length(d.content)=CASE a.url
                       WHEN 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb8_2014.xls' THEN 446976
                       WHEN 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb15_2014.xls' THEN 447488
                       ELSE 448000 END)
                 OR (a.url=%s AND p.url IS NOT NULL AND a.status='review'
                     AND a.processor_version=%s AND a.error=%s
                     AND d.source_url=a.url
                     AND d.media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                     AND d.metadata->>'ingestion_kind'='supply-reference')
                 OR cx.url IS NOT NULL OR li.url IS NOT NULL
                 OR (a.url=ANY(%s::text[]) AND p.url IS NOT NULL
                     AND a.status='processed' AND a.records=0
                     AND a.processor_version='daily-pdf-v6:supply-daily-pdf-summary-v1'
                     AND d.source_url=a.url AND d.media_type='application/pdf')
                 OR (a.url=%s AND p.url IS NOT NULL
                     AND a.kind='dane-weekly-pdf' AND a.status='complete'
                     AND a.processor_version=%s
                     AND d.source_url=a.url AND d.media_type='application/pdf'
                     AND d.metadata->>'ingestion_kind'='dane-weekly-pdf'))
        ) SELECT url,kind,observed_on FROM eligible WHERE turn=1
          ORDER BY pin, CASE WHEN kind='inputs-pdf' THEN 0 ELSE 1 END, CASE WHEN kind='city-zip' THEN 0 ELSE 1 END,
            CASE WHEN kind LIKE 'international-%%' OR kind LIKE 'colombia-%%'
                   OR kind IN ('coffee','coffee-pdf') THEN 1 ELSE 0 END,
            checked_at ASC NULLS FIRST,kind,url LIMIT %s""",
        (expected_versions(),
         *(part for row in PRIORITY_SOURCE_REPAIRS for part in row),
         JUL2022_PENDING_URL,
         corabastos_proof.URL, corabastos_proof.DAY, corabastos_proof.PARENT,
         corabastos_proof.VERSION, corabastos_proof.MEMBER_STEP,
         [row[0] for row in PRIORITY_SOURCE_REPAIRS[2:4]],
         JUL2022_PENDING_URL, JUL2022_OLD_ASSET_VERSION,
         JUL2022_NEW_ASSET_VERSION,
         list(JUL2022_PENDING_ERRORS), resume_checkpoint_open,
         AUG2015_PENDING_URL, WEEKLY_COMPLETED_ORIGINALS[AUG2015_PENDING_URL],
         [AUG2015_OLD_VERSION, AUG2015_NEW_VERSION],
         AUG2015_NEW_VERSION, AUG2015_NEW_VERSION,
         [row[0] for row in PRIORITY_SOURCE_REPAIRS[:2]],
         ARMENIA_OCR_URL, ARMENIA_OCR_SHA, date(2024, 1, 25),
         ARMENIA_OCR_VERSION, ARMENIA_OCR_VERSION, ARMENIA_OCR_STEP,
         ARMENIA_EXACT_URL, ARMENIA_EXACT_SHA, date(2022, 1, 11),
         ARMENIA_EXACT_VERSION, ARMENIA_EXACT_STEP,
         VALLEDUPAR_EXACT_URL, VALLEDUPAR_EXACT_SHA, date(2022, 1, 7),
         VALLEDUPAR_EXACT_VERSION, VALLEDUPAR_EXACT_STEP,
         VALLEDUPAR_EXACT_REVIEW_STEP,
         ARMENIA_OCR_URL, ARMENIA_OCR_SHA, date(2024, 1, 25),
         ARMENIA_OCR_VERSION,
         "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol-reg-03-01-2023.zip",
         "220e0d23060a337f4307b5f93e729fa4f777e89e4373228cb6552a68b8da2c04",
         date(2023, 1, 3), "city-v8:jan2023-local-source-adjudication-v1",
         "InsufficientPrivilege: permission denied for table source_document",
         "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_21feb_27feb_2015.xls",
         "official-v2:audited-unit-review-2018-v1:dane-weekly-v20",
         "ValueError: Weekly grouped workbook has incomplete monetary cells",
         "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_18_2019.pdf",
         "daily-pdf-v6:supply-daily-pdf-summary-v1:feb2019-verified-cover-v1",
         "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_septiembre_5_2016.xls",
         "daily-units-v6:dane-daily-query-v1",
         "ValueError: Unsupported original archive suffix",
         "https://www.dane.gov.co/files/investigaciones/agropecuario/anexo_abastecimiento_ene23.xlsx",
         "supply-daily-summary-v1:supply-period-summary-workbook-v2",
         "TypeError: Object of type datetime is not JSON serializable",
         [row[0] for row in PRIORITY_SOURCE_REPAIRS[:2]],
         "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSASemanal-23mar-27mar-2024.pdf",
         "official-v2:dane-weekly-v20", limit),
    ).fetchall()
    # Keep the first selected weekly repair ahead of the exact Aug article
    # upgrade, even when the weekly row was last in a full lane. The lane cap
    # remains fixed and displaced rows retain their normal later eligibility.
    return _with_aug2013_repair_slot(rows, aug2013_article, limit)


def expected_versions():
    from . import (
        coffee_sources,
        colombia_sources,
        dane_weekly,
        international_sources,
        worker,
    )

    kinds = (
        set(worker.PARSER_VERSIONS)
        | set(colombia_sources.PUBLISHERS)
        | set(international_sources.PUBLISHERS)
        | set(coffee_sources.PUBLISHERS)
        | set(dane_weekly.PUBLISHERS)
    )
    versions = {kind: worker.parser_version(kind) for kind in kinds}
    from .daily_prose import AUDITED as AUDITED_PROSE
    from .daily_prose_generic import VERSION as PROSE_GENERIC_VERSION
    versions["daily-pdf-generic"] = (
        worker.parser_version("daily-pdf") + ":" + PROSE_GENERIC_VERSION
    )
    versions["daily-pdf-generic-excluded"] = sorted(AUDITED_PROSE)
    # Every exact weekly revision must appear in the queue's version map.
    # Otherwise completed assets look current despite a corrected parser,
    # and newly reviewed assets look outdated despite using that parser.
    from .reviewed_weekly_feb2014 import PAIRS as FEB2014_PAIRS
    from .reviewed_weekly_native_context import URLS as NATIVE_CONTEXT_URLS
    for url in (set(dane_weekly.RICE_MONTHLY_CONFLICT_URLS)
                | set(FEB2014_PAIRS) | set(NATIVE_CONTEXT_URLS)):
        versions["url:" + url] = worker.asset_parser_version("dane-weekly-xlsx", url)
    for url in (
        dane_weekly.JANUARY_2017_JAN13_URL, dane_weekly.JUNE_2012_FONT_RUN_URL,
        dane_weekly.AUGUST_2015_WRAP_URL, dane_weekly.AUG2014_PAGE43_URL,
        dane_weekly.AUG2013_PAGE43_URL,
        dane_weekly.NOV2019_COTINUACION_URL,
        dane_weekly.NOVEMBER_2016_MEDELLIN_WRAP_URL,
        dane_weekly.MAY2013_WHITE_CORN_URL, dane_weekly.JULY2012_CONFLICT_URL,
        "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_16jun_20jun_2014.pdf",
    ):
        versions["url:" + url] = worker.asset_parser_version("dane-weekly-pdf", url)
    for url, (kind, _) in worker.URL_SOURCE_REPAIR_VERSIONS.items():
        versions["url:" + url] = worker.asset_parser_version(kind, url)
    for url, kind, _ in PRIORITY_SOURCE_REPAIRS:
        expected = worker.asset_parser_version(kind, url)
        if expected != worker.parser_version(kind):
            versions["url:" + url] = expected
    from .corabastos_source_relocation import KIND
    from .corabastos_locator_replay import VERIFIED_WORKER_SOURCES
    for url in VERIFIED_WORKER_SOURCES.values():
        versions["url:" + url] = worker.asset_parser_version(KIND, url)
    return Jsonb(versions)


def daily_candidates(db, today):
    from .colombia_sources import ROOTS as colombia
    from .dane_weekly import ROOTS as weekly
    from .international_sources import ROOTS as international

    roots = [url for url, _ in (*colombia, *international, *weekly)]
    source_repairs = Jsonb([
        {"url": url, "kind": kind, "sha": digest}
        for url, kind, digest in PRIORITY_SOURCE_REPAIRS
    ])
    return db.execute(
        """WITH config AS (SELECT %s::jsonb AS versions, %s::jsonb AS source_repairs),
        source_assets AS (
          SELECT a.*,c.source_repairs,
            coalesce(c.versions->>('url:'||a.url),
              CASE WHEN a.kind='daily-pdf' AND a.url ~
                '^https://www[.]dane[.]gov[.]co/files/operaciones/SIPSA/bol-SIPSADiario-[0-9]{2}[a-z]{3}[0-9]{4}[.]pdf$'
                AND NOT (c.versions->'daily-pdf-generic-excluded' ? a.url)
                THEN c.versions->>'daily-pdf-generic' END,
              c.versions->>a.kind,'source-v1') AS expected_version
          FROM ingestion_asset a CROSS JOIN config c
        ), versions AS (
          SELECT a.*,a.processor_version IS DISTINCT FROM a.expected_version AS outdated,
            (a.processor_version IS DISTINCT FROM a.expected_version
             AND EXISTS (SELECT 1 FROM jsonb_array_elements(a.source_repairs) repair
               WHERE repair->>'url'=a.url AND repair->>'kind'=a.kind
                 AND repair->>'sha'=a.document_id)) AS exact_source_repair
          FROM source_assets a
        ), fresh AS (
          SELECT url,row_number() OVER(PARTITION BY kind ORDER BY discovered_at DESC,url) AS turn
          FROM ingestion_asset WHERE (kind LIKE 'colombia-%%' OR kind LIKE 'international-%%' OR kind IN ('dane-weekly-xlsx','dane-weekly-pdf'))
          AND observed_on IS NULL AND status='pending'
          AND discovered_at>=now()-interval '48 hours'
        ), candidates AS (SELECT a.*,row_number() OVER(PARTITION BY kind ORDER BY
          CASE WHEN status='pending' THEN 0 ELSE 1 END, observed_on DESC NULLS LAST,
          checked_at ASC NULLS FIRST,url) turn FROM versions a WHERE (
          a.url=ANY(%s::text[]) OR kind IN ('international-worldbank-monthly','colombia-fedegan-csv') OR
          (kind='dane-weekly-xlsx' AND status='review'
           AND coalesce(error,'') LIKE 'DANE weekly native rows lack explicit workbook period or unit; retained as untyped source review%%'
           AND checked_at<now()-interval '30 days'
           AND EXISTS (SELECT 1 FROM official_source_review r
             WHERE r.document_id=a.document_id AND r.parser_version=a.processor_version
             AND r.source_locator='XLS document-level native context review'
             AND r.record->'details'->>'quality_issue'='DANE weekly native rows lack explicit workbook period or unit; retained as untyped source review'
             AND r.record->'details'->>'original_sha256'=a.document_id
             AND r.record->'details'->>'source_url'=a.url)) OR
          (kind='dane-weekly-index' AND url ~ %s) OR
          (kind IN ('dane-weekly-xlsx','dane-weekly-pdf') AND observed_on>=%s) OR
          (kind NOT LIKE 'international-%%' AND kind NOT LIKE 'colombia-%%' AND (
            kind IN ('inputs','inputs-municipal','coffee','coffee-pdf','rice') OR
            (kind IN ('monthly','supply','supply-reference','supply-index') AND
             (url ~ %s OR observed_on>=%s OR kind='supply-reference')) OR
            (kind='milk' AND url ~* %s) OR
            (kind IN ('milk','monthly-annex','inputs-annex','inputs-reference','inputs-pdf','milk-pdf','monthly-pdf','supply-reference-pdf') AND (observed_on IS NULL OR observed_on>=%s)) OR
            (kind IN ('daily','daily-pdf','city-pdf','city-zip','daily-zip') AND observed_on>=%s)
          )) OR ((kind LIKE 'international-%%' OR kind LIKE 'colombia-%%') AND observed_on>=%s)
          OR a.url IN (SELECT url FROM fresh WHERE turn<=3)
          OR exact_source_repair)
          AND (outdated OR (status='awaiting-ocr' AND checked_at<now()-interval '1 day')
               OR (status<>'awaiting-ocr' AND (status<>'review' OR checked_at<now()-interval '1 day')))
          AND NOT (kind='coffee'
                   AND coalesce(error,'') LIKE 'FNC index replaced verified 404 URL:%%')
          AND NOT (url='https://esmis.nal.usda.gov/sites/default/release-files/4x51hj05x/xp68nh41n/pg15dd132/MH_FV221.PDF'
                   AND kind='international-usda-miami-flowers' AND status='review' AND NOT outdated
                   AND coalesce(error,'') LIKE 'USDA verified August 18 replacement: %%'
                   AND checked_at>=now()-interval '30 days')
          AND NOT (kind='dane-weekly-pdf' AND status='review' AND NOT outdated
                   AND document_id='c3192584b35f69b03e8ba93872f9807f04109631d87fa76fc4671d06c05f4a64'
                   AND coalesce(error,'') LIKE 'SourceDateMismatch: Weekly printed period conflicts with the dated source URL%%'
                   AND checked_at>=now()-interval '30 days')
          AND NOT (kind='monthly-pdf' AND status='review'
                   AND coalesce(error,'') LIKE 'DANE monthly index identifies nonprice press release: %%')
          AND NOT (kind='dane-weekly-xlsx' AND status='review' AND NOT outdated
                   AND coalesce(error,'') LIKE 'DANE weekly native rows lack explicit workbook period or unit; retained as untyped source review%%'
                   AND checked_at>=now()-interval '30 days'
                   AND EXISTS (SELECT 1 FROM official_source_review r
                     WHERE r.document_id=a.document_id AND r.parser_version=a.processor_version
                     AND r.source_locator='XLS document-level native context review'
                     AND r.record->'details'->>'quality_issue'='DANE weekly native rows lack explicit workbook period or unit; retained as untyped source review'
                     AND r.record->'details'->>'original_sha256'=a.document_id
                     AND r.record->'details'->>'source_url'=a.url))
          AND NOT (kind='dane-weekly-xlsx' AND status='review' AND NOT outdated
                   AND coalesce(error,'') LIKE 'DANE weekly 2018 native unit undeclared; exact archived workbook reviewed%%'
                   AND checked_at>=now()-interval '30 days'
                   AND EXISTS (SELECT 1 FROM official_source_review r
                     WHERE r.document_id=a.document_id AND r.parser_version=a.processor_version
                     AND r.source_locator='XLSX document-level native unit review'
                     AND r.record->'details'->>'original_sha256'=a.document_id))
          AND ((outdated AND status<>'pending') OR checked_at IS NULL OR checked_at<now()-interval '6 hours')
        ) SELECT url,kind,observed_on FROM candidates
          ORDER BY CASE WHEN exact_source_repair THEN 0 WHEN url=ANY(%s::text[]) THEN 1 ELSE 2 END,turn,
            CASE WHEN kind='coffee-pdf' THEN 0 WHEN kind='coffee' THEN 1
                 WHEN kind IN ('daily','city-pdf','city-zip','daily-zip') THEN 2
                 WHEN kind IN ('inputs','inputs-municipal','supply') THEN 4 ELSE 3 END,
            observed_on DESC NULLS LAST,checked_at ASC NULLS FIRST,url""",
        (
            expected_versions(),
            source_repairs,
            roots,
            str(today.year) + "|" + str(today.year - 1),
            today - timedelta(days=70),
            str(today.year) + "|" + str(today.year - 1),
            today.replace(month=1, day=1),
            # DANE revises this annual workbook in place, sometimes months
            # after its last ingested observation. Individual monthly leaves
            # must still use the recency cutoff below.
            rf"/anex-SIPSALeche-SerieHistoricaPrecios-({today.year}|{today.year - 1})\.xlsx?([?].*)?$",
            today - timedelta(days=70),
            today - timedelta(days=14),
            today - timedelta(days=14),
            roots,
        ),
    ).fetchall()


def current_dane_candidates(db, bogota_day, *, exclude_urls=(), limit=2):
    """At most two hourly source checks for registered recent DANE prices.

    A separate front lane gives mutable daily and city files time before the
    historical backlog. The Bogotá calendar bounds the window; a future URL,
    unrelated host, old reviewed asset or recent check cannot enter it.
    """
    from .current_dane_sources import HOURLY_SLOTS, PREFIXES, RECENT_DAYS, KINDS

    limit = max(0, min(int(limit), HOURLY_SLOTS))
    if not limit:
        return []
    # The newest city ZIP has its own first slot. A busy source index can
    # register a dozen recent annexes; rotating all of them oldest-first would
    # leave the primary market PDFs stale for most of a day. If this ZIP was
    # checked within an hour, the slot returns to the ordinary rotation.
    latest_city = db.execute('''SELECT url,kind,observed_on,
        (checked_at IS NULL OR checked_at<now()-interval '1 hour') AS due
        FROM ingestion_asset
      WHERE kind='city-zip' AND observed_on BETWEEN %s::date-%s AND %s::date
        AND url LIKE ANY(%s::text[]) AND url NOT LIKE '%%?%%'
        AND url NOT LIKE '%%#%%'
        AND status IN ('pending','complete','processed','archived','review','failed','awaiting-ocr')
        AND (status<>'failed' OR attempts<=3)
      ORDER BY observed_on DESC, CASE WHEN status='pending' THEN 0 ELSE 1 END,
        discovered_at DESC,url LIMIT 1''',
      (bogota_day, RECENT_DAYS, bogota_day,
       [prefix + '%' for prefix in PREFIXES])).fetchone()
    reserved = []
    if (latest_city is not None and latest_city[0] not in exclude_urls
            and latest_city[3]):
        reserved = [latest_city[:3]]
    remaining = limit - len(reserved)
    if not remaining:
        return reserved
    rotating = db.execute('''SELECT url,kind,observed_on FROM ingestion_asset
      WHERE kind=ANY(%s::text[]) AND observed_on BETWEEN %s::date-%s AND %s::date
        AND url LIKE ANY(%s::text[]) AND url NOT LIKE '%%?%%'
        AND url NOT LIKE '%%#%%' AND NOT (url=ANY(%s::text[]))
        AND status IN ('pending','complete','processed','archived','review','failed','awaiting-ocr')
        AND (status<>'failed' OR attempts<=3)
        AND (checked_at IS NULL OR checked_at<now()-interval '1 hour')
      ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END,
        checked_at ASC NULLS FIRST, observed_on DESC,url LIMIT %s''',
      (list(KINDS), bogota_day, RECENT_DAYS, bogota_day,
       [prefix + '%' for prefix in PREFIXES], list(exclude_urls) + [r[0] for r in reserved],
       remaining)).fetchall()
    return reserved + rotating


BACKFILL_ELIGIBLE_SQL = """WITH config AS (SELECT %s::jsonb AS versions), versions AS (
          SELECT a.*,a.processor_version IS DISTINCT FROM
            coalesce(c.versions->>('url:'||a.url),
              CASE WHEN a.kind='daily-pdf' AND a.url ~
                '^https://www[.]dane[.]gov[.]co/files/operaciones/SIPSA/bol-SIPSADiario-[0-9]{2}[a-z]{3}[0-9]{4}[.]pdf$'
                AND NOT (c.versions->'daily-pdf-generic-excluded' ? a.url)
                THEN c.versions->>'daily-pdf-generic' END,
              c.versions->>a.kind,'source-v1') AS outdated
          FROM ingestion_asset a CROSS JOIN config c
        ), eligible AS (
          SELECT * FROM versions a WHERE
            NOT (kind='coffee'
                 AND coalesce(error,'') LIKE 'FNC index replaced verified 404 URL:%%') AND
            NOT (url='https://esmis.nal.usda.gov/sites/default/release-files/4x51hj05x/xp68nh41n/pg15dd132/MH_FV221.PDF'
                 AND kind='international-usda-miami-flowers' AND status='review' AND NOT outdated
                 AND coalesce(error,'') LIKE 'USDA verified August 18 replacement: %%'
                 AND checked_at>=now()-interval '30 days') AND
            NOT (kind='dane-weekly-pdf' AND status='review' AND NOT outdated
                 AND document_id='c3192584b35f69b03e8ba93872f9807f04109631d87fa76fc4671d06c05f4a64'
                 AND coalesce(error,'') LIKE 'SourceDateMismatch: Weekly printed period conflicts with the dated source URL%%'
                 AND checked_at>=now()-interval '30 days') AND
            NOT (kind='monthly-pdf' AND status='review'
                 AND coalesce(error,'') LIKE 'DANE monthly index identifies nonprice press release: %%') AND
            NOT (kind='dane-weekly-xlsx' AND status='review' AND NOT outdated
                 AND coalesce(error,'') LIKE 'DANE weekly 2018 native unit undeclared; exact archived workbook reviewed%%'
                 AND checked_at>=now()-interval '30 days'
                 AND EXISTS (SELECT 1 FROM official_source_review r
                   WHERE r.document_id=a.document_id AND r.parser_version=a.processor_version
                   AND r.source_locator='XLSX document-level native unit review'
                   AND r.record->'details'->>'original_sha256'=a.document_id)) AND
            (status IN ('pending','failed') OR
             (outdated AND status IN ('complete','processed','archived','review','awaiting-ocr')) OR
             (status IN ('complete','processed','archived','review','awaiting-ocr')
              AND checked_at<now()-interval '30 days'))
            AND (checked_at IS NULL OR checked_at<now()-interval '6 hours' OR
                 (outdated AND status IN ('complete','processed','archived','review','awaiting-ocr','failed')))
        )"""


def backfill_candidates(db, limit):
    from .dane_weekly import RICE_MONTHLY_CONFLICT_URLS
    from .reviewed_weekly_feb2014 import PAIRS as FEB2014_PAIRS

    return db.execute(
        BACKFILL_ELIGIBLE_SQL + """, fair AS (
          SELECT *,row_number() OVER(PARTITION BY kind ORDER BY
            CASE WHEN kind='dane-weekly-xlsx' AND url=ANY(%s::text[]) AND outdated THEN -2 ELSE 0 END,
            CASE WHEN kind='dane-weekly-xlsx' AND url=ANY(%s::text[]) AND outdated THEN -1 ELSE 0 END,
            CASE WHEN outdated AND status IN ('failed','review','awaiting-ocr') THEN 0
                 WHEN status='pending' THEN 1 WHEN outdated THEN 2
                 WHEN status='failed' THEN 4 ELSE 3 END,
            CASE WHEN kind LIKE 'colombia-%%' OR kind LIKE 'international-%%' OR kind IN ('dane-weekly-xlsx','dane-weekly-pdf') THEN observed_on END DESC NULLS LAST,
            CASE WHEN kind LIKE 'colombia-%%' OR kind LIKE 'international-%%' OR kind IN ('dane-weekly-xlsx','dane-weekly-pdf') THEN discovered_at END DESC,
            coalesce(observed_on,'1900-01-01'),url) AS turn
          FROM eligible
        ) SELECT url,kind,observed_on FROM fair ORDER BY turn,
          CASE WHEN kind='city-zip' THEN 0 WHEN kind LIKE 'colombia-%%' THEN 1
               WHEN kind LIKE 'international-%%' THEN 2 ELSE 3 END,kind LIMIT %s""",
        (expected_versions(), sorted(FEB2014_PAIRS), sorted(RICE_MONTHLY_CONFLICT_URLS),
         max(1, min(int(limit), 1000))),
    ).fetchall()


def historical_candidates(db, limit=5):
    """One verified-eligibility winner per historical DANE family.

    Weekly PDF has a fixed slot while the six other families rotate hourly.
    All candidates still pass the exact backfill eligibility CTE.
    """
    limit = max(0, min(int(limit), 5))
    if not limit:
        return []
    return db.execute(
        BACKFILL_ELIGIBLE_SQL + """, historic AS (
          SELECT url,kind,observed_on,
            row_number() OVER (PARTITION BY kind ORDER BY
              CASE WHEN status='pending' AND checked_at IS NULL THEN 0
                   WHEN status='pending' THEN 1 ELSE 2 END,
              checked_at ASC NULLS FIRST,observed_on ASC NULLS LAST,url) AS turn
          FROM eligible
          WHERE kind IN ('dane-weekly-pdf','dane-weekly-xlsx','daily',
                         'daily-pdf','city-pdf','city-zip','monthly-pdf','inputs-pdf')
            AND observed_on IS NOT NULL
            AND status IN ('pending','failed')
            AND (checked_at IS NULL OR checked_at<now()-interval '6 hours')
        ), winners AS (
          SELECT url,kind,observed_on,
            CASE kind WHEN 'dane-weekly-xlsx' THEN 0
                      WHEN 'daily' THEN 1 WHEN 'daily-pdf' THEN 2
                      WHEN 'city-pdf' THEN 3 WHEN 'city-zip' THEN 4
                      WHEN 'monthly-pdf' THEN 5 WHEN 'inputs-pdf' THEN 6 ELSE -1 END AS family_index
          FROM historic WHERE turn=1
        ), clock AS (
          SELECT mod(floor(extract(epoch FROM now())/3600)::bigint,7)::int AS turn
        ) SELECT url,kind,observed_on FROM winners CROSS JOIN clock
          ORDER BY CASE WHEN kind='dane-weekly-pdf' THEN -1
                 ELSE mod(family_index-clock.turn+7,7) END,
            observed_on,url LIMIT %s""",
        (expected_versions(), limit),
    ).fetchall()


def recent_pending_daily_pdf_candidates(db, today, limit=2):
    """Bounded catch-up for registered daily PDFs that just left freshness.

    The ordinary daily window is fourteen days and historical scheduling
    starts with 2012. Keep one newest never-attempted gap and one due pending
    retry moving without displacing either existing lane. These are ordinary
    source fetches, subject to the run's host cooldown and parser validation.
    """
    limit = max(0, min(int(limit), 2))
    if not limit:
        return []
    return db.execute(
        """WITH eligible AS (
          SELECT url,kind,observed_on,checked_at,
            CASE WHEN checked_at IS NULL THEN 0 ELSE 1 END AS lane
          FROM ingestion_asset
          WHERE kind='daily-pdf' AND status='pending'
            AND observed_on>=%s::date-interval '90 days'
            AND observed_on<=%s::date-interval '14 days'
            AND (checked_at IS NULL OR checked_at<now()-interval '6 hours')
        ), ranked AS (
          SELECT *,row_number() OVER (PARTITION BY lane ORDER BY
            CASE WHEN lane=0 THEN observed_on END DESC NULLS LAST,
            CASE WHEN lane=1 THEN checked_at END ASC NULLS LAST,
            observed_on DESC,url) AS turn
          FROM eligible
        ) SELECT url,kind,observed_on FROM ranked WHERE turn=1
          ORDER BY lane LIMIT %s""",
        (today, today, limit),
    ).fetchall()


def supply_validation_retry(db):
    """Give one interrupted whole-workbook validation a full hourly window.

    Supply must validate the entire native source before publication checkpoints.
    Repeatedly appending it after current large input files can exhaust every run
    before that first checkpoint. Only a time-budget deferral earns this slot;
    malformed, reviewed or newly discovered sources keep the ordinary queue.
    """
    return db.execute(
        """SELECT url,kind,observed_on FROM ingestion_asset
        WHERE kind='supply' AND status='pending'
          AND error IN ('Supply native validation exceeded the run budget',
                        'Supply native validation deferred before starting')
          AND (checked_at IS NULL OR checked_at<now()-interval '6 hours')
        ORDER BY checked_at ASC NULLS FIRST,url LIMIT 1"""
    ).fetchall()


CITY_NEVER_SQL = """WITH eligible AS (
 SELECT url,kind,observed_on,extract(year FROM observed_on)::int AS source_year,
 row_number() OVER (PARTITION BY extract(year FROM observed_on)::int
                    ORDER BY observed_on,url) AS within_year
 FROM ingestion_asset
 WHERE kind='city-zip' AND status='pending' AND checked_at IS NULL
 AND observed_on IS NOT NULL
 AND observed_on <= (clock_timestamp() AT TIME ZONE 'America/Bogota')::date
 AND NOT (url=ANY(%s::text[]))
)
SELECT url,kind,observed_on,source_year,within_year FROM eligible
WHERE within_year<=6 ORDER BY source_year,within_year,observed_on,url"""

CITY_DUE_SQL = """SELECT url,kind,observed_on FROM ingestion_asset
WHERE kind='city-zip' AND status='pending' AND checked_at IS NOT NULL
AND checked_at<clock_timestamp()-interval '6 hours'
AND observed_on IS NOT NULL
AND observed_on <= (clock_timestamp() AT TIME ZONE 'America/Bogota')::date
AND NOT (url=ANY(%s::text[]))
ORDER BY checked_at,observed_on,url LIMIT 1"""

CITY_RECENT_SQL = """SELECT url,kind,observed_on FROM ingestion_asset
WHERE kind='city-zip' AND status='pending'
AND url LIKE 'https://www.dane.gov.co/%%'
AND observed_on >= %s::date
AND observed_on <= (clock_timestamp() AT TIME ZONE 'America/Bogota')::date
AND observed_on < (clock_timestamp() AT TIME ZONE 'America/Bogota')::date - %s::int
AND (checked_at IS NULL OR checked_at<clock_timestamp()-interval '6 hours')
AND NOT (url=ANY(%s::text[]))
ORDER BY observed_on,checked_at ASC NULLS FIRST,url LIMIT 1"""


def city_catchup_candidates(db, *, exclude_urls=(), rotation=None, limit=2,
                            recent_since=None):
    """At most six ordinary pending city ZIPs under the existing run cap.

    A year rotates by UTC hour; its oldest never-checked ZIP leads. A due
    pending retry is second. Remaining slots rotate across different years
    before taking a second or later row from a year.
    With recent_since, reserve one slot for the oldest missing recent DANE
    report. With two slots, the remaining slot alternates a rotating year and
    a due retry, so the reserved recent work cannot starve old pending work.
    A single available slot alternates recent and ordinary catch-up hours.
    No old complete/review/failed asset gets priority here; those still use
    the existing revision and repair eligibility routes.
    """
    limit = max(0, min(int(limit), 6))
    if not limit:
        return []
    rotation = (
        int(datetime.now(timezone.utc).timestamp() // 3600)
        if rotation is None else int(rotation)
    )
    excluded = set(exclude_urls)
    selected = []
    if recent_since is not None and (limit > 1 or rotation % 2 == 0):
        from .current_dane_sources import RECENT_DAYS

        recent = db.execute(CITY_RECENT_SQL,
                            (recent_since, RECENT_DAYS, sorted(excluded))).fetchone()
        if recent:
            selected.append(tuple(recent))
            excluded.add(recent[0])
    never = db.execute(CITY_NEVER_SQL, (sorted(excluded),)).fetchall()
    years = sorted({row[3] for row in never})
    due = db.execute(CITY_DUE_SQL, (sorted(excluded),)).fetchone()
    reserved_recent = bool(selected)
    split_rotation = (recent_since is not None and limit == 1) or (reserved_recent and limit == 2)
    year_rotation = rotation // 2 if split_rotation else rotation
    if reserved_recent and limit == 2 and rotation % 2 and due:
        selected.append(tuple(due))
        excluded.add(due[0])
    if len(selected) < limit and years:
        first_year = years[year_rotation % len(years)]
        first = next(row for row in never if row[3] == first_year and row[4] == 1)
        selected.append(tuple(first[:3]))
        excluded.add(first[0])
    if len(selected) < limit:
        if due and due[0] not in excluded:
            selected.append(tuple(due))
            excluded.add(due[0])
    if len(selected) < limit and years:
        ordered_years = years[year_rotation % len(years):] + years[:year_rotation % len(years)]
        by_year_and_rank = {(row[3], row[4]): row for row in never}
        for rank in range(1, 7):
            for year in ordered_years:
                row = by_year_and_rank.get((year, rank))
                if row is None or row[0] in excluded:
                    continue
                selected.append(tuple(row[:3]))
                excluded.add(row[0])
                if len(selected) == limit:
                    return selected
    return selected
