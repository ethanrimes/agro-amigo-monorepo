"""Materialized daily price matrices with cell-level source-quality reviews.

Unknown market labels remain absent. Date exceptions require a reviewed original
hash and independent official publication evidence, never neighboring columns.
"""

import hashlib
import io
import math
import re
from datetime import date, datetime

VERSION = "daily-units-v6"

# Populated only for exact authoritative originals with independent date evidence.
VERIFIED_DATE_RECOVERIES = {
    "10a85133075b7e2c334bf472bda70df5d99ccdaec6640594ee7ac494d283a316": {
        "archive_date": "2019-12-02",
        "observation_date": "2019-12-02",
        "printed_heading": "Lunes 02 de noviembre de 2019",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-diciembre-de-2019",
        "archive_label": "02 de Diciembre de 2019",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_02_2019.pdf",
        "corroborating_sha256": "96d6ff9a067d516b3a532572e1495511879ae248dafdfab171e28b39d0677185",
        "corroborating_locator": "PDF physical page 1 prints 2 de diciembre de 2019; multiple narrative prices agree with native workbook cells.",
        "corroborating_cells": [
            {"product": "Cebolla junca", "market": "Pasto, El Potrerillo", "xls_cell": "R9", "price_cop_per_kg": 489},
            {"product": "Cebolla junca", "market": "Cali, Cavasa", "xls_cell": "H9", "price_cop_per_kg": 1111},
            {"product": "Cebolla junca", "market": "Montería", "xls_cell": "P9", "price_cop_per_kg": 2146},
            {"product": "Arveja verde en vaina", "market": "Pasto, El Potrerillo", "xls_cell": "R7", "price_cop_per_kg": 2050},
            {"product": "Arveja verde en vaina", "market": "Villavicencio, CAV", "xls_cell": "AB7", "price_cop_per_kg": 3600},
            {"product": "Zanahoria", "market": "Pasto, El Potrerillo", "xls_cell": "R18", "price_cop_per_kg": 587},
        ],
    },
    "5f908d72f6b60fd3cf3f331ea2ae9434aa026d5561609b1fe4e085b7cad2ec85": {
        "archive_date": "2019-08-12",
        "observation_date": "2019-08-12",
        "printed_heading": "Lunes 12 de gosto de 2019",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-agosto-de-2019",
        "archive_label": "12 de Agosto de 2019 — Anexo",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_agosto_12_2019.pdf",
        "corroborating_sha256": "bed32e2c8fa86f5d29b9131049c3af027bef80815262ee5db329ad560418c25b",
        "corroborating_locator": "PDF physical page 1 prints 12 de agosto de 2019; Habichuela Manizales 1,020 COP/kg, Cali Cavasa 1,767 COP/kg, Arveja verde en vaina Medellin CMA 2,563 COP/kg agree with native workbook cells.",
        "corroborating_cells": [
            {"product": "Habichuela", "market": "Manizales", "xls_cell": "L12", "price_cop_per_kg": 1020},
            {"product": "Habichuela", "market": "Cali, Cavasa", "xls_cell": "H12", "price_cop_per_kg": 1767},
            {"product": "Arveja verde en vaina", "market": "Medellín, CMA", "xls_cell": "N7", "price_cop_per_kg": 2563},
        ],
    },
    "58541524d801feadbce7be1059f9e6d924c58b668785ab3023a2725d5114ac4d": {
        "archive_date": "2017-02-20",
        "observation_date": "2017-02-20",
        "printed_heading": "Lunes 20 de enero de 2017",
        "basis": "native_month_typo",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_20_2017.pdf",
        "corroborating_sha256": "87c4ef6e56d87e02a311432d27a4d0e11b296f4e5edfe842d0434fa29206d3a7",
        "corroborating_locator": "PDF physical page 1: Pimentón Cali Cavasa 2,425=H15; Cebolla cabezona blanca Cali Cavasa 1,604=H8; Cebolla junca Bogotá Corabastos 2,389=F9",
        "corroborating_cells": [
            {"product": "Pimentón", "market": "Cali, Cavasa", "xls_cell": "H15", "price_cop_per_kg": 2425},
            {"product": "Cebolla cabezona blanca", "market": "Cali, Cavasa", "xls_cell": "H8", "price_cop_per_kg": 1604},
            {"product": "Cebolla junca", "market": "Bogotá, Corabastos", "xls_cell": "F9", "price_cop_per_kg": 2389},
        ],
    },
    "dde84100bdbe8f0eb0521361d4724ce8481cd3ecd5032dfd64de0b82b1ad47fe": {
        "archive_date": "2016-09-05",
        "observation_date": "2016-09-05",
        "printed_heading": "Lunes 5 de 2016 de 2016",
        "basis": "native_month_omitted",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_septiembre_5_2016.pdf",
        "corroborating_sha256": "5ccb7c57c04dab61862a20e53695ae0c4e039945117789ad1c4692599c122b5f",
        "corroborating_locator": "PDF physical page 1 prints 5 de septiembre de 2016 and Habichuela market prices; XLS Boletín diario row 12 has the exact corresponding native price and variation cells",
        "corroborating_cells": [
            {"product": "Habichuela", "market": "Cali, Cavasa", "xls_row": 12, "price_col": "H", "change_col": "I", "price_cop_per_kg": 2450, "variation_percent": 78},
            {"product": "Habichuela", "market": "Cartagena, Bazurto", "xls_row": 12, "price_col": "J", "change_col": "K", "price_cop_per_kg": 2500, "variation_percent": 72},
            {"product": "Habichuela", "market": "Villavicencio, CAV", "xls_row": 12, "price_col": "AB", "change_col": "AC", "price_cop_per_kg": 1750, "variation_percent": 40},
        ],
    },
    "bbb69b2938848e95c9728a34c9204dd9fb19e720d54b05dd2f9b8289079a0f0f": {
        "archive_date": "2015-12-01",
        "observation_date": "2015-12-01",
        "printed_heading": "Martes 1 de dciembre de 2015",
        "basis": "native_month_typo",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_1_2015.pdf",
        "corroborating_sha256": "8504efb990294f3d77f092e4e1fb48b16a15be4dab43a1ec52020e8a0e653e7e",
        "corroborating_locator": "PDF page 1 date and Habichuela Armenia Mercar 1,080 COP/kg equal XLS native row 12 column B",
    },
    "fe66e1d1a39637d81bde11325ba60f8ef8c12a96fdf779f5c6ab7f3586d83e2c": {
        "archive_date": "2016-01-18",
        "observation_date": "2017-01-18",
        "printed_heading": "Miércoles 18 de enero de 2017",
        "basis": "mislinked_identical_original",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-2016",
        "archive_label": "Anexo - 18 de enero",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_18_2016.xls",
        "corroborating_sha256": "fe66e1d1a39637d81bde11325ba60f8ef8c12a96fdf779f5c6ab7f3586d83e2c",
        "corroborating_archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-2017",
        "corroborating_locator": "January 2017 archive links the identical original; its native heading and companion PDF page 1 explicitly date the observations 18 January 2017",
        "corroborating_pdf_sha256": "847b55c3f765e170d6039af6bdbcbdf32a924724c31b70a08d206758b7daaf29",
    },
    "7ff030995d78b89d20e1efd533bc4390985ddae7f5a70e236d39a74da253397f": {
        "archive_date": "2014-10-15",
        "observation_date": "2014-10-15",
        "printed_heading": "Miércoles 15 de septiembre de 2014",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-octubre-de-2014-1",
        "archive_label": "Anexo - 15 de octubre",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_octubre_15_2014.pdf",
        "corroborating_sha256": "194476e635512fb80819621a604c20ddc4d9645ecdbc51f8b1e08a8c453fed03",
        "corroborating_locator": "PDF page 1: October 15 date and matching cebolla junca, habichuela and tomate market prices",
    },
    "09bcafd697b554afe4bac3953bd5459140dcf356b95f70c42bf569beebac3043": {
        "archive_date": "2014-02-11",
        "observation_date": "2014-02-11",
        "printed_heading": "Martes 11 de febrera de 2014",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-febrero-de-2014-1",
        "archive_label": "Anexo - 11 de febrero",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_11_2014.pdf",
        "corroborating_sha256": "afde49f7efa5911624b0c9687a87d2679ad4971c25ab6b849454c6592462579a",
        "corroborating_locator": "PDF page 1: printed date and named-market prices",
    },
    "60f8375806bc73d3f64596bbb199248300151f978837d23e8fad68142fbbc57e": {
        "archive_date": "2013-11-13",
        "observation_date": "2013-11-13",
        "printed_heading": "Miércoles 13 de noviembre",
        "basis": "native_year_omitted",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-noviembre-de-2013-1",
        "archive_label": "Anexo - 13 de noviembre",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_noviembre_13_2013.pdf",
        "corroborating_sha256": "710cffdcb2bbf0bd8efc7b71eedb72b07ca26d4d08fdd7f82f4c6c17ab9ed9bc",
        "corroborating_locator": "PDF page 1: printed date and named-market prices",
    },
    "ba1bcc4bca12a82b9bcc25d8005a8a30c18656c4404efb6a4bfbe5729903062f": {
        "archive_date": "2013-09-26",
        "observation_date": "2013-09-26",
        "printed_heading": "Jueves 26 de septiembe de 2013",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-septiembre-de-2013-1",
        "archive_label": "Anexo - 26 de septiembre",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_septiembre_26_2013.pdf",
        "corroborating_sha256": "f4a11b500fa47ae7f57972750cb4de3f4efcb56ecde1f0f69d16d09613c80c22",
        "corroborating_locator": "PDF page 1: printed date and named-market prices",
    },
    "3fdf93edbe09ab0319f411ffd1ffd93d80b340b0dbaae27ce4c2b0c61b670d3a": {
        "archive_date": "2013-02-11",
        "observation_date": "2013-02-11",
        "printed_heading": "Lunes 11 de enero de 2013",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-febrero-de-2013-1",
        "archive_label": "Anexo - 11 de febrero",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_feb_11_2013.pdf",
        "corroborating_sha256": "d1fc15f9581bb74637a96017f5ef8313e17599b06233dac877aef2c00624bfc8",
        "corroborating_locator": "PDF page 1: printed date and named-market prices",
        "price_disagreements": [
            {
                "product_name": "Zanahoria",
                "market_name": "Cartagena, Bazurto",
                "workbook_price": 1292,
                "companion_pdf_price": 1229,
                "policy": "Preserve literal workbook price; companion prose is not a replacement.",
            }
        ],
    },
    "ad0c02b5ef2edf4fbacdb6b9ce1537d03260236e7dd19dbc52aa2b7048b35ada": {
        "archive_date": "2013-12-06",
        "observation_date": "2013-12-06",
        "printed_heading": "Viernes 6 de noviembre de 2013",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-diciembre-de-2013",
        "archive_label": "Anexo - 6 de diciembre",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_6_2013.pdf",
        "corroborating_sha256": "58ad7142b079af8a190c7a51d36c4006e674c99d84701cf4a649a97496ae4bcc",
        "corroborating_locator": "PDF page 1: printed date and named-market prices",
    },
    "cf3a0c3e001b5cc867ac43d609afb9aafe9a51eba4c4d638315febe6978d8445": {
        "archive_date": "2012-12-05",
        "observation_date": "2012-12-06",
        "printed_heading": "Jueves 6 de diciembre de 2012",
        "basis": "mislinked_identical_original",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-diciembre-de-2012-1",
        "archive_label": "Anexo - 5 de diciembre",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_anexo_dic_6_2012.xls",
        "corroborating_sha256": "cf3a0c3e001b5cc867ac43d609afb9aafe9a51eba4c4d638315febe6978d8445",
        "corroborating_locator": "All native cells and the official archive dated link",
    },
    "302aa6336d7b53016c2afcf79bdc03499637663effb575341606e1dbb9ebb3f9": {
        "archive_date": "2013-07-12",
        "observation_date": "2013-07-15",
        "printed_heading": "Lunes 15 de julio de 2013",
        "basis": "mislinked_identical_original",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-julio-de-2013-1",
        "archive_label": "Anexo - 12 de julio",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_julio_15_2013.xls",
        "corroborating_sha256": "302aa6336d7b53016c2afcf79bdc03499637663effb575341606e1dbb9ebb3f9",
        "corroborating_locator": "All native cells and the official archive dated link",
    },
    "7e3dd859361ac543fe71f740b9898117ebcefc6b69a9ae2815a94155bc1f7088": {
        "archive_date": "2013-05-20",
        "observation_date": "2013-05-21",
        "printed_heading": "Martes 21 de mayo de 2013",
        "basis": "mislinked_identical_original",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-mayo-de-2013-1",
        "archive_label": "Anexo - 20 de mayo",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_mayo_21_2013.xls",
        "corroborating_sha256": "7e3dd859361ac543fe71f740b9898117ebcefc6b69a9ae2815a94155bc1f7088",
        "corroborating_locator": "All native cells and the official archive dated link",
    },
    "82cc122be75103f787e1e84d92ffee9da227e693c22dfcb7190c8e8430aac3fc": {
        "archive_date": "2014-06-11",
        "observation_date": "2014-06-10",
        "printed_heading": "Martes 10 de junio de 2014",
        "basis": "mislinked_identical_native_cells",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-junio-de-2014-1",
        "archive_label": "Anexo - 11 de junio",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_junio_10_2014.xls",
        "corroborating_sha256": "eb968f3e7bdb8ee9f0e75c06d1fa985fb523039faaf88ec72847df07b127e6ef",
        "corroborating_locator": "All native cells and the official archive dated link",
    },
    # Eight exact 2020 daily workbooks with a native 2019 year typo. Each is
    # bound to its archive row and a visible companion-PDF date plus price witnesses.
    '73e9e87255acfdae1c851920d084f00ed90d21baf754f848c88da6112971fe72': {'archive_date': '2020-01-07',
     'observation_date': '2020-01-07',
     'printed_heading': 'Martes 7 de enero de 2019',
     'basis': 'native_year_typo',
     'source_url_required': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_07_2020.xlsx',
     'archive_url': 'https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-de-2020',
     'archive_label': '07 de enero de 2020',
     'corroborating_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_07_2020.pdf',
     'corroborating_sha256': '2bba2c3ed056b5d2624af824c2d845aadbb16cadb31ab29e3ca26475061abaec',
     'corroborating_locator': 'Visible upper-right PDF page 1 date is 7 de enero de 2020; a hidden stationery '
                              'text layer says 28 de agosto de 2018 and is not the visible heading. Weekday '
                              'martes agrees with 2020-01-07. Independent exact price and variation witnesses '
                              'span the printed pages.',
     'corroborating_cells': [{'product': 'Chócolo mazorca',
                              'market': 'Bogotá, Corabastos',
                              'price_cell': 'D10',
                              'variation_cell': 'E10',
                              'price_cop_per_kg': 1050,
                              'variation_percent': -40.0,
                              'pdf_page': 1,
                              'pdf_witness': 'Bogotá chócolo mazorca: 40,00% decrease; $1.050/kg'},
                             {'product': 'Tomate*',
                              'market': 'Ibagué, La 21',
                              'price_cell': 'L17',
                              'variation_cell': 'M17',
                              'price_cop_per_kg': 770,
                              'variation_percent': -23.0,
                              'pdf_page': 1,
                              'pdf_witness': 'Tomate in Ibagué: 23,00% decrease; $770/kg'},
                             {'product': 'Habichuela',
                              'market': 'Bucaramanga, Centroabastos',
                              'price_cell': 'F12',
                              'variation_cell': 'G12',
                              'price_cop_per_kg': 2500,
                              'variation_percent': 42.86,
                              'pdf_page': 1,
                              'pdf_witness': 'Bucaramanga habichuela: 42,86% increase; $2.500/kg'},
                             {'product': 'Habichuela',
                              'market': 'Pereira, La 41',
                              'price_cell': 'V12',
                              'variation_cell': 'W12',
                              'price_cop_per_kg': 1547,
                              'variation_percent': 20.83,
                              'pdf_page': 1,
                              'pdf_witness': 'Pereira La 41 habichuela: 20,83% increase; $1.547/kg'},
                             {'product': 'Mango tommy',
                              'market': 'Cali, Santa Helena',
                              'price_cell': 'H29',
                              'variation_cell': 'I29',
                              'price_cop_per_kg': 1427,
                              'variation_percent': 33.75,
                              'pdf_page': 2,
                              'pdf_witness': 'Cali Santa Helena mango Tommy: 33,75% increase; $1.427/kg'},
                             {'product': 'Mango tommy',
                              'market': 'Neiva, Surabastos',
                              'price_cell': 'T29',
                              'variation_cell': 'U29',
                              'price_cop_per_kg': 1300,
                              'variation_percent': 22.64,
                              'pdf_page': 2,
                              'pdf_witness': 'Neiva Surabastos mango Tommy: 22,64% increase; $1.300/kg'},
                             {'product': 'Mango tommy',
                              'market': 'Pereira, La 41',
                              'price_cell': 'V29',
                              'variation_cell': 'W29',
                              'price_cop_per_kg': 1767,
                              'variation_percent': 17.78,
                              'pdf_page': 2,
                              'pdf_witness': 'Pereira La 41 mango Tommy: 17,78% increase; $1.767/kg'},
                             {'product': 'Naranja*',
                              'market': 'Manizales',
                              'price_cell': 'N33',
                              'variation_cell': 'O33',
                              'price_cop_per_kg': 967,
                              'variation_percent': 16.0,
                              'pdf_page': 2,
                              'pdf_witness': 'Manizales orange: 16,00% increase; $967/kg'},
                             {'product': 'Limón Tahití',
                              'market': 'Pereira, La 41',
                              'price_cell': 'V26',
                              'variation_cell': 'W26',
                              'price_cop_per_kg': 2167,
                              'variation_percent': 41.3,
                              'pdf_page': 2,
                              'pdf_witness': 'Pereira La 41 Tahiti lime: 41,30% increase; $2.167/kg'},
                             {'product': 'Papa  criolla',
                              'market': 'Bucaramanga, Centroabastos',
                              'price_cell': 'F39',
                              'variation_cell': 'G39',
                              'price_cop_per_kg': 950,
                              'variation_percent': -40.63,
                              'pdf_page': 3,
                              'pdf_witness': 'Bucaramanga papa criolla: 40,63% decrease; $950/kg'}],
     'excluded_disagreements': [{'product': 'Pepino cohombro',
                                 'market': 'Neiva, Surabastos',
                                 'xls_price_cell': 'T14',
                                 'xls_variation_cell': 'U14',
                                 'xls_price_cop_per_kg': 1120,
                                 'xls_variation_percent': -25.33,
                                 'pdf_page': 1,
                                 'pdf_variation_percent': -25.53,
                                 'policy': 'Not used as a corroborating witness; preserve workbook variation '
                                           'literally.'}]},
    '74f03719c5227c25c219b4b7475740b0382e61b911d025aeb5f13d71abaa81a1': {'archive_date': '2020-01-08',
     'observation_date': '2020-01-08',
     'printed_heading': 'Miércoles 8 de enero de 2019',
     'basis': 'native_year_typo',
     'source_url_required': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_08_2020.xlsx',
     'archive_url': 'https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-de-2020',
     'archive_label': '08 de enero de 2020',
     'corroborating_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_08_2020.pdf',
     'corroborating_sha256': 'c053303f5068d234c5c9b9b3048621b305ebe4861f046055be03db8a5a8e024e',
     'corroborating_locator': 'Visible upper-right PDF page 1 date is 8 de enero de 2020; a hidden stationery '
                              'text layer says 28 de agosto de 2018 and is not the visible heading. Weekday '
                              'miércoles agrees with 2020-01-08. Independent exact price and variation witnesses '
                              'span the printed pages.',
     'corroborating_cells': [{'product': 'Pepino cohombro',
                              'market': 'Cartagena, Bazurto',
                              'price_cell': 'F14',
                              'variation_cell': 'G14',
                              'price_cop_per_kg': 840,
                              'variation_percent': -31.15,
                              'pdf_page': 1,
                              'pdf_witness': 'Cartagena Bazurto pepino: 31,15% decrease; $840/kg'},
                             {'product': 'Pepino cohombro',
                              'market': 'Popayán',
                              'price_cell': 'N14',
                              'variation_cell': 'O14',
                              'price_cop_per_kg': 615,
                              'variation_percent': -20.0,
                              'pdf_page': 1,
                              'pdf_witness': 'Popayán pepino: 20,00% decrease; $615/kg'},
                             {'product': 'Pepino cohombro',
                              'market': 'Sincelejo',
                              'price_cell': 'R14',
                              'variation_cell': 'S14',
                              'price_cop_per_kg': 500,
                              'variation_percent': -23.08,
                              'pdf_page': 1,
                              'pdf_witness': 'Sincelejo pepino: 23,08% decrease; $500/kg'},
                             {'product': 'Zanahoria',
                              'market': 'Medellín, CMA',
                              'price_cell': 'H18',
                              'variation_cell': 'I18',
                              'price_cop_per_kg': 569,
                              'variation_percent': -14.58,
                              'pdf_page': 1,
                              'pdf_witness': 'Medellín CMA carrot: 14,58% decrease; $569/kg'},
                             {'product': 'Zanahoria',
                              'market': 'Valledupar',
                              'price_cell': 'T18',
                              'variation_cell': 'U18',
                              'price_cop_per_kg': 1375,
                              'variation_percent': -12.0,
                              'pdf_page': 1,
                              'pdf_witness': 'Valledupar carrot: 12,00% decrease; $1.375/kg'},
                             {'product': 'Cebolla junca',
                              'market': 'Bogotá, Corabastos',
                              'price_cell': 'D9',
                              'variation_cell': 'E9',
                              'price_cop_per_kg': 1250,
                              'variation_percent': -16.67,
                              'pdf_page': 1,
                              'pdf_witness': 'Bogotá Corabastos spring onion: 16,67% decrease; $1.250/kg'},
                             {'product': 'Mora de Castilla',
                              'market': 'Medellín, CMA',
                              'price_cell': 'H32',
                              'variation_cell': 'I32',
                              'price_cop_per_kg': 3050,
                              'variation_percent': 71.83,
                              'pdf_page': 2,
                              'pdf_witness': 'Medellín CMA mora: 71,83% increase; $3.050/kg'},
                             {'product': 'Mora de Castilla',
                              'market': 'Montería',
                              'price_cell': 'J32',
                              'variation_cell': 'K32',
                              'price_cop_per_kg': 2875,
                              'variation_percent': 32.69,
                              'pdf_page': 2,
                              'pdf_witness': 'Montería mora: 32,69% increase; $2.875/kg'},
                             {'product': 'Limón común',
                              'market': 'Pereira, Mercasa',
                              'price_cell': 'L25',
                              'variation_cell': 'M25',
                              'price_cop_per_kg': 2133,
                              'variation_percent': 28.0,
                              'pdf_page': 2,
                              'pdf_witness': 'Pereira Mercasa common lime: 28,00% increase; $2.133/kg'},
                             {'product': 'Limón común',
                              'market': 'Villavicencio, CAV',
                              'price_cell': 'V25',
                              'variation_cell': 'W25',
                              'price_cop_per_kg': 3250,
                              'variation_percent': 23.81,
                              'pdf_page': 2,
                              'pdf_witness': 'Villavicencio CAV common lime: 23,81% increase; $3.250/kg'},
                             {'product': 'Naranja*',
                              'market': 'Montería',
                              'price_cell': 'J33',
                              'variation_cell': 'K33',
                              'price_cop_per_kg': 1000,
                              'variation_percent': 57.48,
                              'pdf_page': 2,
                              'pdf_witness': 'Montería orange: 57,48% increase; $1.000/kg'},
                             {'product': 'Naranja*',
                              'market': 'Pereira, Mercasa',
                              'price_cell': 'L33',
                              'variation_cell': 'M33',
                              'price_cop_per_kg': 1100,
                              'variation_percent': 50.0,
                              'pdf_page': 2,
                              'pdf_witness': 'Pereira Mercasa orange: 50,00% increase; $1.100/kg'}]},
    'fe7ca4b678001889d58d945d2098a88877e53e35c77c74bbda0af6ea2123b7a3': {'archive_date': '2020-01-09',
     'observation_date': '2020-01-09',
     'printed_heading': 'Jueves 09 de enero de 2019',
     'basis': 'native_year_typo',
     'source_url_required': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_09_2020.xlsx',
     'archive_url': 'https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-de-2020',
     'archive_label': '09 de enero de 2020',
     'corroborating_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_09_2020.pdf',
     'corroborating_sha256': '36c9b840561fb2e717a3b3164728a918a3c9449a607f02f450acee412e191aa0',
     'corroborating_locator': 'Visible upper-right physical PDF page 1 date is 9 de enero de 2020; weekday '
                              'agrees with that date. Multiple narrative price and variation witnesses agree '
                              'exactly with the corresponding workbook market/product cells.',
     'corroborating_cells': [{'product': 'Arveja verde en vaina',
                              'market': 'Armenia, Mercar',
                              'price_cell': 'B7',
                              'variation_cell': 'C7',
                              'price_cop_per_kg': 2347,
                              'variation_percent': -15.38,
                              'pdf_page': 1,
                              'pdf_witness': 'Armenia arveja: 15,38% decrease; $2.347/kg'},
                             {'product': 'Arveja verde en vaina',
                              'market': 'Cúcuta, Cenabastos',
                              'price_cell': 'J7',
                              'variation_cell': 'K7',
                              'price_cop_per_kg': 2500,
                              'variation_percent': -35.48,
                              'pdf_page': 1,
                              'pdf_witness': 'Cúcuta arveja: 35,48% decrease; $2.500/kg'},
                             {'product': 'Cebolla junca',
                              'market': 'Bogotá, Corabastos',
                              'price_cell': 'D9',
                              'variation_cell': 'E9',
                              'price_cop_per_kg': 1083,
                              'variation_percent': -13.33,
                              'pdf_page': 1,
                              'pdf_witness': 'Bogotá onion: 13,33% decrease; $1.083/kg'}]},
    '4632f2426dda197ff7115c7801e28bfbf8eebcf012b6343e656ac1bfdff1e538': {'archive_date': '2020-01-10',
     'observation_date': '2020-01-10',
     'printed_heading': 'Viernes 10 de enero de 2019',
     'basis': 'native_year_typo',
     'source_url_required': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_10_2020.xlsx',
     'archive_url': 'https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-de-2020',
     'archive_label': '10 de enero de 2020',
     'corroborating_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_10_2020.pdf',
     'corroborating_sha256': 'f3f6f2acb3033464a12d4c86a8f8e826be5ca5f4a9646f3b61c330ce24b06b2f',
     'corroborating_locator': 'Visible upper-right physical PDF page 1 date is 10 de enero de 2020; weekday '
                              'agrees with that date. Multiple narrative price and variation witnesses agree '
                              'exactly with the corresponding workbook market/product cells.',
     'corroborating_cells': [{'product': 'Arveja verde en vaina',
                              'market': 'Neiva, Surabastos',
                              'price_cell': 'R7',
                              'variation_cell': 'S7',
                              'price_cop_per_kg': 2000,
                              'variation_percent': -23.08,
                              'pdf_page': 1,
                              'pdf_witness': 'Neiva arveja: 23,08% decrease; $2.000/kg'},
                             {'product': 'Pepino cohombro',
                              'market': 'Neiva, Surabastos',
                              'price_cell': 'R14',
                              'variation_cell': 'S14',
                              'price_cop_per_kg': 760,
                              'variation_percent': -33.33,
                              'pdf_page': 1,
                              'pdf_witness': 'Neiva cucumber: 33,33% decrease; $760/kg'},
                             {'product': 'Remolacha',
                              'market': 'Montería',
                              'price_cell': 'P16',
                              'variation_cell': 'Q16',
                              'price_cop_per_kg': 1000,
                              'variation_percent': -13.04,
                              'pdf_page': 1,
                              'pdf_witness': 'Montería beet: 13,04% decrease; $1.000/kg'}]},
    'eca65a7f770f62021b338f94aae46d96f6421ee5d2337f1db93de013a8c06d2b': {'archive_date': '2020-01-13',
     'observation_date': '2020-01-13',
     'printed_heading': 'Lunes 13 de enero de 2019',
     'basis': 'native_year_typo',
     'source_url_required': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_13_2020.xlsx',
     'archive_url': 'https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-de-2020',
     'archive_label': '13 de enero de 2020',
     'corroborating_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_13_2020.pdf',
     'corroborating_sha256': '1f4a8e9af7aafd51508eae906853a4c1d3d13061d5df7dbaf5f2af63ed6e5669',
     'corroborating_locator': 'Visible upper-right physical PDF page 1 date is 13 de enero de 2020; weekday '
                              'agrees with that date. Multiple narrative price and variation witnesses agree '
                              'exactly with the corresponding workbook market/product cells.',
     'corroborating_cells': [{'product': 'Habichuela',
                              'market': 'Manizales',
                              'price_cell': 'L12',
                              'variation_cell': 'M12',
                              'price_cop_per_kg': 3200,
                              'variation_percent': 135.29,
                              'pdf_page': 1,
                              'pdf_witness': 'Manizales green bean: 135,29% increase; $3.200/kg'},
                             {'product': 'Habichuela',
                              'market': 'Armenia, Mercar',
                              'price_cell': 'B12',
                              'variation_cell': 'C12',
                              'price_cop_per_kg': 2027,
                              'variation_percent': 40.74,
                              'pdf_page': 1,
                              'pdf_witness': 'Armenia green bean: 40,74% increase; $2.027/kg'},
                             {'product': 'Habichuela',
                              'market': 'Valledupar',
                              'price_cell': 'Z12',
                              'variation_cell': 'AA12',
                              'price_cop_per_kg': 2625,
                              'variation_percent': 16.67,
                              'pdf_page': 1,
                              'pdf_witness': 'Valledupar green bean: 16,67% increase; $2.625/kg'},
                             {'product': 'Tomate*',
                              'market': 'Manizales',
                              'price_cell': 'L17',
                              'variation_cell': 'M17',
                              'price_cop_per_kg': 2250,
                              'variation_percent': 50.0,
                              'pdf_page': 1,
                              'pdf_witness': 'Manizales tomato: 50,00% increase; $2.250/kg'},
                             {'product': 'Tomate*',
                              'market': 'Valledupar',
                              'price_cell': 'Z17',
                              'variation_cell': 'AA17',
                              'price_cop_per_kg': 1300,
                              'variation_percent': 44.44,
                              'pdf_page': 1,
                              'pdf_witness': 'Valledupar tomato: 44,44% increase; $1.300/kg'}]},
    '872320bb98111d27365140203675f28bfbaf8856d437d977aee87de53ddfd5fb': {
        'archive_date': '2020-01-14', 'observation_date': '2020-01-14',
        'printed_heading': 'Martes 14 de enero de 2019', 'basis': 'native_year_typo',
        'source_url_required': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_14_2020.xlsx',
        'archive_url': 'https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-de-2020',
        'archive_label': '14 de enero de 2020',
        'corroborating_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_14_2020.pdf',
        'corroborating_sha256': '15bfd0fd1c6baebb34776f2841f7b95b98292f6b2fb2499ddcffe3e1e3539bc5',
        'corroborating_locator': 'Official January archive links the exact workbook on 14 January 2020. The companion PDF visibly prints 14 January 2020 on page 1; root physical review matched all seven price/variation witnesses to the XLS cells (7/7).',
        'corroborating_cells': [
            {'product':'Habichuela','market':'Ibagué, La 21','price_cell':'L12','variation_cell':'M12','price_cop_per_kg':2340,'variation_percent':82.81,'pdf_page':1},
            {'product':'Habichuela','market':'Cúcuta, Cenabastos','price_cell':'J12','variation_cell':'K12','price_cop_per_kg':3469,'variation_percent':85,'pdf_page':1},
            {'product':'Habichuela','market':'Pereira, La 41','price_cell':'R12','variation_cell':'S12','price_cop_per_kg':2260,'variation_percent':66.18,'pdf_page':1},
            {'product':'Tomate*','market':'Pereira, La 41','price_cell':'R17','variation_cell':'S17','price_cop_per_kg':2333,'variation_percent':55.56,'pdf_page':1},
            {'product':'Tomate*','market':'Bucaramanga, Centroabastos','price_cell':'F17','variation_cell':'G17','price_cop_per_kg':1909,'variation_percent':47.37,'pdf_page':1},
            {'product':'Cebolla junca','market':'Cali, Santa Helena','price_cell':'H9','variation_cell':'I9','price_cop_per_kg':1600,'variation_percent':17.39,'pdf_page':1},
            {'product':'Lechuga batavia','market':'Neiva, Surabastos','price_cell':'P13','variation_cell':'Q13','price_cop_per_kg':1440,'variation_percent':-18.18,'pdf_page':1},
        ]},
    'd0eea326eb44186c3ac0be8796da460897d9b78cee3f5f885784cc42d2353219': {
        'archive_date': '2020-01-15', 'observation_date': '2020-01-15',
        'printed_heading': 'Miércoles 15 de enero de 2019', 'basis': 'native_year_typo',
        'source_url_required': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_15_2020.xlsx',
        'archive_url': 'https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-de-2020',
        'archive_label': '15 de enero de 2020',
        'corroborating_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_15_2020.pdf',
        'corroborating_sha256': '6e9bbe3a02eb5fb27ae9692df8bb9d94bc6499e04f889a48219a624519ab08c9',
        'corroborating_locator': 'Official January archive links the exact workbook on 15 January 2020. The companion PDF visibly prints 15 January 2020 on page 1; root physical review matched all nine price/variation witnesses to the XLS cells (9/9).',
        'corroborating_cells': [
            {'product':'Habichuela','market':'Popayán','price_cell':'N12','variation_cell':'O12','price_cop_per_kg':2760,'variation_percent':40.82,'pdf_page':1},
            {'product':'Habichuela','market':'Bogotá, Corabastos','price_cell':'D12','variation_cell':'E12','price_cop_per_kg':2333,'variation_percent':12,'pdf_page':1},
            {'product':'Zanahoria','market':'Montería','price_cell':'J18','variation_cell':'K18','price_cop_per_kg':1206,'variation_percent':23.3,'pdf_page':1},
            {'product':'Cebolla cabezona blanca','market':'Montería','price_cell':'J8','variation_cell':'K8','price_cop_per_kg':990,'variation_percent':15.79,'pdf_page':1},
            {'product':'Tomate*','market':'Villavicencio, CAV','price_cell':'V17','variation_cell':'W17','price_cop_per_kg':2288,'variation_percent':12.62,'pdf_page':1},
            {'product':'Pepino cohombro','market':'Villavicencio, CAV','price_cell':'V14','variation_cell':'W14','price_cop_per_kg':1075,'variation_percent':22.86,'pdf_page':1},
            {'product':'Pepino cohombro','market':'Montería','price_cell':'J14','variation_cell':'K14','price_cop_per_kg':768,'variation_percent':10.83,'pdf_page':1},
            {'product':'Pimentón','market':'Bogotá, Corabastos','price_cell':'D15','variation_cell':'E15','price_cop_per_kg':2100,'variation_percent':-12.5,'pdf_page':1},
            {'product':'Pimentón','market':'Villavicencio, CAV','price_cell':'V15','variation_cell':'W15','price_cop_per_kg':1875,'variation_percent':-16.28,'pdf_page':1},
        ]},
    '83885449eb25388a124efeed3fa7e642ce487cbd68a11051e6daba3ee460f787': {
        'archive_date': '2020-01-16', 'observation_date': '2020-01-16',
        'printed_heading': 'Jueves 16 de enero de 2019', 'basis': 'native_year_typo',
        'source_url_required': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_16_2020.xlsx',
        'archive_url': 'https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-de-2020',
        'archive_label': '16 de enero de 2020',
        'corroborating_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_16_2020.pdf',
        'corroborating_sha256': 'ca08164318e52ef85ad9cca27010e27f8d6ac2e004f12c91f44d3d45b2b26270',
        'corroborating_locator': 'Official January archive links the exact workbook on 16 January 2020. The companion PDF visibly prints 16 January 2020 on page 1; root physical review matched all seven price/variation witnesses to the XLS cells (7/7).',
        'corroborating_cells': [
            {'product':'Remolacha','market':'Cali, Cavasa','price_cell':'H16','variation_cell':'I16','price_cop_per_kg':691,'variation_percent':13.71,'pdf_page':1},
            {'product':'Remolacha','market':'Santa Marta','price_cell':'X16','variation_cell':'Y16','price_cop_per_kg':1000,'variation_percent':27.66,'pdf_page':1},
            {'product':'Remolacha','market':'Bucaramanga, Centroabastos','price_cell':'F16','variation_cell':'G16','price_cop_per_kg':850,'variation_percent':13.33,'pdf_page':1},
            {'product':'Pepino cohombro','market':'Santa Marta','price_cell':'X14','variation_cell':'Y14','price_cop_per_kg':1200,'variation_percent':33.33,'pdf_page':1},
            {'product':'Pepino cohombro','market':'Cúcuta, Cenabastos','price_cell':'J14','variation_cell':'K14','price_cop_per_kg':700,'variation_percent':12,'pdf_page':1},
            {'product':'Arveja verde en vaina','market':'Cali, Cavasa','price_cell':'H7','variation_cell':'I7','price_cop_per_kg':2683,'variation_percent':30.89,'pdf_page':1},
            {'product':'Pimentón','market':'Manizales','price_cell':'L15','variation_cell':'M15','price_cop_per_kg':1350,'variation_percent':-36.47,'pdf_page':1},
        ]},
    'c8d59b0c713dcf74d256f9d2ea49c1f73170fbf9f9770138cf3a335a64e2b9a6': {
        'archive_date': '2020-02-03', 'observation_date': '2020-02-03',
        'printed_heading': 'Lunes 3 de febrero de 2019', 'basis': 'native_year_typo',
        'source_url_required': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_03_2020.xlsx',
        'archive_url': 'https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-febrero-de-2020',
        'archive_label': '03 de febrero de 2020',
        'corroborating_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_03_2020.pdf',
        'corroborating_sha256': '22063f57fe4146f6c7685cd496a9d5a0663d0b6d4c290ff4623b40bb5c991be4',
        'corroborating_locator': 'Official February archive links this exact workbook on 03 February 2020. Companion PDF page 1 visibly prints 3 de febrero de 2020 and VERDURAS Y HORTALIZAS; three Habichuela price and variation witnesses match the native workbook.',
        'corroborating_cells': [
            {'product':'Habichuela','market':'Pereira, Mercasa','price_cell':'T12','variation_cell':'U12','price_cop_per_kg':3900,'variation_percent':98.98,'pdf_page':1},
            {'product':'Habichuela','market':'Barranquilla','price_cell':'D12','variation_cell':'E12','price_cop_per_kg':2925,'variation_percent':71.43,'pdf_page':1},
            {'product':'Habichuela','market':'Armenia, Mercar','price_cell':'B12','variation_cell':'C12','price_cop_per_kg':2453,'variation_percent':37.31,'pdf_page':1},
        ],
    },
}


def _publication_day(data, rows, expected_day, source_url=None):
    from .worker import SourceDateMismatch, clean, date_from_text

    headings = [clean(value) for row in rows[:4] for value in row if clean(value)]
    typed = {
        value.date() if isinstance(value, datetime) else value
        for row in rows[:4]
        for value in row
        if isinstance(value, (date, datetime))
    }
    if len(typed) > 1:
        raise SourceDateMismatch("Conflicting typed daily publication dates")
    day = next(iter(typed), None) or date_from_text(" ".join(headings))
    evidence = VERIFIED_DATE_RECOVERIES.get(hashlib.sha256(data).hexdigest())
    required_url = evidence.get("source_url_required") if evidence else None
    if required_url and source_url != required_url:
        raise SourceDateMismatch("Reviewed daily source URL no longer agrees")
    # A mislinked original can also be served by its correctly dated link.
    # Accept that counterpart only when its native date independently agrees;
    # heading-typo exceptions still belong solely to their reviewed archive date.
    if (
        evidence
        and evidence["archive_date"] != expected_day.isoformat()
        and not (
            evidence["basis"].startswith("mislinked_identical_")
            and evidence["observation_date"] == expected_day.isoformat()
            and day == expected_day
        )
    ):
        raise SourceDateMismatch("Reviewed daily original is linked to a different archive date")
    if day == expected_day:
        return day, None, headings
    if evidence:
        if evidence["printed_heading"] not in headings:
            raise SourceDateMismatch("Reviewed daily date heading no longer agrees")
        return date.fromisoformat(evidence["observation_date"]), evidence, headings
    if day is None:
        raise ValueError("Daily workbook has no verifiable publication date")
    raise SourceDateMismatch(
        f"Daily link date {expected_day} differs from workbook {day}"
    )


def _number_formats(data):
    """Native variation formats keyed by one-based sheet/row/column."""
    if data[:2] == b"PK":
        import openpyxl

        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            return {
                (sheet.title, cell.row, cell.column): cell.number_format
                for sheet in book
                for row in sheet
                for cell in row
                if cell.value is not None
            }
        finally:
            book.close()
    import xlrd

    book = xlrd.open_workbook(file_contents=data, formatting_info=True)
    try:
        return {
            (sheet.name, row + 1, col + 1): book.format_map[
                book.xf_list[sheet.cell_xf_index(row, col)].format_key
            ].format_str
            for sheet in book.sheets()
            for row in range(sheet.nrows)
            for col in range(sheet.ncols)
            if sheet.cell_value(row, col) != ""
        }
    finally:
        book.release_resources()


def percentage_change(raw, number_format, *, ocr_printed_percent=False):
    """Convert native numeric fractions only when Excel actually displays %."""
    finite = (
        isinstance(raw, (int, float))
        and not isinstance(raw, bool)
        and math.isfinite(raw)
    )
    literal = raw if not isinstance(raw, float) or math.isfinite(raw) else str(raw)
    details = {"raw_change": literal, "change_number_format": number_format}
    if ocr_printed_percent:
        # A reconstructed OCR workbook has no original Excel number format.
        # Trust only a complete, visibly printed percentage, never a bare
        # numeric string whose native fraction/points semantics are unknown.
        if isinstance(raw, str):
            match = re.fullmatch(r"\s*([+\-−]?(?:0|[1-9]\d*)(?:,\d+)?)\s*%\s*", raw)
            if match:
                value = float(match[1].replace("−", "-").replace(",", "."))
                if math.isfinite(value):
                    return value, {
                        **details,
                        "change_percent_encoding": "printed_ocr_percent",
                        "change_scale": 1,
                    }
        return None, {**details, "change_percent_encoding": "unverified_ocr_percent"}
    if not finite:
        return None, {**details, "change_percent_encoding": "not_numeric"}
    # Select the actual positive/negative/zero section. Quoted, escaped, fill,
    # spacing and bracket tokens cannot turn a literal percent into scaling.
    sections = re.findall(r'(?:"[^"]*"|\\.|[^;])+', number_format or "General")
    section = sections[
        1
        if raw < 0 and len(sections) > 1
        else 2
        if raw == 0 and len(sections) > 2
        else 0
    ]
    if re.search(r"\[[<>=]", section):
        raise ValueError("Conditional daily variation format requires review")
    tokens = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]|_.|\*.', "", section)
    count = tokens.count("%")
    if count > 1:
        raise ValueError("Multiple daily percentage scaling tokens require review")
    scale = 100 if count else 1
    return float(raw) * scale, {
        **details,
        "change_percent_encoding": "fraction" if count else "percentage_points",
        "change_scale": scale,
    }


def parse_daily(data, expected_day, *, ocr_printed_percent=False, source_url=None):
    """Validate the whole original, returning rows, reviews and date evidence.

    Callers must persist ``reviews`` with the original's document id before
    considering the asset complete. A late invalid sheet raises before this
    function returns any prices to the publication layer.
    """
    from .worker import clean, positive, record, unit_for, workbooks

    output, reviews, resolutions = [], [], []
    formats = _number_formats(data)
    for sheet, source in workbooks(data):
        rows = list(source)
        if not rows or not any(clean(value) for row in rows for value in row):
            continue
        day, evidence, headings = _publication_day(data, rows, expected_day, source_url=source_url)
        if evidence and evidence not in resolutions:
            resolutions.append(evidence)
        header = next(
            (
                index
                for index, row in enumerate(rows[:12])
                if sum(clean(value).lower() == "precio" for value in row) >= 3
            ),
            None,
        )
        if header is None:
            raise ValueError("Daily price matrix header not found")
        columns = [
            col
            for col, value in enumerate(rows[header])
            if clean(value).lower() == "precio"
        ]
        market_header = next(
            (
                index
                for index, row in enumerate(rows[:header])
                if row and "precio" in clean(row[0]).lower()
            ),
            header - 1,
        )
        market_cells = {
            col: [
                clean(rows[index][col]) if col < len(rows[index]) else ""
                for index in range(market_header, header)
            ]
            for col in columns
        }
        markets = {
            col: ", ".join(dict.fromkeys(value for value in cells if value))
            for col, cells in market_cells.items()
        }
        for rownum, row in enumerate(rows[header + 1 :], header + 2):
            name = clean(row[0]) if row else ""
            for col in columns:
                raw_price = row[col] if col < len(row) else None
                if not positive(raw_price):
                    continue
                raw_variation = row[col + 1] if col + 1 < len(row) else None
                variation, change_details = percentage_change(
                    raw_variation, formats.get((sheet, rownum, col + 2), "General"),
                    ocr_printed_percent=ocr_printed_percent,
                )
                change_details["change_source_locator"] = (
                    f"{sheet}!row {rownum},col {col + 2}"
                )
                locator = f"{sheet}!row {rownum},col {col + 1}"
                if not name or not markets[col]:
                    reviews.append(
                        {
                            "source_locator": locator,
                            "reason": "Daily price has no explicit "
                            + ("product" if not name else "market")
                            + " header",
                            "record": {
                                "sheet": sheet,
                                "row": rownum,
                                "column": col + 1,
                                "product_name": name,
                                "market_name": markets[col] or None,
                                "price": float(raw_price),
                                **change_details,
                                "market_header_cells": market_cells[col],
                                "printed_heading_cells": headings,
                                "archive_date": expected_day.isoformat(),
                                "observation_date": day.isoformat(),
                                "parser_version": VERSION,
                            },
                        }
                    )
                    continue
                details = {
                    "predominant_variety": "*" in name,
                    **change_details,
                    "parser_version": VERSION,
                }
                if evidence:
                    details["date_resolution"] = evidence
                output.append(
                    record(
                        "dane-daily",
                        day,
                        name,
                        markets[col],
                        unit_for(name),
                        raw_price,
                        locator,
                        variation,
                        details,
                    )
                )
    if not output and not reviews:
        raise ValueError("No daily prices parsed")
    return {"rows": output, "reviews": reviews, "date_resolutions": resolutions}
