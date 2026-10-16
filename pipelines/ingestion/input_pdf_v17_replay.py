"""Source-bound v14 -> v17 input-PDF replay and publication guards.

Callers parse the complete source before starting the publication transaction.
"""

import hashlib
import io
import json
import re
from urllib.parse import urlsplit
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

import pdfplumber

VERSION = "inputs-pdf-v17"
OLD_VERSION = "inputs-pdf-v14"
MAX_PDF_BYTES = 32 * 1024 * 1024
# The exact retained long originals below require at most 209 pages. Keep the
# existing 32 MiB byte ceiling; documents above this explicit page ceiling fail closed.
MAX_PDF_PAGES = 256
ROW_FIELDS = "source_locator,series,observed_on,product_name,market_name,unit,price,change_percent,details"
FEB2016_CONTEXT_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_feb_2016.pdf"
FEB2016_CONTEXT_ID = "cb2289b8dad52378bc04a9787c7560a93a1feccfd47c64a41e010a33a499f5ab"
FEB2016_CONTEXT_DAY = "2016-02-29"
FEB2016_CONTEXT_PAGES = 88
FEB2016_CONTEXT_RAW_ROWS = 8779
FEB2016_CONTEXT_PUBLISHED_ROWS = 8177
FEB2016_CONTEXT_UNRESOLVED_ROWS = 602
FEB2016_CONTEXT_RETRY_ERROR = "ValueError: Retained input original identity/bytes mismatch"
APR2016_CONTEXT_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_abr_2016.pdf"
APR2016_CONTEXT_ID = "6cba3d6b39f171d2ae0f6e13b8afb7ab468e6dc4d2d807febc1f2a1c2731b2fc"
APR2016_CONTEXT_DAY = "2016-04-30"
APR2016_CONTEXT_PAGES = 89
APR2016_CONTEXT_BYTES = 4545108
APR2016_CONTEXT_RAW_ROWS = 9179
APR2016_CONTEXT_PUBLISHED_ROWS = 9179
APR2016_CONTEXT_UNRESOLVED_ROWS = 0
APR2016_CONTEXT_RETRY_ERROR = "ValueError: Retained input original identity/bytes mismatch"
APR2016_CONTEXT_TITLE = "DANE - Bol_Insumos_abr_2016.pdf"
APR2016_CONTEXT_OLD_VECTOR_SHA256 = "b5024b1e42e9135a112f384786238d794397612b9bc5a842e70f811dac41e85a"
FEB2016_CONTEXT_OLD_VECTOR_SHA256 = "51ffffaa7412e357e962f1fb97e9cb925a79db5ee322cba95836c0d2f6039fbb"
WORK_DEFERRED_RETRY_ERROR = "PDF page checkpoint retained; extraction will resume within the next run budget"
APR2016_CONTEXT_METADATA = {
    "retention": "permanent", "ingestion_kind": "context-pdf",
    "original_filename": "Bol_Insumos_abr_2016.pdf",
}
AUG2012_ALIAS_ASSET_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_producci%C3%B3n_agosto_2012.pdf"
AUG2012_ALIAS_SOURCE_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_producción_agosto_2012.pdf"
AUG2012_ALIAS_ID = "d5014c53af5300f481f5ce25f5404d2ef462255c0db8da6ac072e091549c8479"
AUG2012_ALIAS_DAY = "2012-08-31"
AUG2012_ALIAS_PAGES = 84
AUG2012_ALIAS_BYTES = 1196708
AUG2012_ALIAS_RAW_ROWS = 7921
AUG2012_ALIAS_PUBLISHED_ROWS = 7891
AUG2012_ALIAS_UNRESOLVED_ROWS = 30
AUG2012_ALIAS_RETRY_ERROR = "ValueError: Retained input original identity/bytes mismatch"
AUG2012_ALIAS_TITLE = "DANE - insumos_factores_de_producción_agosto_2012.pdf"
AUG2012_ALIAS_FILENAME = "insumos_factores_de_producción_agosto_2012.pdf"
# Exact retained 2012 input-PDF originals use ordinary inputs-pdf metadata,
# while the 2013 registry below uses context-pdf metadata.
RETAINED_2012_CONTEXTS = {
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_noviembre_2012.pdf": {
        "document_id": "0c2cf79ba4c3c25c006f8979f4d4e96b0b556cb609054d1cbcaa47fe933113d7",
        "day": "2012-11-30", "pages": 75, "bytes": 1338752,
        "raw_rows": 8036, "typed_rows": 7997, "unresolved_rows": 39,
        "title": "DANE - insumos_factores_de_produccion_noviembre_2012.pdf",
        "filename": "insumos_factores_de_produccion_noviembre_2012.pdf",
        "metadata": {"retention": "permanent", "ingestion_kind": "inputs-pdf",
                     "original_filename": "insumos_factores_de_produccion_noviembre_2012.pdf"},
        "source_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_noviembre_2012.pdf",
        "old_vector_sha256": "c655ba0caf0ccd8b8feb1b7ff4d77f805cbbc55d44afbcb340eb83ad1c5706e9",
    },
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_diciembre_2012.pdf": {
        "document_id": "fddfc753c883425d3e7f9374285c07e037313be68a69ad97a0ac56fff1d7bd6a",
        "day": "2012-12-31", "pages": 76, "bytes": 1268719,
        "raw_rows": 7833, "typed_rows": 7726, "unresolved_rows": 107,
        "title": "DANE - insumos_factores_de_produccion_diciembre_2012.pdf",
        "filename": "insumos_factores_de_produccion_diciembre_2012.pdf",
        "metadata": {"retention": "permanent", "ingestion_kind": "inputs-pdf",
                     "original_filename": "insumos_factores_de_produccion_diciembre_2012.pdf"},
        "source_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_diciembre_2012.pdf",
        "old_vector_sha256": "cfabc31d2a30c6108b37c218377ce6fd00a5b3d0cd9939bc7c9bbed627417bdc",
    },
}
RETAINED_2013_CONTEXTS = {
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_ene_2014.pdf': ('8e7fa15de3e8cf11535eed5d54401cac447f849ed145ca8c6f980526c639c818', '2014-01-31', 59, 2561852, 5639, 5639, 0, 'DANE - insumos_factores_de_produccion_ene_2014.pdf', 'insumos_factores_de_produccion_ene_2014.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_febrero_2013.pdf': ('21e7b209bf00c76ca714b3083c7a0604b5ca1e57b316eba2e19efb9ac1e13674', '2013-02-28', 84, 2487802, 8843, 8843, 0, 'DANE - insumos_factores_de_produccion_febrero_2013.pdf', 'insumos_factores_de_produccion_febrero_2013.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_marzo_2013.pdf': ('1a13ada6199f60b15c94b4b0504330011d29348a9075d14d0562252f9dac9b58', '2013-03-31', 96, 2450553, 10101, 10101, 0, 'DANE - insumos_factores_de_produccion_marzo_2013.pdf', 'insumos_factores_de_produccion_marzo_2013.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_abril_2013.pdf': ('8a7e745f864c99151e0d2aa98b67e4575f5f600e20ad13a08902cf46142e0d93', '2013-04-30', 84, 5362682, 8923, 8897, 26, 'DANE - insumos_factores_de_produccion_abril_2013.pdf', 'insumos_factores_de_produccion_abril_2013.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mayo_2013.pdf': ('8a75439242cf7c532409a7bf53a2207f8f7c1f9b4f311338f372c62276549566', '2013-05-31', 96, 2542752, 10711, 10711, 0, 'DANE - insumos_factores_de_produccion_mayo_2013.pdf', 'insumos_factores_de_produccion_mayo_2013.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_junio_2013.pdf': ('26c8a7fc1ffe2c9252becc64055f8abf9be89e13e99668888f394d84a70db390', '2013-06-30', 92, 2445766, 9860, 9835, 25, 'DANE - insumos_factores_de_produccion_junio_2013.pdf', 'insumos_factores_de_produccion_junio_2013.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_julio_2013.pdf': ('3861de4e5c36b88e139234b0a6ca6e5d1c4b41b9128d26c748165300f2a9ffd6', '2013-07-31', 92, 2529454, 10652, 10646, 6, 'DANE - insumos_factores_de_produccion_julio_2013.pdf', 'insumos_factores_de_produccion_julio_2013.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_agosto_2013.pdf': ('36b4ed98022f86790b4e420f8a41f8cec5d13b06f9f0961d2c4ff16ce44a8d4e', '2013-08-31', 92, 2513747, 10202, 10151, 51, 'DANE - insumos_factores_de_produccion_agosto_2013.pdf', 'insumos_factores_de_produccion_agosto_2013.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_sep_2013.pdf': ('2141ca9b89046ade49f79b31846831331ef4170c77f6d8923f04bd09bb02c6c0', '2013-09-30', 92, 2537238, 9295, 9286, 9, 'DANE - insumos_factores_de_produccion_sep_2013.pdf', 'insumos_factores_de_produccion_sep_2013.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_oct_2013.pdf': ('73e73c6951273ff113cd37bb1121858ca990d2cfd836f6fcfc2b30bd0b3278fe', '2013-10-31', 56, 2447460, 5657, 5657, 0, 'DANE - insumos_factores_de_produccion_oct_2013.pdf', 'insumos_factores_de_produccion_oct_2013.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_nov_2013.pdf': ('c1512c726dcacc08e0b6d5cf9f69adf876a0afa782fbdcfb8d15adc40e146a72', '2013-11-30', 64, 2519711, 6109, 6106, 3, 'DANE - insumos_factores_de_produccion_nov_2013.pdf', 'insumos_factores_de_produccion_nov_2013.pdf'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_dic_2013.pdf': ('1eb6cb351a62a47406657e342ee40d5be8eb364e1cc844a210a8572588eee53f', '2013-12-31', 60, 1935343, 5506, 5506, 0, 'DANE - insumos_factores_de_produccion_dic_2013.pdf', 'insumos_factores_de_produccion_dic_2013.pdf'),
}
RETAINED_2013_CONTEXT_RETRY_ERROR = "ValueError: Retained input original identity/bytes mismatch"
RETAINED_2012_RETRY_ERROR = "ValueError: Retained input old publication checkpoint changed"

def _approved_registered_retry_error(status, error, initial_error):
    """Accept the known initial mismatch or an exact pending budget deferral only."""
    return ((status == "failed" and error == initial_error)
            or (status == "pending" and error in (initial_error, WORK_DEFERRED_RETRY_ERROR)))


# This read-only pre-retry snapshot supplies each source's exact prior v14
# error field. Lifecycle status/version are validated separately below because
# the worker may leave a bound source pending or failed while resuming it.
RETAINED_2013_OLD_ASSETS = {
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_ene_2014.pdf': ('failed', 'inputs-pdf-v17', 5639, 'ValueError: Retained input original identity/bytes mismatch'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_febrero_2013.pdf': ('failed', 'inputs-pdf-v17', 8843, 'ValueError: Retained input original identity/bytes mismatch'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_marzo_2013.pdf': ('failed', 'inputs-pdf-v17', 10101, 'ValueError: Retained input original identity/bytes mismatch'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_abril_2013.pdf': ('failed', 'inputs-pdf-v17', 8923, 'ValueError: Retained input original identity/bytes mismatch'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mayo_2013.pdf': ('failed', 'inputs-pdf-v17', 10711, 'ValueError: Retained input original identity/bytes mismatch'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_junio_2013.pdf': ('failed', 'inputs-pdf-v17', 9860, 'ValueError: Retained input original identity/bytes mismatch'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_julio_2013.pdf': ('failed', 'inputs-pdf-v17', 10652, 'ValueError: Retained input original identity/bytes mismatch'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_agosto_2013.pdf': ('complete', 'inputs-pdf-v14', 10202, None),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_sep_2013.pdf': ('complete', 'inputs-pdf-v14', 9295, 'Conflicting source keys retained but excluded from app: 13'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_oct_2013.pdf': ('complete', 'inputs-pdf-v14', 5657, 'Conflicting source keys retained but excluded from app: 5'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_nov_2013.pdf': ('complete', 'inputs-pdf-v14', 6109, None),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_dic_2013.pdf': ('complete', 'inputs-pdf-v14', 5506, None),
}
RETAINED_2013_V14_ASSET_ERRORS = {
    url: asset[3] for url, asset in RETAINED_2013_OLD_ASSETS.items()
}
RETAINED_2013_OLD_VECTOR_SHA256 = {
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_ene_2014.pdf': '71bc5a4fc6d1cbc7675b08bb54b5b20bfbc70839fc62f36e414172468a45fcea',
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_febrero_2013.pdf": "339e373522aec5c8ff04737795e757870656ca12ce3d04a90e76ba29700c9697",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_marzo_2013.pdf": "340affb2a0502fdc6341772739b024dbb6de017b1cf477daeccb8532af53fad2",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_abril_2013.pdf": "a5e73cee5c14ff65c266e54c73013f3443d3d9325d13826286b4504b39cfc4da",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mayo_2013.pdf": "a986d5f5c500001e995c442fb2a06934c9783e7d221c659cc0eb6ed9704948df",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_junio_2013.pdf": "83606abcc7ab6d597f43fee02cc5ab0643357caae8401d165770abb79eddf19c",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_julio_2013.pdf": "8a3aeab18b7d39bc0739205b258824ab85a614e818c355cfec31014892a44000",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_agosto_2013.pdf": "064bde2a52b8ad640877163c7c7d89bd4464a653b5af8693de1ac1ce7d40592b",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_sep_2013.pdf": "d690a983859b14a83217c5e4ecc869bc515df2e5900885bf58c4d2fe7342db2a",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_oct_2013.pdf": "5640593cd9ba961f5869be5ef8bdd4c28a7d625fbeaca5c23d4778b6178b1747",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_nov_2013.pdf": "100f318262f8992192225f215d1d342b5bb87c5f849e896acb4ad54d9cdc652e",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_dic_2013.pdf": "78c9c2c1b47eeacb37416a34d533bd30d81015fdecdc8b6b7a113e0036bf20d0",
}
RETAINED_2013_NEW_COHORTS = {
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_ene_2014.pdf': (5639, 5639, 0, '9a41e5e3fce93d3fab54b7e6a9f50700f15fdbe2b5683dd6dfc0e1a7015ffe79'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_febrero_2013.pdf': (8843, 8843, 0, 'fd9e0d6f0b238399e9004e744430aed2a8e796067d16d57af95fdcfc6f9f2abb'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_marzo_2013.pdf': (10101, 10101, 0, 'b67f070187346795fdde9ccccfa0245b3652bd6e47e90f1549197a271450a57f'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_abril_2013.pdf': (8923, 8897, 26, '7e1d7ae31656fb8457aea0c1735b596153448a1e5a0d5b04d5c4a23474b670d1'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mayo_2013.pdf': (10711, 10711, 0, '25b16108cb89fc24b737f0b4637465ddfa33af75e8ae83855801014d4c8f57e8'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_junio_2013.pdf': (9860, 9835, 25, 'ba71aad4128404230876c09a4e5aee5206dd25624997752a5bd90fd661129755'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_julio_2013.pdf': (10652, 10646, 6, '9af6a13db6647a0a5a5df3544115113075e3efbfeed758dd755b77deac477b52'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_agosto_2013.pdf': (10202, 10151, 51, '8e2345ff8bebdefefb9a7dccf531f07fa7f2d701a282ce2d46c75a19c8dc3024'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_sep_2013.pdf': (9310, 9301, 9, 'c6ddd065d32ebc49c992d37c16d586fdd216b8e42a37de3ce388120e326af9ef'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_oct_2013.pdf': (5657, 5657, 0, '37527a14ae715b4533fa9718429660d8dbab879c718e6ba0476cfde74ccafbe9'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_nov_2013.pdf': (6110, 6107, 3, '5b9e1b3df5f6c5bd625e383888e364590f4b699bf94ce9e99412135a384848dc'),
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_dic_2013.pdf': (5506, 5506, 0, 'e6c1093d16c566fa1237dc2efa7d855d4a790eabd9f1ec3a3aa4f52259a2469d'),
}

CONTEXT_ORIGINALS = {
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_feb_2014.pdf":
        ("3e1265bdbff25420d9be9b44c4db0aa7564585270cdc93878810c68ebae46dc3", "2014-02-28", 56, 4794),
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mar_2014.pdf":
        ("2befda0f1d3d4740b7a82e3a9d5ca3e6c9d2e213193ccf011ddadf9d8d729403", "2014-03-31", 64, 5706),
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_may_2014.pdf":
        ("db08213afe320e1a1101d2c8311565c924f4a2c82aef56d98a3971e26a1c9d62", "2014-05-31", 64, 5977),
}

# Fallback for the retained DANE SIPSA input-PDF family. This is based on
# immutable archive evidence and the complete v14/v17 row checks below, not a
# URL-only month allowlist. URL spellings remain byte-exact.
_DANE_INPUT_PDF_NAME = re.compile(
    r"(?:insumos_factores_de_produccion_[A-Za-z0-9_%.-]+|"
    r"Bol_(?:%20| )?Insumos[A-Za-z0-9_% .-]*)\.pdf\Z"
)
_RETAINED_IDENTITY_ERROR = "ValueError: Retained input original identity/bytes mismatch"
# Independent full-v14 SQL exports for the four 2014 context originals reviewed
# for this route. Other exact context originals are verified by native reparse.
JAN2019_CONTEXT_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_%20Insumos_ene_2019.pdf"
JAN2019_LITERAL_ALIAS_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_ Insumos_ene_2019.pdf"
JAN2019_CONTEXT_DID = "849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb"
JAN2019_CONTEXT_DAY = "2019-01-31"
JAN2019_CONTEXT_PAGES = 206
JAN2019_CONTEXT_BYTES = 3681233
JAN2019_CONTEXT_RAW_ROWS = 14458
JAN2019_CONTEXT_TYPED_ROWS = 14443
JAN2019_CONTEXT_UNRESOLVED_ROWS = 15
JAN2019_CONTEXT_OLD_VECTOR_SHA256 = "dceb3a49cfcffb9e3b71fc40b455e5eae9b3faac719494b86f5e641539fc0b71"
JAN2019_CONTEXT_NEW_VECTOR_SHA256 = "5f20551b874de7bff325aae83dbe86d2b7e20d371f747d244f17c4ba92c25484"
JAN2019_CONTEXT_SOURCE_ALIASES = {JAN2019_CONTEXT_URL: JAN2019_CONTEXT_URL,
                                  JAN2019_LITERAL_ALIAS_URL: JAN2019_CONTEXT_URL}
JAN2019_CONTEXT_REFERENCE_PERIOD = "Serie histórica completa"
LONG_INPUT_PDF_REPAIRS = {
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_sep_2018.pdf": {
        "document_id": "f37ddee1c655810d1e6a6ea7746bd1a429337fd22deda2b3db8c52762780a2fb",
        "day": "2018-09-30", "pages": 201, "bytes": 4430044, "raw_rows": 15344,
        "typed_rows": 15339, "unresolved_rows": 5,
        "old_vector_sha256": "2038a1c87e4bfcfb5480ffb3ac313b2eceafbeadd4911d72e3a458687ca1d07a",
        "metadata_kind": "inputs-pdf",
    },
    JAN2019_CONTEXT_URL: {
        "document_id": JAN2019_CONTEXT_DID, "day": JAN2019_CONTEXT_DAY,
        "pages": JAN2019_CONTEXT_PAGES, "bytes": JAN2019_CONTEXT_BYTES,
        "raw_rows": JAN2019_CONTEXT_RAW_ROWS, "typed_rows": JAN2019_CONTEXT_TYPED_ROWS,
        "unresolved_rows": JAN2019_CONTEXT_UNRESOLVED_ROWS,
        "old_vector_sha256": JAN2019_CONTEXT_OLD_VECTOR_SHA256,
        "metadata_kind": "context-pdf",
    },
    JAN2019_LITERAL_ALIAS_URL: {
        "document_id": JAN2019_CONTEXT_DID, "day": JAN2019_CONTEXT_DAY,
        "pages": JAN2019_CONTEXT_PAGES, "bytes": JAN2019_CONTEXT_BYTES,
        "raw_rows": JAN2019_CONTEXT_RAW_ROWS, "typed_rows": JAN2019_CONTEXT_TYPED_ROWS,
        "unresolved_rows": JAN2019_CONTEXT_UNRESOLVED_ROWS,
        "old_vector_sha256": JAN2019_CONTEXT_OLD_VECTOR_SHA256,
        "metadata_kind": "context-pdf",
    },
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_feb_2019.pdf": {
        "document_id": "8c5e95de023a6fafd71484dc476c40083aa886d05ca00f90ada498cac05043f7",
        "day": "2019-02-28", "pages": 209, "bytes": 3976584, "raw_rows": 14366,
        "typed_rows": 14363, "unresolved_rows": 3,
        "old_vector_sha256": "c4493ebc31c03509b22b875e99475d56bce44721498bdf5a563c7e36759c7cae",
        "metadata_kind": "inputs-pdf",
    },
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_nov_2018.pdf": {
        "document_id": "79b2dadcad9c2387648b64620d92a896b5ef5d8f9a2d366e522021ff62d7cbb3",
        "day": "2018-11-30", "pages": 195, "bytes": 2806034, "raw_rows": 15241,
        "typed_rows": 15215, "unresolved_rows": 26,
        "old_vector_sha256": "d72f5489dabb9530fa058a8409aeb7e6caa70641fdb6a99357e12d2c7e1ae059",
        "new_vector_sha256": "f4091a0233146c619e0b0789ffa031945692b0ed7c9c0f3075b2148fc0bf3125",
        "metadata_kind": "inputs-pdf",
        "failed_retry_errors": ("ValueError: Retained input old publication checkpoint changed",),
    },
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_dic_2018.pdf": {
        "document_id": "7b33370ff3eb28f8567fb36528dc8c2c619aad1629c1aaf761f7448269ceb293",
        "day": "2018-12-31", "pages": 180, "bytes": 2627644, "raw_rows": 13906,
        "typed_rows": 13888, "unresolved_rows": 18,
        "old_vector_sha256": "a4a23f80303ce72c1d4d3dee8b9467d945f07709985cb8c8833520757e20bfdf",
        "new_vector_sha256": "5052dbf4dde522ec05e4f382e874f654d39b0e1cf78ccaff338307a0d285759d",
        "metadata_kind": "inputs-pdf",
        "failed_retry_errors": ("ValueError: Retained input old publication checkpoint changed",),
    },
}




def _assert_long_input_pdf_witness(url, did, day, page_count, records, body):
    """Bind only source-registered originals eligible for the long-input retry lane."""
    spec = LONG_INPUT_PDF_REPAIRS.get(url)
    if spec is None or did != spec["document_id"]:
        return False
    if ((day.isoformat() if hasattr(day, "isoformat") else None,
         page_count, records, len(body)) !=
            (spec["day"], spec["pages"], spec["raw_rows"], spec["bytes"])
            or hashlib.sha256(body).hexdigest() != did):
        raise ValueError("Registered long input PDF source witness differs")
    return True


def _assert_long_input_pdf_v14_witness(db, url, spec):
    """Bind an exact long ordinary-input source to its complete v14 cohort."""
    did, day = spec["document_id"], spec["day"]
    filename = url.rsplit("/", 1)[-1]
    source = db.execute(
        """SELECT kind,source_url,media_type,page_count,content,metadata,title,publisher,reference_period
           FROM source_document WHERE id=%s""", (did,),
    ).fetchone()
    if source is None:
        raise ValueError("Registered long input PDF source witness is missing")
    kind, source_url, media, pages, content, metadata, title, publisher, period = source
    body = bytes(content or b"")
    if ((kind, source_url, media, pages, metadata, title, publisher, str(period)) !=
            ("original", url, "application/pdf", spec["pages"],
             {"retention": "permanent", "ingestion_kind": "inputs-pdf",
              "original_filename": filename},
             "DANE - " + filename, "DANE", day)
            or len(body) != spec["bytes"]
            or hashlib.sha256(body).hexdigest() != did):
        raise ValueError("Registered long input PDF source metadata differs")
    checkpoint = db.execute(
        """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
           AND processor_version=%s AND step='inputs-pdf:published'""", (did, OLD_VERSION),
    ).fetchone()
    cohort = db.execute(
        """SELECT count(*),count(*) FILTER (WHERE series='dane-inputs-pdf'),
                  count(*) FILTER (WHERE series='dane-inputs-pdf-unresolved')
           FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s""",
        (did, OLD_VERSION),
    ).fetchone()
    if (tuple(cohort) != (spec["raw_rows"], spec["typed_rows"], spec["unresolved_rows"])
            or checkpoint != (spec["typed_rows"],)):
        raise ValueError("Registered long input PDF v14 cohort/checkpoint differs")
    rows = db.execute(
        f"SELECT {ROW_FIELDS} FROM historical_price WHERE document_id=%s "
        "AND details->>'parser_version'=%s ORDER BY source_locator", (did, OLD_VERSION),
    ).fetchall()
    if _retained_vector_sha256(rows) != spec["old_vector_sha256"]:
        raise ValueError("Registered long input PDF v14 vector differs")


def _generic_context_source_url(url, did=None):
    """Resolve the Jan literal URL only for its exact immutable source DID."""
    if url == JAN2019_LITERAL_ALIAS_URL:
        return JAN2019_CONTEXT_URL if did == JAN2019_CONTEXT_DID else url
    return url


def _generic_context_expected_period(url, day, did=None):
    if (url in (JAN2019_CONTEXT_URL, JAN2019_LITERAL_ALIAS_URL)
            and did == JAN2019_CONTEXT_DID and day is not None
            and hasattr(day, "isoformat") and day.isoformat() == JAN2019_CONTEXT_DAY):
        return JAN2019_CONTEXT_REFERENCE_PERIOD
    return day.isoformat() if day is not None and hasattr(day, "isoformat") else None


GENERIC_CONTEXT_OLD_VECTOR_SHA256 = {
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_abr_2014.pdf": "bfe28a89983dc6b44c6f45ae1227d2b0a842220c33fa3e015778853d9acbd10f",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_jun_2014.pdf": "0639f0d385c61b79a64d955effc88410887a59dfe2175c7012cd87cbd146668e",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_jul_2014.pdf": "d8f3864140ea85d5d7ad5b2b372d96cff5c9a91927e73023c14434ed7a1a7b2a",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_ago_2014.pdf": "9966b7e928a0a17fdf5192fcaebf043437f66c5684dca38717d61134426f6a1b",
}


def _generic_retained_context_filename(url, did=None):
    """Return an allowed exact DANE filename, with one registered asset alias."""
    try:
        parsed = urlsplit(_generic_context_source_url(url, did))
    except (TypeError, ValueError):
        return None
    if (parsed.scheme != "https" or parsed.netloc != "www.dane.gov.co"
            or parsed.query or parsed.fragment
            or not parsed.path.startswith("/files/investigaciones/agropecuario/sipsa/")):
        return None
    name = parsed.path.rsplit("/", 1)[-1]
    return name if _DANE_INPUT_PDF_NAME.fullmatch(name) else None


def _generic_context_lifecycle(status, processor_version, error, url=None, did=None, day=None):
    """Return eligibility for the exact retained-source lifecycle."""
    if processor_version == OLD_VERSION and status in ("complete", "processed", "pending"):
        return True
    if processor_version == VERSION and status == "complete":
        return True
    ordinary_retry = (processor_version == VERSION and _approved_registered_retry_error(
        status, error, _RETAINED_IDENTITY_ERROR
    ))
    jan_page_retry = (
        url in JAN2019_CONTEXT_SOURCE_ALIASES and did == JAN2019_CONTEXT_DID
        and day is not None and hasattr(day, "isoformat")
        and day.isoformat() == JAN2019_CONTEXT_DAY
        and processor_version == VERSION and status in ("failed", "pending")
        and error == "ValueError: Retained input PDF page count mismatch"
    )
    return ordinary_retry or jan_page_retry


def _generic_context_metadata_ok(url, day, page_count, metadata, title, publisher, reference_period, did=None):
    filename = _generic_retained_context_filename(url, did)
    return bool(
        filename
        and metadata == {
            "retention": "permanent", "ingestion_kind": "context-pdf",
            "original_filename": filename,
        }
        and title == "DANE - " + filename
        and publisher == "DANE"
        and day is not None and hasattr(day, "isoformat")
        and reference_period == _generic_context_expected_period(url, day, did)
        and isinstance(page_count, int) and 0 < page_count <= MAX_PDF_PAGES
    )


def _generic_context_archive_kind(db, did):
    """Distinguish a real retained context original from ordinary input PDFs."""
    row = db.execute(
        "SELECT kind,metadata FROM source_document WHERE id=%s", (did,),
    ).fetchone()
    if row is None:
        return None
    return row[1].get("ingestion_kind") if isinstance(row[1], dict) else None


def _generic_context_original_id(db, url):
    """Return the exact retained context original bound to this URL, if any."""
    if not _generic_retained_context_filename(url):
        return None
    source_url = (JAN2019_CONTEXT_URL if url == JAN2019_LITERAL_ALIAS_URL else url)
    rows = db.execute(
        """SELECT id FROM source_document WHERE source_url=%s AND kind='original'
           AND metadata->>'ingestion_kind'='context-pdf' ORDER BY id""",
        (source_url,),
    ).fetchall()
    if len(rows) > 1:
        raise ValueError("DANE context URL has multiple retained originals")
    if url in JAN2019_CONTEXT_SOURCE_ALIASES and rows and rows[0][0] != JAN2019_CONTEXT_DID:
        raise ValueError("January 2019 asset URL points to an unexpected retained original")
    return rows[0][0] if rows else None


def source_input_processor_version(url):
    """Keep reviewed URL routes and mixed-date source at their old versions."""
    from pipelines.ingestion.reviewed_wuxal_apr2015 import URL as WUXAL_URL, VERSION as WUXAL_VERSION
    from pipelines.ingestion.reviewed_quindio_sep2014 import URL as SEPT_URL, VERSION as SEPT_VERSION
    from pipelines.ingestion.pdf_sources import MIXED_FEB2018_INPUT_URL
    if url == WUXAL_URL:
        return WUXAL_VERSION
    if url == SEPT_URL:
        return SEPT_VERSION
    if url == MIXED_FEB2018_INPUT_URL:
        return OLD_VERSION
    return VERSION


def _normalized_old(row):
    locator, series, day, product, market, unit, price, variation, details = row
    if not locator.endswith("; " + OLD_VERSION) or details.get("parser_version") != OLD_VERSION:
        raise ValueError("Old input row lacks exact v14 locator/details")
    return (
        locator[: -len(OLD_VERSION)] + VERSION, series, day, product, market, unit,
        Decimal(str(price)), Decimal(str(variation)) if variation is not None else None,
        {**details, "parser_version": VERSION},
    )


def _as_vector(row):
    locator, series, day, product, market, unit, price, variation, details = row
    return (locator, series, day, product, market, unit, Decimal(str(price)),
            Decimal(str(variation)) if variation is not None else None, details)


def _assert_2013_registered_old_witness(db, url, spec):
    """Keep the original registered v14 source/cohort intact across URL revisions."""
    did, day, pages, size, raw, typed, unresolved, title, filename = spec
    source = db.execute(
        """SELECT kind,source_url,media_type,page_count,content,metadata,
                  title,publisher,reference_period
           FROM source_document WHERE id=%s""", (did,)
    ).fetchone()
    if source is None:
        raise ValueError("Registered 2013 v14 source witness is missing")
    kind, source_url, media, page_count, content, metadata, actual_title, publisher, period = source
    body = bytes(content or b"")
    if ((kind, source_url, media, page_count, actual_title, publisher, str(period)) !=
            ("original", url, "application/pdf", pages, title, "DANE", day)
            or metadata != {"retention": "permanent", "ingestion_kind": "context-pdf",
                            "original_filename": filename}
            or len(body) != size or hashlib.sha256(body).hexdigest() != did
            or not body.startswith(b"%PDF-")):
        raise ValueError("Registered 2013 v14 source witness differs")
    checkpoint = db.execute(
        """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
           AND processor_version=%s AND step='inputs-pdf:published'""", (did, OLD_VERSION)
    ).fetchone()
    cohort = db.execute(
        """SELECT count(*),count(*) FILTER (WHERE series='dane-inputs-pdf'),
                  count(*) FILTER (WHERE series='dane-inputs-pdf-unresolved')
           FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s""",
        (did, OLD_VERSION),
    ).fetchone()
    if checkpoint != (typed,) or tuple(cohort) != (raw, typed, unresolved):
        raise ValueError("Registered 2013 v14 source cohort/checkpoint differs")
    rows = db.execute(
        f"SELECT {ROW_FIELDS} FROM historical_price WHERE document_id=%s "
        "AND details->>'parser_version'=%s ORDER BY source_locator",
        (did, OLD_VERSION),
    ).fetchall()
    expected_vector = RETAINED_2013_OLD_VECTOR_SHA256.get(url)
    if expected_vector is None or _retained_vector_sha256(rows) != expected_vector:
        raise ValueError("Registered 2013 v14 full source vector differs")


def _registered_2013_replacement_state(db, url, day, asset, spec):
    """Validate a newly archived mutable-URL body before normal fetch/replay.

    This does not provide the body to the parser and never treats a prior
    revision as a v14 replay. It only permits the ordinary worker path after
    proving the exact URL/day, hash-addressed archive metadata, preserved v14
    witness, and a complete or transactionally empty v17 lifecycle.
    """
    did, expected_day, _pages, _size, _old_raw, _old_typed, _old_unresolved, _title, _filename = spec
    if day is None or not hasattr(day, "isoformat") or day.isoformat() != expected_day:
        raise ValueError("Registered 2013 replacement date differs")
    if asset is None or len(asset) != 6:
        raise ValueError("Registered 2013 replacement asset is missing")
    kind, asset_day, current_did, status, version, records = asset
    if (kind, str(asset_day), status, version) not in {
        ("inputs-pdf", expected_day, "complete", VERSION),
        ("inputs-pdf", expected_day, "pending", VERSION),
        ("inputs-pdf", expected_day, "failed", VERSION),
    } or not isinstance(current_did, str) or len(current_did) != 64 or current_did == did:
        raise ValueError("Registered 2013 replacement asset identity/lifecycle differs")

    _assert_2013_registered_old_witness(db, url, spec)
    name = url.rsplit("/", 1)[-1]
    source = db.execute(
        """SELECT kind,source_url,media_type,page_count,content,metadata,
                  title,publisher,reference_period
           FROM source_document WHERE id=%s""", (current_did,)
    ).fetchone()
    if source is None:
        raise ValueError("Registered 2013 replacement original is missing")
    source_kind, source_url, media, page_count, content, metadata, title, publisher, period = source
    body = bytes(content or b"")
    if ((source_kind, source_url, media, title, publisher, str(period)) !=
            ("original", url, "application/pdf", "DANE - " + name, "DANE", expected_day)
            or metadata != {"ingestion_kind": "inputs-pdf", "retention": "permanent",
                            "original_filename": name}
            or not body.startswith(b"%PDF-") or not 0 < len(body) <= MAX_PDF_BYTES
            or hashlib.sha256(body).hexdigest() != current_did):
        raise ValueError("Registered 2013 replacement source identity/bytes differ")
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        actual_pages = len(pdf.pages)
    if not 0 < actual_pages <= MAX_PDF_PAGES or page_count != actual_pages:
        raise ValueError("Registered 2013 replacement page count differs")

    previous_rows = db.execute(
        "SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",
        (current_did, OLD_VERSION),
    ).fetchone()[0]
    if previous_rows:
        raise ValueError("Registered 2013 replacement unexpectedly has a v14 quote cohort")
    stray_checkpoints = db.execute(
        """SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s
           AND step='inputs-pdf:published' AND processor_version<>%s""",
        (current_did, VERSION),
    ).fetchone()[0]
    if stray_checkpoints:
        raise ValueError("Registered 2013 replacement has an unexpected publication checkpoint")
    cohort = db.execute(
        """SELECT count(*),count(*) FILTER (WHERE series='dane-inputs-pdf'),
                  count(*) FILTER (WHERE series='dane-inputs-pdf-unresolved')
           FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s""",
        (current_did, VERSION),
    ).fetchone()
    checkpoint = db.execute(
        """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
           AND processor_version=%s AND step='inputs-pdf:published'""", (current_did, VERSION)
    ).fetchone()
    if status == "complete":
        if (records is None or cohort[0] != records or cohort[1] <= 0
                or cohort[1] + cohort[2] != cohort[0]
                or checkpoint != (cohort[1],)):
            raise ValueError("Registered 2013 replacement completion cohort is inconsistent")
    elif (cohort != (0, 0, 0) or checkpoint is not None
          or not isinstance(records, int) or records < 0):
        raise ValueError("Registered 2013 interrupted replacement is not an empty resumable cohort")


def _registered_2012_replacement_state(db, url, day, asset, spec):
    """Validate a changed Nov/Dec 2012 body before ordinary URL refresh."""
    if day is None or not hasattr(day, "isoformat") or day.isoformat() != spec["day"]:
        raise ValueError("Registered November/December 2012 replacement date differs")
    if asset is None or len(asset) != 6:
        raise ValueError("Registered November/December 2012 replacement asset is missing")
    kind, asset_day, did, status, version, records = asset
    valid_lifecycle = (
        (status == "complete" and version == VERSION)
        or (status in ("pending", "failed") and version in (OLD_VERSION, VERSION))
    )
    if ((kind, str(asset_day)) != ("inputs-pdf", spec["day"]) or not valid_lifecycle
            or not isinstance(did, str) or len(did) != 64 or did == spec["document_id"]):
        raise ValueError("Registered November/December 2012 replacement lifecycle differs")
    if _registered_replacement_old_did(db, did) != spec["document_id"]:
        raise ValueError("Registered November/December 2012 replacement old witness differs")
    cohort = db.execute(
        """SELECT count(*),count(*) FILTER (WHERE series='dane-inputs-pdf'),
                  count(*) FILTER (WHERE series='dane-inputs-pdf-unresolved')
           FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s""",
        (did, VERSION),
    ).fetchone()
    checkpoint = db.execute(
        """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
           AND processor_version=%s AND step='inputs-pdf:published'""", (did, VERSION),
    ).fetchone()
    if status == "complete":
        if (not isinstance(records, int) or cohort[0] != records or cohort[1] + cohort[2] != cohort[0]
                or cohort[1] <= 0 or checkpoint != (cohort[1],)):
            raise ValueError("Registered November/December 2012 replacement completion differs")
    elif cohort != (0, 0, 0) or checkpoint is not None or not isinstance(records, int) or records < 0:
        raise ValueError("Registered November/December 2012 interrupted replacement is not empty")


def _retained_vector_sha256(rows):
    def scalar(value):
        if value is None:
            return None
        number = Decimal(str(value))
        return "0" if number == 0 else format(number.normalize(), "f")

    values = []
    for row in rows:
        vector = _as_vector(row)
        values.append([
            vector[0], vector[1], vector[2].isoformat() if hasattr(vector[2], "isoformat") else str(vector[2]),
            vector[3], vector[4], vector[5], scalar(vector[6]), scalar(vector[7]), dict(vector[8]),
        ])
    values.sort(key=lambda item: item[0])
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def retained_v14_input_pdf(db, url, kind, day, target_version):
    """Return bytes only for an exact retained-source lifecycle, or None.

    A present old asset with corrupt original/row evidence raises; it never
    silently falls through to a publisher fetch. Registered 2013 sources may
    resume from their exact v14 complete/pending state or v17 failed/pending
    retry state. Once the asset points at a hash- and metadata-verified newer
    body, its original v14 witness remains pinned and the URL continues through
    the ordinary mutable fetch path; replacement bytes are never returned as
    an old v14 replay.
    """
    if kind != "inputs-pdf" or target_version != VERSION or source_input_processor_version(url) != VERSION:
        return None
    asset = db.execute(
        """SELECT kind,observed_on,document_id,status,processor_version,records
           FROM ingestion_asset WHERE url=%s""", (url,)
    ).fetchone()
    if asset is None:
        return None
    actual_kind, actual_day, did, status, old_version, records = asset
    if actual_day is None or not hasattr(actual_day, "isoformat"):
        raise ValueError("Retained input source date missing")
    explicit_context_url = (
        url in CONTEXT_ORIGINALS or url in RETAINED_2013_CONTEXTS
        or url in RETAINED_2012_CONTEXTS
        or url in (FEB2016_CONTEXT_URL, APR2016_CONTEXT_URL, AUG2012_ALIAS_ASSET_URL)
    )
    generic_context_retry = False
    generic_context_binding = False
    generic_context_original = (
        _generic_context_original_id(db, url) if not explicit_context_url else None
    )
    if generic_context_original is not None and did != generic_context_original:
        replacement_old = _generic_context_replacement_old_did(db, did)
        if replacement_old == generic_context_original:
            # A source-verified changed URL body follows the normal fetch and
            # publication lifecycle; it is never replayed as the old v14 body.
            return None
        raise ValueError("Retained DANE context asset points to a different source original")
    generic_context_candidate = bool(
        not explicit_context_url and _generic_retained_context_filename(url)
        and actual_kind == kind == "inputs-pdf"
        and (did == generic_context_original or _generic_context_archive_kind(db, did) == "context-pdf")
    )
    if generic_context_candidate:
        error_row = db.execute("SELECT error FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
        current_error = error_row[0] if error_row else None
        if not _generic_context_lifecycle(status, old_version, current_error, url, did, actual_day):
            raise ValueError("Retained DANE context input lifecycle is not an approved v14/v17 state")
        generic_context_binding = True
        generic_context_retry = status in ("failed", "pending") and old_version == VERSION
    long_spec = LONG_INPUT_PDF_REPAIRS.get(url)
    long_input_retry = False
    if (long_spec and long_spec["metadata_kind"] == "inputs-pdf"
            and (actual_kind, actual_day.isoformat(), did, records) ==
                ("inputs-pdf", long_spec["day"], long_spec["document_id"], long_spec["raw_rows"])
            and status in ("failed", "pending") and old_version == VERSION):
        error_row = db.execute("SELECT error FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
        allowed_errors = {
            "ValueError: Retained input PDF page count mismatch",
            WORK_DEFERRED_RETRY_ERROR,
            *long_spec.get("failed_retry_errors", ()),
        }
        if not error_row or error_row[0] not in allowed_errors:
            raise ValueError("Registered long input PDF retry state is not approved")
        retained_body = db.execute(
            "SELECT content FROM source_document WHERE id=%s", (did,),
        ).fetchone()
        if retained_body is None:
            raise ValueError("Registered long input PDF source body is missing")
        _assert_long_input_pdf_witness(
            url, did, actual_day, long_spec["pages"], records, bytes(retained_body[0] or b""),
        )
        long_input_retry = True
    registered_spec = _registered_v14_replacement_spec(url)
    if registered_spec and did != registered_spec["document_id"]:
        _registered_2012_replacement_state(
            db, url, day, (actual_kind, actual_day, did, status, old_version, records),
            registered_spec,
        )
        # Verified changed bodies go through the ordinary fetch/archive/parse path.
        return None
    feb2016_retry = (
        url == FEB2016_CONTEXT_URL and target_version == VERSION
        and actual_kind == "inputs-pdf" and actual_day.isoformat() == FEB2016_CONTEXT_DAY
        and did == FEB2016_CONTEXT_ID and status in ("failed", "pending")
        and old_version == VERSION and records == FEB2016_CONTEXT_RAW_ROWS
    )
    april2016_context_route = url == APR2016_CONTEXT_URL and target_version == VERSION
    april2016_context_retry = False
    april2016_context_binding = False
    if april2016_context_route and old_version == VERSION:
        if status not in ("failed", "pending", "complete"):
            raise ValueError("Retained April 2016 context asset has an unsupported lifecycle state")
        if ((actual_kind, actual_day.isoformat(), did, records) !=
                ("inputs-pdf", APR2016_CONTEXT_DAY, APR2016_CONTEXT_ID, APR2016_CONTEXT_RAW_ROWS)):
            raise ValueError("Retained April 2016 context asset identity differs")
        april2016_context_binding = True
        april2016_context_retry = status in ("failed", "pending")
        _assert_registered_v14_source_witness(db, url, _registered_v14_replacement_spec(url))
    elif april2016_context_route and status in ("failed", "pending"):
        raise ValueError("Retained April 2016 context asset has an unexpected processor version")
    aug2012_alias_route = url == AUG2012_ALIAS_ASSET_URL and target_version == VERSION
    aug2012_alias_retry = False
    if aug2012_alias_route and status in ("failed", "pending", "complete") and old_version == VERSION:
        if ((actual_kind, actual_day.isoformat(), did, records) !=
                ("inputs-pdf", AUG2012_ALIAS_DAY, AUG2012_ALIAS_ID, AUG2012_ALIAS_RAW_ROWS)):
            raise ValueError("Retained August 2012 failed asset identity differs")
        aug2012_alias_retry = status in ("failed", "pending")
        _assert_registered_v14_source_witness(db, url, _registered_v14_replacement_spec(url))
    elif aug2012_alias_route and status in ("failed", "pending"):
        raise ValueError("Retained August 2012 asset has an unexpected processor version")
    if feb2016_retry:
        _assert_registered_v14_source_witness(db, url, _registered_v14_replacement_spec(url))
        error = db.execute("SELECT error FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
        if not _approved_registered_retry_error(status, error[0] if error else None, FEB2016_CONTEXT_RETRY_ERROR):
            raise ValueError("Retained February 2016 retry asset error differs")
    if april2016_context_retry:
        error = db.execute("SELECT error FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
        if not _approved_registered_retry_error(status, error[0] if error else None, APR2016_CONTEXT_RETRY_ERROR):
            raise ValueError("Retained April 2016 retry asset error differs")
    if aug2012_alias_retry:
        error = db.execute("SELECT error FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
        if not _approved_registered_retry_error(status, error[0] if error else None, AUG2012_ALIAS_RETRY_ERROR):
            raise ValueError("Retained August 2012 retry asset error differs")
    retained_2012_spec = _registered_v14_replacement_spec(url)
    retained_2012_binding = False
    retained_2012_retry = False
    if retained_2012_spec and url in RETAINED_2012_CONTEXTS:
        if did != retained_2012_spec["document_id"]:
            _registered_2012_replacement_state(
                db, url, day, (actual_kind, actual_day, did, status, old_version, records),
                retained_2012_spec,
            )
            # A verified changed body remains on the ordinary URL fetch path.
            return None
        if status in ("failed", "pending") and old_version == VERSION:
            error = db.execute("SELECT error FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
            if ((actual_kind, actual_day.isoformat(), records) !=
                    ("inputs-pdf", retained_2012_spec["day"], retained_2012_spec["raw_rows"])
                    or not _approved_registered_retry_error(
                        status, error[0] if error else None, RETAINED_2012_RETRY_ERROR
                    )):
                raise ValueError("Retained November/December 2012 retry lifecycle differs")
            _assert_registered_v14_source_witness(db, url, retained_2012_spec)
            retained_2012_binding = True
            retained_2012_retry = True
    retained_2013_spec = RETAINED_2013_CONTEXTS.get(url)
    retained_2013_binding = False
    retained_2013_retry = False
    if retained_2013_spec is not None:
        did_13, day_13, pages_13, bytes_13, raw_13, typed_13, unresolved_13, title_13, filename_13 = retained_2013_spec
        if did != did_13:
            _registered_2013_replacement_state(
                db, url, day, (actual_kind, actual_day, did, status, old_version, records),
                retained_2013_spec,
            )
            # A validated replacement continues through ordinary conditional
            # HTTP, archive, parse, and v17 completion; it is never returned as
            # the original v14 body and never uses the immutable-v14 subset path.
            return None
        error = db.execute("SELECT error FROM ingestion_asset WHERE url=%s", (url,)).fetchone()[0]
        exact_identity = (actual_kind, actual_day.isoformat(), did) == ("inputs-pdf", day_13, did_13)
        v14_state = (
            status in ("complete", "pending") and old_version == OLD_VERSION
            and records == raw_13 and error == RETAINED_2013_V14_ASSET_ERRORS[url]
        )
        v17_retry_state = (
            old_version == VERSION and records == raw_13
            and _approved_registered_retry_error(status, error, RETAINED_2013_CONTEXT_RETRY_ERROR)
        )
        exact_asset = exact_identity and (v14_state or v17_retry_state)
        if ((actual_kind, actual_day.isoformat(), did) != ("inputs-pdf", day_13, did_13)
                or not exact_asset):
            # A complete v17 asset is handled by the ordinary already-current
            # worker path below. A registered prior source in any other state
            # must match its explicitly recorded lifecycle exactly.
            if not (status == "complete" and old_version == VERSION
                    and records == RETAINED_2013_NEW_COHORTS[url][0]
                    and (actual_kind, actual_day.isoformat(), did) == ("inputs-pdf", day_13, did_13)):
                raise ValueError("Retained 2013 context input asset identity or lifecycle differs")
        else:
            retained_2013_binding = True
            retained_2013_retry = v17_retry_state
    if retained_2013_retry:
        error = db.execute("SELECT error FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
        if not _approved_registered_retry_error(
            status, error[0] if error else None, RETAINED_2013_CONTEXT_RETRY_ERROR
        ):
            raise ValueError("Retained 2013 context input retry error differs")
    if not (feb2016_retry or april2016_context_retry or aug2012_alias_retry or retained_2012_retry or retained_2013_retry or generic_context_retry or long_input_retry) and (
        old_version != OLD_VERSION or status not in ("complete", "processed", "pending")
    ):
        return None
    if day is None or not hasattr(day, "isoformat"):
        raise ValueError("Retained input source date missing")
    if actual_kind != kind or actual_day != day:
        raise ValueError("Retained input kind/source date conflicts with asset")
    if not did or len(did) != 64:
        raise ValueError("Retained input original pointer missing")
    original = db.execute(
        """SELECT kind,source_url,media_type,page_count,content,metadata
           FROM source_document WHERE id=%s""", (did,)
    ).fetchone()
    if original is None:
        raise ValueError("Retained input original missing")
    source_kind, source_url, media, page_count, content, metadata = original
    body = bytes(content or b"")
    context_case = CONTEXT_ORIGINALS.get(url)
    context_ok = bool(context_case and (did, day.isoformat(), page_count, records) == context_case)
    if generic_context_binding:
        bound = db.execute(
            "SELECT title,publisher,reference_period FROM source_document WHERE id=%s", (did,),
        ).fetchone()
        context_ok = bool(bound and _generic_context_metadata_ok(
            url, day, page_count, metadata, bound[0], bound[1], bound[2], did
        ))
        if not context_ok:
            raise ValueError("Retained DANE context input source metadata differs")
        if did == JAN2019_CONTEXT_DID:
            jan_witness = _generic_context_v14_witness(db, url, day)
            if (jan_witness is None or jan_witness["document_id"] != did
                    or jan_witness["vector_sha256"] != JAN2019_CONTEXT_OLD_VECTOR_SHA256):
                raise ValueError("January 2019 retained v14 vector differs")
    if retained_2013_binding:
        did_13, day_13, pages_13, bytes_13, raw_13, typed_13, unresolved_13, title_13, filename_13 = retained_2013_spec
        bound_13 = db.execute("SELECT title,publisher,reference_period FROM source_document WHERE id=%s", (did,)).fetchone()
        context_ok = ((did, day.isoformat(), page_count, records) == (did_13, day_13, pages_13, raw_13)
                      and metadata == {"retention": "permanent", "ingestion_kind": "context-pdf", "original_filename": filename_13}
                      and len(body) == bytes_13 and bound_13 == (title_13, "DANE", day_13))
        if not context_ok:
            raise ValueError("Retained 2013 context input source metadata differs")
    if retained_2012_binding:
        spec = retained_2012_spec
        bound = db.execute("SELECT title,publisher,reference_period FROM source_document WHERE id=%s", (did,)).fetchone()
        if ((did, day.isoformat(), page_count, records) !=
                (spec["document_id"], spec["day"], spec["pages"], spec["raw_rows"])
                or metadata != spec["metadata"]
                or bound != (spec["title"], "DANE", spec["day"])
                or len(body) != spec["bytes"]):
            raise ValueError("Retained November/December 2012 source metadata differs")
    if feb2016_retry:
        context_ok = (
            (did, day.isoformat(), page_count, records)
            == (FEB2016_CONTEXT_ID, FEB2016_CONTEXT_DAY, FEB2016_CONTEXT_PAGES, FEB2016_CONTEXT_RAW_ROWS)
            and metadata == {
                "retention": "permanent", "ingestion_kind": "context-pdf",
                "original_filename": "Bol_Insumos_feb_2016.pdf",
            }
            and len(body) == 1636900
        )
        bound = db.execute(
            "SELECT title,publisher,reference_period FROM source_document WHERE id=%s",
            (did,),
        ).fetchone()
        if bound != ("DANE - Bol_Insumos_feb_2016.pdf", "DANE", "2016-02-29"):
            raise ValueError("Retained February 2016 source metadata differs")
    if april2016_context_binding:
        context_ok = ((did, day.isoformat(), page_count, records) ==
                      (APR2016_CONTEXT_ID, APR2016_CONTEXT_DAY, APR2016_CONTEXT_PAGES, APR2016_CONTEXT_RAW_ROWS)
                      and metadata == APR2016_CONTEXT_METADATA and len(body) == APR2016_CONTEXT_BYTES)
        bound = db.execute(
            "SELECT title,publisher,reference_period FROM source_document WHERE id=%s", (did,),
        ).fetchone()
        if not context_ok or bound != (APR2016_CONTEXT_TITLE, "DANE", APR2016_CONTEXT_DAY):
            raise ValueError("Retained April 2016 source metadata differs")
    if aug2012_alias_retry:
        context_ok = ((did, day.isoformat(), page_count, records) ==
                      (AUG2012_ALIAS_ID, AUG2012_ALIAS_DAY, AUG2012_ALIAS_PAGES, AUG2012_ALIAS_RAW_ROWS))
        bound = db.execute(
            "SELECT title,publisher,reference_period FROM source_document WHERE id=%s", (did,),
        ).fetchone()
        if (bound != (AUG2012_ALIAS_TITLE, "DANE", AUG2012_ALIAS_DAY)
                or metadata != {"ingestion_kind": "inputs-pdf", "original_filename": AUG2012_ALIAS_FILENAME,
                                "retention": "permanent"}
                or len(body) != AUG2012_ALIAS_BYTES):
            raise ValueError("Retained August 2012 source metadata differs")
    expected_source_url = (AUG2012_ALIAS_SOURCE_URL if aug2012_alias_retry else
                           _generic_context_source_url(url, did) if generic_context_binding else url)
    if (source_kind != "original" or source_url != expected_source_url or media != "application/pdf"
            or (metadata.get("ingestion_kind") != kind
                and not (metadata.get("ingestion_kind") == "context-pdf" and context_ok))
            or not body.startswith(b"%PDF-")
            or not 0 < len(body) <= MAX_PDF_BYTES
            or hashlib.sha256(body).hexdigest() != did):
        raise ValueError("Retained input original identity/bytes mismatch")
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        actual_pages = len(pdf.pages)
    if not 0 < actual_pages <= MAX_PDF_PAGES or page_count != actual_pages:
        raise ValueError("Retained input PDF page count mismatch")
    _assert_long_input_pdf_witness(url, did, day, page_count, records, body)
    long_spec = LONG_INPUT_PDF_REPAIRS.get(url)
    if (long_spec and long_spec["metadata_kind"] == "inputs-pdf"
            and did == long_spec["document_id"]):
        _assert_long_input_pdf_v14_witness(db, url, long_spec)
    checkpoint = db.execute(
        """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
           AND processor_version=%s AND step='inputs-pdf:published'""",
        (did, OLD_VERSION),
    ).fetchone()
    zero_context = records == 0 and status in ("processed", "pending") and checkpoint is None
    if checkpoint is None and not zero_context:
        raise ValueError("Retained input v14 publication checkpoint missing")
    cohort = db.execute(
        """SELECT count(*),count(*) FILTER (WHERE series='dane-inputs-pdf'),
           count(*) FILTER (WHERE series='dane-inputs-pdf-unresolved')
           FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s""",
        (did, OLD_VERSION),
    ).fetchone()
    if feb2016_retry:
        if checkpoint is None or checkpoint[0] != FEB2016_CONTEXT_PUBLISHED_ROWS or tuple(cohort) != (
            FEB2016_CONTEXT_RAW_ROWS, FEB2016_CONTEXT_PUBLISHED_ROWS,
            FEB2016_CONTEXT_UNRESOLVED_ROWS,
        ):
            raise ValueError("Retained February 2016 v14 rows/checkpoint are not the exact 8177+602 cohort")
    elif april2016_context_binding:
        if checkpoint is None or checkpoint[0] != APR2016_CONTEXT_PUBLISHED_ROWS or tuple(cohort) != (
            APR2016_CONTEXT_RAW_ROWS, APR2016_CONTEXT_PUBLISHED_ROWS, APR2016_CONTEXT_UNRESOLVED_ROWS,
        ):
            raise ValueError("Retained April 2016 v14 rows/checkpoint are not the exact 9179-row cohort")
    elif aug2012_alias_retry:
        if checkpoint is None or checkpoint[0] != AUG2012_ALIAS_PUBLISHED_ROWS or tuple(cohort) != (
            AUG2012_ALIAS_RAW_ROWS, AUG2012_ALIAS_PUBLISHED_ROWS, AUG2012_ALIAS_UNRESOLVED_ROWS,
        ):
            raise ValueError("Retained August 2012 v14 rows/checkpoint are not the exact 7891+30 cohort")
    elif (cohort[0] != records or cohort[1] != (checkpoint[0] if checkpoint else 0)
          or cohort[1] + cohort[2] != cohort[0]):
        raise ValueError("Retained input v14 row/checkpoint cohort mismatch")
    if retained_2013_binding and tuple(cohort) != (retained_2013_spec[4], retained_2013_spec[5], retained_2013_spec[6]):
        raise ValueError("Retained 2013 v14 typed/unresolved cohort differs")
    newer_checkpoint = db.execute(
        """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
           AND step='inputs-pdf:published' AND processor_version ~ '^inputs-pdf-v[0-9]+$'
           AND substring(processor_version from '([0-9]+)$')::integer>=17 LIMIT 1""",
        (did,),
    ).fetchone()
    if newer_checkpoint:
        if feb2016_retry or april2016_context_retry or aug2012_alias_retry or retained_2012_retry or retained_2013_binding or generic_context_retry or long_input_retry:
            raise ValueError("Retained-source replay has an unexpected v17 completion checkpoint")
        return None
    return body


def assert_retained_v14_binding_locked(db, url, kind, day, did, old_count):
    """Lock only the mutable asset; rebind immutable original/old checkpoint."""
    if day is None or not hasattr(day, "isoformat"):
        raise ValueError("Retained input source date missing during publication")
    asset = db.execute(
        """SELECT kind,observed_on,document_id,status,processor_version,records,error
        FROM ingestion_asset WHERE url=%s FOR UPDATE""", (url,)
    ).fetchone()
    feb2016_retry = (
        url == FEB2016_CONTEXT_URL and did == FEB2016_CONTEXT_ID
        and day.isoformat() == FEB2016_CONTEXT_DAY and old_count == FEB2016_CONTEXT_RAW_ROWS
    )
    april2016_context_retry = (
        url == APR2016_CONTEXT_URL and did == APR2016_CONTEXT_ID
        and day.isoformat() == APR2016_CONTEXT_DAY and old_count == APR2016_CONTEXT_RAW_ROWS
    )
    aug2012_alias_retry = (
        url == AUG2012_ALIAS_ASSET_URL and did == AUG2012_ALIAS_ID
        and day.isoformat() == AUG2012_ALIAS_DAY and old_count == AUG2012_ALIAS_RAW_ROWS
    )
    retained_2013_spec = RETAINED_2013_CONTEXTS.get(url)
    retained_2013_registered = bool(
        retained_2013_spec and did == retained_2013_spec[0]
        and day.isoformat() == retained_2013_spec[1]
    )
    retained_2013_identity = bool(
        retained_2013_registered and old_count == retained_2013_spec[4]
    )
    retained_2013_v14_states = {
        (kind, day, did, state, OLD_VERSION, retained_2013_spec[4],
         RETAINED_2013_V14_ASSET_ERRORS[url])
        for state in ("complete", "pending")
    } if retained_2013_identity else set()
    retained_2013_v17_states = (
        {(kind, day, did, "failed", VERSION, retained_2013_spec[4], RETAINED_2013_CONTEXT_RETRY_ERROR),
         (kind, day, did, "pending", VERSION, retained_2013_spec[4], RETAINED_2013_CONTEXT_RETRY_ERROR),
         (kind, day, did, "pending", VERSION, retained_2013_spec[4], WORK_DEFERRED_RETRY_ERROR)}
        if retained_2013_identity else set()
    )
    retained_2013_binding = bool(retained_2013_identity and asset in (
        retained_2013_v14_states | retained_2013_v17_states
    ))
    retained_2012_spec = _registered_v14_replacement_spec(url)
    retained_2012_identity = bool(
        retained_2012_spec and url in RETAINED_2012_CONTEXTS
        and did == retained_2012_spec["document_id"]
        and day.isoformat() == retained_2012_spec["day"]
        and old_count == retained_2012_spec["raw_rows"]
    )
    retained_2012_states = (
        {(kind, day, did, "failed", VERSION, retained_2012_spec["raw_rows"], RETAINED_2012_RETRY_ERROR),
         (kind, day, did, "pending", VERSION, retained_2012_spec["raw_rows"], RETAINED_2012_RETRY_ERROR),
         (kind, day, did, "pending", VERSION, retained_2012_spec["raw_rows"], WORK_DEFERRED_RETRY_ERROR)}
        if retained_2012_identity else set()
    )
    retained_2012_binding = bool(retained_2012_identity and asset in retained_2012_states)
    explicit_context_url = (
        url in CONTEXT_ORIGINALS or url in RETAINED_2013_CONTEXTS
        or url in RETAINED_2012_CONTEXTS
        or url in (FEB2016_CONTEXT_URL, APR2016_CONTEXT_URL, AUG2012_ALIAS_ASSET_URL)
    )
    generic_context_binding = False
    generic_context_retry = False
    generic_context_original = (
        _generic_context_original_id(db, url) if not explicit_context_url else None
    )
    if generic_context_original is not None and did != generic_context_original:
        replacement_old = _generic_context_replacement_old_did(db, did)
        if replacement_old != generic_context_original:
            raise ValueError("Retained DANE context asset points to a different source original")
    if (not explicit_context_url and _generic_retained_context_filename(url)
            and asset is not None
            and (did == generic_context_original or _generic_context_archive_kind(db, did) == "context-pdf")):
        generic_context_binding = bool(
            asset[:3] == (kind, day, did)
            and asset[4] in (OLD_VERSION, VERSION)
            and asset[5] == old_count
            and _generic_context_lifecycle(asset[3], asset[4], asset[6], url, did, day)
        )
        generic_context_retry = generic_context_binding and asset[4] == VERSION and asset[3] in ("failed", "pending")
        if not generic_context_binding:
            raise ValueError("Retained DANE context input lifecycle changed during publication")
    long_spec = LONG_INPUT_PDF_REPAIRS.get(url)
    long_input_retry = False
    if (long_spec and long_spec["metadata_kind"] == "inputs-pdf"
            and (kind, day.isoformat(), did, old_count) ==
                ("inputs-pdf", long_spec["day"], long_spec["document_id"], long_spec["raw_rows"])):
        long_v17_states = {
            (kind, day, did, "failed", VERSION, old_count,
             "ValueError: Retained input PDF page count mismatch"),
            (kind, day, did, "pending", VERSION, old_count,
             "ValueError: Retained input PDF page count mismatch"),
            (kind, day, did, "pending", VERSION, old_count, WORK_DEFERRED_RETRY_ERROR),
        }
        for error in long_spec.get("failed_retry_errors", ()):
            long_v17_states.add((kind, day, did, "failed", VERSION, old_count, error))
            long_v17_states.add((kind, day, did, "pending", VERSION, old_count, error))
        if asset in long_v17_states:
            _assert_long_input_pdf_v14_witness(db, url, long_spec)
            long_input_retry = True
        elif not (asset is not None and asset[:6] ==
                  (kind, day, did, "pending", OLD_VERSION, old_count)):
            raise ValueError("Registered long input PDF asset lifecycle changed during parsing")
    if retained_2013_registered and (
        not retained_2013_identity
        or asset not in (retained_2013_v14_states | retained_2013_v17_states)
    ):
        raise ValueError("Retained 2013 input asset lifecycle is not an approved v14/v17 state")
    if (retained_2012_spec and url in RETAINED_2012_CONTEXTS
            and did == retained_2012_spec["document_id"]
            and (not retained_2012_identity or asset not in retained_2012_states)):
        raise ValueError("Retained November/December 2012 asset lifecycle is not the approved retry state")
    retained_2013_retry = bool(retained_2013_binding and asset in retained_2013_v17_states)
    def retry_asset_states(raw_count, initial_error):
        return {
            (kind, day, did, "failed", VERSION, raw_count, initial_error),
            (kind, day, did, "pending", VERSION, raw_count, initial_error),
            (kind, day, did, "pending", VERSION, raw_count, WORK_DEFERRED_RETRY_ERROR),
        }
    expected_assets = (
        retry_asset_states(FEB2016_CONTEXT_RAW_ROWS, FEB2016_CONTEXT_RETRY_ERROR)
        if feb2016_retry else
        retry_asset_states(APR2016_CONTEXT_RAW_ROWS, APR2016_CONTEXT_RETRY_ERROR)
        if april2016_context_retry else
        retry_asset_states(AUG2012_ALIAS_RAW_ROWS, AUG2012_ALIAS_RETRY_ERROR)
        if aug2012_alias_retry else
        long_v17_states
        if long_input_retry else
        retained_2012_states
        if retained_2012_binding else
        retained_2013_v14_states | retained_2013_v17_states
        if retained_2013_binding else None
    )
    if asset is None:
        raise ValueError("Retained input asset missing during publication")
    if generic_context_binding:
        pass
    elif ((asset not in expected_assets) if (feb2016_retry or april2016_context_retry or aug2012_alias_retry or long_input_retry or retained_2012_binding or retained_2013_retry or retained_2013_binding) else
          asset[:6] != (kind, day, did, "pending", OLD_VERSION, old_count)):
        raise ValueError("Retained input asset pointer/status/version changed during parsing")
    source = db.execute(
        """SELECT kind,source_url,media_type,page_count,content,metadata
        FROM source_document WHERE id=%s""", (did,)
    ).fetchone()
    if source is None:
        raise ValueError("Retained input original missing during publication")
    source_kind, source_url, media, pages, content, metadata = source
    body = bytes(content or b"")
    context = CONTEXT_ORIGINALS.get(url)
    feb2016_retry = (
        url == FEB2016_CONTEXT_URL and did == FEB2016_CONTEXT_ID
        and day.isoformat() == FEB2016_CONTEXT_DAY and old_count == FEB2016_CONTEXT_RAW_ROWS
    )
    if feb2016_retry:
        bound = db.execute(
            "SELECT title,publisher,reference_period FROM source_document WHERE id=%s",
            (did,),
        ).fetchone()
        if (bound != ("DANE - Bol_Insumos_feb_2016.pdf", "DANE", "2016-02-29")
                or metadata != {
                    "retention": "permanent", "ingestion_kind": "context-pdf",
                    "original_filename": "Bol_Insumos_feb_2016.pdf",
                }
                or len(body) != 1636900):
            raise ValueError("Retained February 2016 source metadata changed during publication")
        context = (FEB2016_CONTEXT_ID, FEB2016_CONTEXT_DAY,
                   FEB2016_CONTEXT_PAGES, FEB2016_CONTEXT_RAW_ROWS)
    if april2016_context_retry:
        bound = db.execute(
            "SELECT title,publisher,reference_period FROM source_document WHERE id=%s", (did,),
        ).fetchone()
        if (bound != (APR2016_CONTEXT_TITLE, "DANE", APR2016_CONTEXT_DAY)
                or metadata != APR2016_CONTEXT_METADATA or len(body) != APR2016_CONTEXT_BYTES):
            raise ValueError("Retained April 2016 source metadata changed during publication")
        context = (APR2016_CONTEXT_ID, APR2016_CONTEXT_DAY,
                   APR2016_CONTEXT_PAGES, APR2016_CONTEXT_RAW_ROWS)
    if aug2012_alias_retry:
        bound = db.execute(
            "SELECT title,publisher,reference_period FROM source_document WHERE id=%s", (did,),
        ).fetchone()
        if (bound != (AUG2012_ALIAS_TITLE, "DANE", AUG2012_ALIAS_DAY)
                or metadata != {"ingestion_kind": "inputs-pdf", "original_filename": AUG2012_ALIAS_FILENAME,
                                "retention": "permanent"}
                or len(body) != AUG2012_ALIAS_BYTES):
            raise ValueError("Retained August 2012 source metadata changed during publication")
        context = (AUG2012_ALIAS_ID, AUG2012_ALIAS_DAY, AUG2012_ALIAS_PAGES, AUG2012_ALIAS_RAW_ROWS)
    if retained_2013_binding:
        did_13, day_13, pages_13, bytes_13, raw_13, typed_13, unresolved_13, title_13, filename_13 = retained_2013_spec
        bound_13 = db.execute("SELECT title,publisher,reference_period FROM source_document WHERE id=%s", (did,)).fetchone()
        if (bound_13 != (title_13, "DANE", day_13) or metadata != {"retention": "permanent", "ingestion_kind": "context-pdf", "original_filename": filename_13}
                or len(body) != bytes_13):
            raise ValueError("Retained 2013 context source metadata changed during publication")
        context = (did_13, day_13, pages_13, raw_13)
    if retained_2012_binding:
        spec = retained_2012_spec
        bound = db.execute("SELECT title,publisher,reference_period FROM source_document WHERE id=%s", (did,)).fetchone()
        if ((did, day.isoformat(), pages, old_count) !=
                (spec["document_id"], spec["day"], spec["pages"], spec["raw_rows"])
                or bound != (spec["title"], "DANE", spec["day"])
                or metadata != spec["metadata"] or len(body) != spec["bytes"]):
            raise ValueError("Retained November/December 2012 source metadata changed during publication")
        context = (did, spec["day"], spec["pages"], spec["raw_rows"])
    if generic_context_binding:
        bound = db.execute(
            "SELECT title,publisher,reference_period FROM source_document WHERE id=%s", (did,),
        ).fetchone()
        if not bound or not _generic_context_metadata_ok(url, day, pages, metadata, *bound, did):
            raise ValueError("Retained DANE context source metadata changed during publication")
        if did == JAN2019_CONTEXT_DID:
            jan_witness = _generic_context_v14_witness(db, url, day)
            if (jan_witness is None or jan_witness["document_id"] != did
                    or jan_witness["vector_sha256"] != JAN2019_CONTEXT_OLD_VECTOR_SHA256):
                raise ValueError("January 2019 retained v14 vector changed during publication")
        context = (did, day.isoformat(), pages, old_count)
    expected_source_url = (AUG2012_ALIAS_SOURCE_URL if aug2012_alias_retry else
                           _generic_context_source_url(url, did) if generic_context_binding else url)
    if (source_kind != "original" or source_url != expected_source_url or media != "application/pdf"
            or not pages or not 0 < len(body) <= MAX_PDF_BYTES
            or hashlib.sha256(body).hexdigest() != did
            or (metadata.get("ingestion_kind") != kind and not (
                metadata.get("ingestion_kind") == "context-pdf" and context
                and (did, day.isoformat(), pages, old_count) == context))):
        raise ValueError("Retained input original metadata changed during publication")
    checkpoint = db.execute(
        """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
        AND processor_version=%s AND step='inputs-pdf:published'""",
        (did, OLD_VERSION),
    ).fetchone()
    cohort = db.execute(
        """SELECT count(*),count(*) FILTER (WHERE series='dane-inputs-pdf'),
           count(*) FILTER (WHERE series='dane-inputs-pdf-unresolved')
           FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s""",
        (did, OLD_VERSION),
    ).fetchone()
    expected_old_checkpoint = checkpoint[0] if checkpoint else 0
    if (cohort[0] != old_count or cohort[1] != expected_old_checkpoint
            or cohort[1] + cohort[2] != cohort[0]
            or (not checkpoint and old_count != 0)
            or (feb2016_retry and (not checkpoint or cohort != (
                FEB2016_CONTEXT_RAW_ROWS, FEB2016_CONTEXT_PUBLISHED_ROWS,
                FEB2016_CONTEXT_UNRESOLVED_ROWS)))
            or (april2016_context_retry and cohort != (
                APR2016_CONTEXT_RAW_ROWS, APR2016_CONTEXT_PUBLISHED_ROWS,
                APR2016_CONTEXT_UNRESOLVED_ROWS))
            or (aug2012_alias_retry and cohort != (
                AUG2012_ALIAS_RAW_ROWS, AUG2012_ALIAS_PUBLISHED_ROWS,
                AUG2012_ALIAS_UNRESOLVED_ROWS))
            or (retained_2012_binding and cohort != (
                retained_2012_spec["raw_rows"], retained_2012_spec["typed_rows"],
                retained_2012_spec["unresolved_rows"]))
            or (retained_2013_binding and cohort != (retained_2013_spec[4], retained_2013_spec[5], retained_2013_spec[6]))):
        raise ValueError("Retained input old publication checkpoint/typed cohort changed")
    if feb2016_retry or april2016_context_retry or aug2012_alias_retry or retained_2012_binding or retained_2013_binding or generic_context_retry:
        newer = db.execute(
            "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND step='inputs-pdf:published' "
            "AND processor_version ~ '^inputs-pdf-v[0-9]+$' "
            "AND substring(processor_version from '([0-9]+)$')::integer>=17 LIMIT 1", (did,),
        ).fetchone()
        if newer:
            raise ValueError("Failed retained-source replay has an unexpected v17 completion checkpoint")


def assert_native_zero_input_context(data, did):
    """Allow readable non-price context PDFs to remain processed with zero rows.

    The parser itself raises for a recognized but unverifiable monetary table.
    This additional page pass refuses unreadable/raster price-like pages and
    table headings missed by its case-sensitive fast page selector.
    """
    from .pdf_sources import native_price_page_failure
    if hashlib.sha256(data).hexdigest() != did or not data.startswith(b"%PDF-"):
        raise ValueError("Zero-row input PDF source bytes mismatch")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not 0 < len(pdf.pages) <= MAX_PDF_PAGES:
            raise ValueError("Zero-row input PDF page count unsupported")
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if native_price_page_failure(page, text, False):
                raise ValueError(f"Zero-row input PDF page {number} needs native/OCR review")
            if (re.search(r"\bmercados\b", text, re.IGNORECASE)
                    and re.search(r"\bprecio\s+medio\b", text, re.IGNORECASE)):
                raise ValueError(f"Zero-row input PDF page {number} has an unverified monetary table")


def assert_retained_context_replacement_vectors(db, old_did, new_rows):
    """Require a changed-body v17 parse to preserve every v14 source row."""
    old_rows = db.execute(
        f"SELECT {ROW_FIELDS} FROM historical_price WHERE document_id=%s "
        "AND details->>'parser_version'=%s ORDER BY source_locator",
        (old_did, OLD_VERSION),
    ).fetchall()
    expected = {_normalized_old(row)[0]: _normalized_old(row) for row in old_rows}
    parsed = {row[0]: _as_vector(row) for row in new_rows}
    if len(expected) != len(old_rows) or len(parsed) != len(new_rows):
        raise ValueError("DANE replacement has duplicate or incomplete source locators")
    for locator, row in expected.items():
        if parsed.get(locator) != row:
            raise ValueError("DANE replacement changed an immutable v14 source row: " + locator)
    return len(expected)


def assert_retained_v14_vectors(db, did, old_rows, new_rows, *, complete=False):
    """Require a full old cohort and exact v17 supersets before any COPY."""
    old = {_normalized_old(row)[0]: _normalized_old(row) for row in old_rows}
    new = {row[0]: _as_vector(row) for row in new_rows}
    if len(old) != len(old_rows) or len(new) != len(new_rows):
        raise ValueError("Duplicate or empty input PDF locator")
    if did == FEB2016_CONTEXT_ID:
        expected_series = {"dane-inputs-pdf": 8177, "dane-inputs-pdf-unresolved": 602}
        if (len(old_rows) != FEB2016_CONTEXT_RAW_ROWS or len(new_rows) != FEB2016_CONTEXT_RAW_ROWS
                or {series: sum(row[1] == series for row in old_rows) for series in expected_series} != expected_series
                or {series: sum(row[1] == series for row in new_rows) for series in expected_series} != expected_series):
            raise ValueError("Retained February 2016 full source vector lost the exact 8177+602 split")
    if did == APR2016_CONTEXT_ID:
        expected_series = {"dane-inputs-pdf": APR2016_CONTEXT_PUBLISHED_ROWS,
                           "dane-inputs-pdf-unresolved": APR2016_CONTEXT_UNRESOLVED_ROWS}
        if (len(old_rows) != APR2016_CONTEXT_RAW_ROWS or len(new_rows) != APR2016_CONTEXT_RAW_ROWS
                or {series: sum(row[1] == series for row in old_rows) for series in expected_series} != expected_series
                or {series: sum(row[1] == series for row in new_rows) for series in expected_series} != expected_series):
            raise ValueError("Retained April 2016 full source vector lost the exact 9179-row cohort")
    retained_url = next((url for url, spec in RETAINED_2013_CONTEXTS.items() if spec[0] == did), None)
    spec_2013 = RETAINED_2013_CONTEXTS.get(retained_url) if retained_url else None
    if spec_2013 is not None:
        expected_new = RETAINED_2013_NEW_COHORTS[retained_url]
        if (len(old_rows) != spec_2013[4] or len(new_rows) != expected_new[0]
                or {"dane-inputs-pdf": sum(row[1] == "dane-inputs-pdf" for row in old_rows),
                    "dane-inputs-pdf-unresolved": sum(row[1] == "dane-inputs-pdf-unresolved" for row in old_rows)} !=
                   {"dane-inputs-pdf": spec_2013[5], "dane-inputs-pdf-unresolved": spec_2013[6]}
                or {"dane-inputs-pdf": sum(row[1] == "dane-inputs-pdf" for row in new_rows),
                    "dane-inputs-pdf-unresolved": sum(row[1] == "dane-inputs-pdf-unresolved" for row in new_rows)} !=
                   {"dane-inputs-pdf": expected_new[1], "dane-inputs-pdf-unresolved": expected_new[2]}
                or _retained_vector_sha256(new_rows) != expected_new[3]):
            raise ValueError("Retained 2013 full source vector differs from its exact source-bound v17 oracle")
    if did == AUG2012_ALIAS_ID:
        expected_series = {"dane-inputs-pdf": AUG2012_ALIAS_PUBLISHED_ROWS,
                           "dane-inputs-pdf-unresolved": AUG2012_ALIAS_UNRESOLVED_ROWS}
        if (len(old_rows) != AUG2012_ALIAS_RAW_ROWS or len(new_rows) != AUG2012_ALIAS_RAW_ROWS
                or {series: sum(row[1] == series for row in old_rows) for series in expected_series} != expected_series
                or {series: sum(row[1] == series for row in new_rows) for series in expected_series} != expected_series):
            raise ValueError("Retained August 2012 full source vector lost the exact 7891+30 split")
    for loc, row in old.items():
        if new.get(loc) != row:
            raise ValueError("v17 changed an immutable v14 input row: " + loc)
    found_old = db.execute(
        f"SELECT {ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",
        (did, OLD_VERSION),
    ).fetchall()
    if len(found_old) != len(old_rows) or {
        _normalized_old(row)[0]: _normalized_old(row) for row in found_old
    } != old:
        raise ValueError("Stored v14 input cohort differs from original")
    found_new = db.execute(
        f"SELECT {ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",
        (did, VERSION),
    ).fetchall()
    if complete and len(found_new) != len(new_rows):
        raise ValueError("Stored v17 input cohort is incomplete")
    for row in found_new:
        if new.get(row[0]) != _as_vector(row):
            raise ValueError("Stored v17 input row conflicts with original")
    return len(new)


def assert_v17_existing_rows(db, did, new_rows, *, complete=False):
    """Guard ON CONFLICT DO NOTHING against a changed same-locator price."""
    new = {row[0]: _as_vector(row) for row in new_rows}
    if len(new) != len(new_rows):
        raise ValueError("Incomplete or duplicated v17 source rows")
    found = db.execute(
        f"SELECT {ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",
        (did, VERSION),
    ).fetchall()
    if complete and len(found) != len(new_rows):
        raise ValueError("Stored v17 input cohort is incomplete")
    for row in found:
        if new.get(row[0]) != _as_vector(row):
            raise ValueError("Stored v17 input row conflicts with original")
    return len(found)


def _registered_v14_replacement_spec(url):
    """Describe one exact old source, normalizing its metadata conventions."""
    if url == FEB2016_CONTEXT_URL:
        return {
            "document_id": FEB2016_CONTEXT_ID, "day": FEB2016_CONTEXT_DAY,
            "pages": FEB2016_CONTEXT_PAGES, "bytes": 1636900,
            "raw_rows": FEB2016_CONTEXT_RAW_ROWS, "typed_rows": FEB2016_CONTEXT_PUBLISHED_ROWS,
            "unresolved_rows": FEB2016_CONTEXT_UNRESOLVED_ROWS,
            "title": "DANE - Bol_Insumos_feb_2016.pdf",
            "filename": "Bol_Insumos_feb_2016.pdf",
            "metadata": {"retention": "permanent", "ingestion_kind": "context-pdf",
                         "original_filename": "Bol_Insumos_feb_2016.pdf"},
            "source_url": FEB2016_CONTEXT_URL,
            "old_vector_sha256": FEB2016_CONTEXT_OLD_VECTOR_SHA256,
        }
    if url == APR2016_CONTEXT_URL:
        return {
            "document_id": APR2016_CONTEXT_ID, "day": APR2016_CONTEXT_DAY,
            "pages": APR2016_CONTEXT_PAGES, "bytes": APR2016_CONTEXT_BYTES,
            "raw_rows": APR2016_CONTEXT_RAW_ROWS, "typed_rows": APR2016_CONTEXT_PUBLISHED_ROWS,
            "unresolved_rows": APR2016_CONTEXT_UNRESOLVED_ROWS,
            "title": APR2016_CONTEXT_TITLE, "filename": "Bol_Insumos_abr_2016.pdf",
            "metadata": APR2016_CONTEXT_METADATA, "source_url": APR2016_CONTEXT_URL,
            "old_vector_sha256": APR2016_CONTEXT_OLD_VECTOR_SHA256,
        }
    retained_2013 = RETAINED_2013_CONTEXTS.get(url)
    if retained_2013:
        did, day, pages, size, raw, typed, unresolved, title, filename = retained_2013
        return {
            "document_id": did, "day": day, "pages": pages, "bytes": size,
            "raw_rows": raw, "typed_rows": typed, "unresolved_rows": unresolved,
            "title": title, "filename": filename,
            "metadata": {"retention": "permanent", "ingestion_kind": "context-pdf",
                         "original_filename": filename},
            "source_url": url,
            "old_vector_sha256": RETAINED_2013_OLD_VECTOR_SHA256[url],
        }
    retained_2012 = RETAINED_2012_CONTEXTS.get(url)
    if retained_2012:
        return {
            **retained_2012,
            "typed_rows": retained_2012.get("typed_rows", retained_2012.get("published_rows")),
            "source_url": url,
        }
    if url == AUG2012_ALIAS_ASSET_URL:
        return {
            "document_id": AUG2012_ALIAS_ID, "day": AUG2012_ALIAS_DAY,
            "pages": AUG2012_ALIAS_PAGES, "bytes": AUG2012_ALIAS_BYTES,
            "raw_rows": AUG2012_ALIAS_RAW_ROWS, "typed_rows": AUG2012_ALIAS_PUBLISHED_ROWS,
            "unresolved_rows": AUG2012_ALIAS_UNRESOLVED_ROWS,
            "title": AUG2012_ALIAS_TITLE, "filename": AUG2012_ALIAS_FILENAME,
            "metadata": {"retention": "permanent", "ingestion_kind": "inputs-pdf",
                         "original_filename": AUG2012_ALIAS_FILENAME},
            "source_url": AUG2012_ALIAS_SOURCE_URL,
            "old_vector_sha256": "661aa275ed7f3b1390c7f6e1c17671820bb45225a33d009f49153f749275e3ff",
        }
    return None


def _assert_registered_v14_source_witness(db, url, spec):
    source = db.execute(
        """SELECT kind,source_url,media_type,page_count,content,metadata,
                  title,publisher,reference_period
           FROM source_document WHERE id=%s""", (spec["document_id"],)
    ).fetchone()
    if source is None:
        raise ValueError("Registered v14 replacement witness is missing")
    kind, source_url, media, pages, content, metadata, title, publisher, period = source
    body = bytes(content or b"")
    if ((kind, source_url, media, pages, title, publisher, str(period)) !=
            ("original", spec["source_url"], "application/pdf", spec["pages"],
             spec["title"], "DANE", spec["day"])
            or metadata != spec["metadata"] or len(body) != spec["bytes"]
            or hashlib.sha256(body).hexdigest() != spec["document_id"]
            or not body.startswith(b"%PDF-")):
        raise ValueError("Registered v14 replacement source witness differs")
    checkpoint = db.execute(
        """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
           AND processor_version=%s AND step='inputs-pdf:published'""",
        (spec["document_id"], OLD_VERSION),
    ).fetchone()
    cohort = db.execute(
        """SELECT count(*),count(*) FILTER (WHERE series='dane-inputs-pdf'),
                  count(*) FILTER (WHERE series='dane-inputs-pdf-unresolved')
           FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s""",
        (spec["document_id"], OLD_VERSION),
    ).fetchone()
    if checkpoint != (spec["typed_rows"],) or tuple(cohort) != (
            spec["raw_rows"], spec["typed_rows"], spec["unresolved_rows"]):
        raise ValueError("Registered v14 replacement cohort/checkpoint differs")
    rows = db.execute(
        f"SELECT {ROW_FIELDS} FROM historical_price WHERE document_id=%s "
        "AND details->>'parser_version'=%s ORDER BY source_locator",
        (spec["document_id"], OLD_VERSION),
    ).fetchall()
    if (not spec.get("old_vector_sha256")
            or _retained_vector_sha256(rows) != spec["old_vector_sha256"]):
        raise ValueError("Registered v14 replacement full source vector differs")


def _generic_context_v14_witness(db, url, day):
    """Find and validate one exact retained context-PDF v14 source for a URL.

    This compatibility route is deliberately based on the archived source row,
    never filename normalization or a URL alias. It is limited to native DANE
    inputs-PDF filenames and requires the complete immutable v14 vector to
    agree with reparsing the exact retained bytes.
    """
    is_jan_alias = url == JAN2019_LITERAL_ALIAS_URL
    filename = _generic_retained_context_filename(
        url, JAN2019_CONTEXT_DID if is_jan_alias else None
    )
    if not filename or day is None or not hasattr(day, "isoformat"):
        return None
    source_url = JAN2019_CONTEXT_URL if is_jan_alias else url
    rows = db.execute(
        """SELECT id,kind,source_url,media_type,page_count,content,metadata,
                  title,publisher,reference_period
           FROM source_document WHERE source_url=%s AND kind='original'
             AND metadata->>'ingestion_kind'='context-pdf'
           ORDER BY id""", (source_url,),
    ).fetchall()
    if len(rows) != 1:
        if rows:
            raise ValueError("DANE context URL has multiple retained originals")
        return None
    (did, source_kind, source_url, media, pages, content, metadata,
     title, publisher, period) = rows[0]
    if (url in JAN2019_CONTEXT_SOURCE_ALIASES
            and (did != JAN2019_CONTEXT_DID or day.isoformat() != JAN2019_CONTEXT_DAY)):
        raise ValueError("January 2019 asset URL did not resolve to its exact source witness")
    body = bytes(content or b"")
    if ((source_kind, source_url, media, title, publisher, str(period)) !=
            ("original", JAN2019_CONTEXT_URL if is_jan_alias else url, "application/pdf",
             "DANE - " + filename, "DANE", _generic_context_expected_period(url, day, did))
            or metadata != {"retention": "permanent", "ingestion_kind": "context-pdf",
                            "original_filename": filename}
            or not body.startswith(b"%PDF-") or not 0 < len(body) <= MAX_PDF_BYTES
            or hashlib.sha256(body).hexdigest() != did):
        raise ValueError("DANE context retained source binding differs")
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        actual_pages = len(pdf.pages)
    if not 0 < actual_pages <= MAX_PDF_PAGES or pages != actual_pages:
        raise ValueError("DANE context retained source page count differs")
    checkpoint = db.execute(
        """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
           AND processor_version=%s AND step='inputs-pdf:published'""",
        (did, OLD_VERSION),
    ).fetchone()
    cohort = db.execute(
        """SELECT count(*),count(*) FILTER (WHERE series='dane-inputs-pdf'),
                  count(*) FILTER (WHERE series='dane-inputs-pdf-unresolved')
           FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s""",
        (did, OLD_VERSION),
    ).fetchone()
    if (checkpoint is None or cohort[0] <= 0 or checkpoint[0] != cohort[1]
            or cohort[1] + cohort[2] != cohort[0]):
        raise ValueError("DANE context retained v14 cohort/checkpoint differs")
    if did == JAN2019_CONTEXT_DID and (
        url not in JAN2019_CONTEXT_SOURCE_ALIASES
        or day.isoformat() != JAN2019_CONTEXT_DAY
        or pages != JAN2019_CONTEXT_PAGES or len(body) != JAN2019_CONTEXT_BYTES
        or cohort != (JAN2019_CONTEXT_RAW_ROWS, JAN2019_CONTEXT_TYPED_ROWS,
                      JAN2019_CONTEXT_UNRESOLVED_ROWS)
        or checkpoint != (JAN2019_CONTEXT_TYPED_ROWS,)
    ):
        raise ValueError("January 2019 literal alias source cohort/checkpoint differs")
    stored = db.execute(
        f"SELECT {ROW_FIELDS} FROM historical_price WHERE document_id=%s "
        "AND details->>'parser_version'=%s ORDER BY source_locator",
        (did, OLD_VERSION),
    ).fetchall()
    if len(stored) != cohort[0] or _retained_vector_sha256(stored) == "":
        raise ValueError("DANE context retained v14 rows are incomplete")
    stored_hash = _retained_vector_sha256(stored)
    independent_hash = (
        JAN2019_CONTEXT_OLD_VECTOR_SHA256 if did == JAN2019_CONTEXT_DID
        else GENERIC_CONTEXT_OLD_VECTOR_SHA256.get(url)
    )
    if independent_hash is not None and stored_hash != independent_hash:
        raise ValueError("DANE context retained v14 vector differs from independent SQL export")
    return {"document_id": did, "day": day.isoformat(), "pages": pages,
            "raw_rows": cohort[0], "typed_rows": cohort[1],
            "unresolved_rows": cohort[2], "vector_sha256": stored_hash,
            "filename": filename}


def _generic_context_replacement_old_did(db, did):
    """Validate a normal-input replacement and return its exact prior context DID."""
    current = db.execute(
        """SELECT kind,source_url,media_type,page_count,content,metadata,
                  title,publisher,reference_period
           FROM source_document WHERE id=%s""", (did,),
    ).fetchone()
    if current is None:
        raise ValueError("DANE replacement source original is missing")
    kind, url, media, pages, content, metadata, title, publisher, period = current
    filename = _generic_retained_context_filename(url, did)
    canonical_url = _generic_context_source_url(url, did)
    if (not filename or kind != "original" or media != "application/pdf"
            or metadata != {"ingestion_kind": "inputs-pdf", "retention": "permanent",
                            "original_filename": filename}
            or title != "DANE - " + filename or publisher != "DANE"
            or (canonical_url != url and url not in JAN2019_CONTEXT_SOURCE_ALIASES)):
        return None
    if url in (JAN2019_CONTEXT_URL, JAN2019_LITERAL_ALIAS_URL):
        day = date.fromisoformat(JAN2019_CONTEXT_DAY)
        if str(period) != JAN2019_CONTEXT_DAY:
            raise ValueError("DANE January 2019 replacement period differs")
    else:
        day = date.fromisoformat(str(period))
    old = _generic_context_v14_witness(db, url, day)
    if old is None:
        return None
    body = bytes(content or b"")
    if ((kind, url, media, title, publisher, metadata) !=
            ("original", url, "application/pdf", "DANE - " + filename, "DANE",
             {"ingestion_kind": "inputs-pdf", "retention": "permanent",
              "original_filename": filename})
            or not body.startswith(b"%PDF-") or not 0 < len(body) <= MAX_PDF_BYTES
            or hashlib.sha256(body).hexdigest() != did):
        raise ValueError("DANE changed-body source binding differs")
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        actual_pages = len(pdf.pages)
    if not 0 < actual_pages <= MAX_PDF_PAGES or pages != actual_pages:
        raise ValueError("DANE changed-body page count differs")
    asset = db.execute(
        """SELECT kind,observed_on,document_id,status,processor_version,records
           FROM ingestion_asset WHERE url=%s FOR UPDATE""", (url,),
    ).fetchone()
    if (asset is None or asset[0] != "inputs-pdf" or str(asset[1]) != day.isoformat()
            or asset[2] != did or asset[3] not in ("complete", "pending", "failed")
            or asset[4] != VERSION or not isinstance(asset[5], int) or asset[5] < 0):
        raise ValueError("DANE changed-body asset pointer/lifecycle differs")
    old_rows = db.execute(
        "SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",
        (did, OLD_VERSION),
    ).fetchone()[0]
    old_checkpoints = db.execute(
        """SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s
           AND processor_version=%s AND step='inputs-pdf:published'""", (did, OLD_VERSION),
    ).fetchone()[0]
    if old_rows or old_checkpoints:
        raise ValueError("DANE replacement unexpectedly contains a v14 cohort")
    count = db.execute(
        "SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",
        (did, VERSION),
    ).fetchone()[0]
    checkpoint = db.execute(
        """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
           AND processor_version=%s AND step='inputs-pdf:published'""", (did, VERSION),
    ).fetchone()
    if asset[3] == "complete":
        if count != asset[5] or checkpoint != (count,):
            raise ValueError("DANE completed replacement cohort/checkpoint differs")
    elif checkpoint is not None:
        raise ValueError("DANE interrupted replacement has a publication checkpoint")
    return old["document_id"]


def complete_jan2019_sibling_asset(db, url, kind, day):
    """Complete the exact sister URL asset from its already-published same-DID rows.

    This is only for the second of the two observed URLs after the shared
    immutable source already has a complete v17 cohort. It performs no fetch,
    parse, source/history/checkpoint write, or publication projection update.
    """
    if url not in JAN2019_CONTEXT_SOURCE_ALIASES or kind != "inputs-pdf":
        return None
    if day is None or not hasattr(day, "isoformat") or day.isoformat() != JAN2019_CONTEXT_DAY:
        raise ValueError("January 2019 sibling asset date differs")
    with db.transaction():
        asset = db.execute(
            """SELECT kind,observed_on,document_id,status,processor_version,records,error
               FROM ingestion_asset WHERE url=%s FOR UPDATE""", (url,),
        ).fetchone()
        if asset is None:
            return None
        # Only intercept a retry of the exact retained DID. Initial v14 work
        # and a URL whose current pointer is a separately verified body must
        # continue through the standard replay/replacement guards.
        if asset[2] != JAN2019_CONTEXT_DID:
            return None
        if asset[:3] != ("inputs-pdf", day, JAN2019_CONTEXT_DID):
            return None
        if asset[3] == "complete" and asset[4] == VERSION:
            if (asset[:3] != ("inputs-pdf", day, JAN2019_CONTEXT_DID)
                    or asset[5] != JAN2019_CONTEXT_RAW_ROWS or asset[6] is not None):
                raise ValueError("January 2019 completed sibling asset binding differs")
            return None
        old_v14_sibling = asset[4] == OLD_VERSION and asset[3] in ("complete", "pending")
        retry_v17_sibling = asset[4] == VERSION and asset[3] in ("failed", "pending")
        if not (old_v14_sibling or retry_v17_sibling):
            return None
        retry_errors = {
            _RETAINED_IDENTITY_ERROR,
            "ValueError: Retained input PDF page count mismatch",
            WORK_DEFERRED_RETRY_ERROR,
        }
        if (asset[5] != JAN2019_CONTEXT_RAW_ROWS
                or (retry_v17_sibling and asset[6] not in retry_errors)):
            return None
        checkpoint = db.execute(
            """SELECT records FROM ingestion_checkpoint WHERE document_id=%s
               AND processor_version=%s AND step='inputs-pdf:published'""",
            (JAN2019_CONTEXT_DID, VERSION),
        ).fetchone()
        if checkpoint is None:
            return None
        old = _generic_context_v14_witness(db, url, day)
        if (old is None or old["document_id"] != JAN2019_CONTEXT_DID
                or old["vector_sha256"] != JAN2019_CONTEXT_OLD_VECTOR_SHA256):
            raise ValueError("January 2019 sibling v14 source witness differs")
        rows = db.execute(
            f"SELECT {ROW_FIELDS} FROM historical_price WHERE document_id=%s "
            "AND details->>'parser_version'=%s ORDER BY source_locator",
            (JAN2019_CONTEXT_DID, VERSION),
        ).fetchall()
        cohort = db.execute(
            """SELECT count(*),count(*) FILTER (WHERE series='dane-inputs-pdf'),
                      count(*) FILTER (WHERE series='dane-inputs-pdf-unresolved')
               FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s""",
            (JAN2019_CONTEXT_DID, VERSION),
        ).fetchone()
        if (tuple(cohort) != (JAN2019_CONTEXT_RAW_ROWS, JAN2019_CONTEXT_TYPED_ROWS,
                              JAN2019_CONTEXT_UNRESOLVED_ROWS)
                or checkpoint != (JAN2019_CONTEXT_TYPED_ROWS,)
                or _retained_vector_sha256(rows) != JAN2019_CONTEXT_NEW_VECTOR_SHA256):
            raise ValueError("January 2019 sibling published v17 cohort differs")
        changed = db.execute(
            """UPDATE ingestion_asset SET status='complete',processor_version=%s,records=%s,checked_at=now(),
               attempts=attempts+1,error=NULL WHERE url=%s AND document_id=%s
                 AND status IN ('complete','failed','pending') AND processor_version IN (%s,%s)""",
            (VERSION, JAN2019_CONTEXT_RAW_ROWS, url, JAN2019_CONTEXT_DID, OLD_VERSION, VERSION),
        )
        if changed.rowcount != 1:
            raise ValueError("January 2019 sibling asset completion lost its locked row")
        return JAN2019_CONTEXT_RAW_ROWS


def assert_generic_context_replacement_locked(db, url, kind, day, new_did, old_did):
    """Rebind a changed URL body while holding the mutable asset row lock."""
    if kind != "inputs-pdf" or old_did is None:
        return
    old = _generic_context_v14_witness(db, url, day)
    if old is None or old["document_id"] != old_did:
        raise ValueError("DANE changed-body old source witness changed during publication")
    asset = db.execute(
        """SELECT kind,observed_on,document_id,status,processor_version,records
           FROM ingestion_asset WHERE url=%s FOR UPDATE""", (url,),
    ).fetchone()
    if (asset is None or asset[0] != kind or asset[1] != day
            or asset[2] != new_did or asset[3] not in ("pending", "complete")
            or asset[4] != VERSION):
        raise ValueError("DANE changed-body asset pointer changed during publication")
    _generic_context_replacement_old_did(db, new_did)


def _registered_replacement_old_did(db, did):
    """Validate a current exact registered body and return its old DID witness."""
    source = db.execute(
        """SELECT kind,source_url,media_type,page_count,content,metadata,
                  title,publisher,reference_period
           FROM source_document WHERE id=%s""", (did,)
    ).fetchone()
    if source is None:
        raise ValueError("Registered replacement original is missing")
    kind, url, media, pages, content, metadata, title, publisher, period = source
    spec = _registered_v14_replacement_spec(url)
    if spec is None:
        return _generic_context_replacement_old_did(db, did)
    if did == spec["document_id"]:
        return None
    asset = db.execute(
        "SELECT kind,observed_on,document_id,status,processor_version FROM ingestion_asset WHERE url=%s FOR UPDATE",
        (url,),
    ).fetchone()
    if (asset is None or asset[0] != "inputs-pdf" or str(asset[1]) != spec["day"]
            or asset[2] != did or asset[3] not in ("pending", "failed", "complete")
            or asset[4] not in (OLD_VERSION, VERSION)):
        raise ValueError("Registered replacement asset pointer/lifecycle differs")
    _assert_registered_v14_source_witness(db, url, spec)
    filename = url.rsplit("/", 1)[-1]
    body = bytes(content or b"")
    try:
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            actual_pages = len(pdf.pages)
    except Exception as exc:
        raise ValueError("Registered replacement source PDF page tree is unreadable") from exc
    if ((kind, media, title, publisher, str(period), url) !=
            ("original", "application/pdf", "DANE - " + filename, "DANE", spec["day"], url)
            or metadata != {"ingestion_kind": "inputs-pdf", "retention": "permanent",
                            "original_filename": filename}
            or pages != actual_pages or not 0 < actual_pages <= MAX_PDF_PAGES or not body.startswith(b"%PDF-")
            or not 0 < len(body) <= MAX_PDF_BYTES or hashlib.sha256(body).hexdigest() != did):
        raise ValueError("Registered replacement source binding differs")
    old_rows = db.execute(
        "SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",
        (did, OLD_VERSION),
    ).fetchone()[0]
    other_checkpoints = db.execute(
        """SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s
           AND step='inputs-pdf:published' AND processor_version<>%s""",
        (did, VERSION),
    ).fetchone()[0]
    if old_rows or other_checkpoints:
        raise ValueError("Registered replacement has an unexpected old cohort/checkpoint")
    return spec["document_id"]


def assert_v17_public_stage_safe(db, did):
    """Allow only conflicts already present with identical v14 evidence.

    The existing projector excludes conflicting keys and leaves their
    watermarks alone. This guard confirms that every conflict being excluded
    is the same complete source group already retained in v14; a new or
    modified conflict fails closed. Other identities retain the same-source
    publication guard below.
    """
    staged = db.execute(
        """SELECT id,department,observed_on,name,category,presentation,price,
                  brand,registration,product_line,municipality,source_locator
        FROM input_stage ORDER BY id,department,municipality,observed_on,source_locator"""
    ).fetchall()
    current_groups = defaultdict(Counter)
    for row in staged:
        key = (row[0], row[1], row[10], row[2])
        current_groups[key][tuple(row)] += 1
    ambiguous_keys = {
        key for key, rows in current_groups.items()
        if len({row[6] for row in rows}) > 1
    }
    registered_old_did = _registered_replacement_old_did(db, did)
    old_rows = []
    if ambiguous_keys or registered_old_did:
        witness_did = registered_old_did or did
        old_rows = db.execute(
            f"SELECT {ROW_FIELDS} FROM historical_price WHERE document_id=%s "
            "AND details->>'parser_version'=%s AND series='dane-inputs-pdf'",
            (witness_did, OLD_VERSION),
        ).fetchall()
    from .inputs import identity
    old_groups = defaultdict(Counter)
    for old in old_rows:
        loc, series, observed, name, market, unit, price, _variation, details = old
        category = details.get("category")
        if not category:
            raise ValueError("Stored v14 conflict row lacks its input category")
        department = details.get("department") or market
        municipality = details.get("municipality", "") if series != "dane-inputs" else ""
        old_locator = _normalized_old(old)[0]
        signature = (
            identity(name, details), department, observed, name, category,
            details.get("presentation") or unit, Decimal(str(price)),
            details.get("brand", ""), details.get("ica", ""), details.get("line", ""),
            municipality, old_locator,
        )
        old_groups[(signature[0], department, municipality, observed)][signature] += 1
    old_ambiguous_keys = {
        key for key, rows in old_groups.items()
        if len({signature[6] for signature in rows}) > 1
    }
    for key in ambiguous_keys | old_ambiguous_keys:
        if old_groups.get(key) != current_groups.get(key):
            raise ValueError("v17 input PDF introduced, removed, or changed a conflicting source group")
    for table, municipal in (("input_price", False), ("input_municipal_price", True)):
        changed = db.execute(
            f"""SELECT 1 FROM input_stage s JOIN {table} p
            ON p.id=s.id AND p.department=s.department AND p.observed_on=s.observed_on
            {"AND p.municipality=s.municipality" if municipal else ""}
            WHERE s.municipality {"<>" if municipal else "="} ''
              AND p.document_id=%s AND p.price<>s.price LIMIT 1""",
            (did,),
        ).fetchone()
        if changed:
            raise ValueError("v17 input PDF changes a previously published price from the same original")
