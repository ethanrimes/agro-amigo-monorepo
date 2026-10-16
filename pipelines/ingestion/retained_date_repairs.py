"""Retained exact originals for reviewed DANE source repairs."""
import hashlib

BASE = 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/'
REPAIRS = {
    BASE + 'mayoristas_diciembre_02_2019.xlsx': (
        'daily', '10a85133075b7e2c334bf472bda70df5d99ccdaec6640594ee7ac494d283a316',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ':dec2019-native-month-review-v1'),
    BASE + 'mayoristas_agosto_12_2019.xlsx': (
        'daily', '5f908d72f6b60fd3cf3f331ea2ae9434aa026d5561609b1fe4e085b7cad2ec85',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ':aug2019-native-month-review-v1'),
    BASE + 'Semana_16nov_22nov_2013.pdf': (
        'dane-weekly-pdf', '6fffa387e6644720dd066739de89d38ce604a3af4ae5c7271a3b20127aa199d7',
        'application/pdf', ':panela-article-boundary-v1'),
    BASE + 'Semana_29nov_6dic_2013.pdf': (
        'dane-weekly-pdf', 'a4456cbe9dfb2d3a6c5cb5c91c453f5f43b15edece78da2e83c7aa5429b12809',
        'application/pdf', ':panela-article-boundary-v1'),
    BASE + 'Semana_6dic_13dic_2013.pdf': (
        'dane-weekly-pdf', 'ab3f0d13a9440ae992a3bde558d3c4d2ca56024262d873a6b1ecf7f30472fdc1',
        'application/pdf', ':panela-article-boundary-v1'),
    BASE + 'Semana_16jun_20jun_2014.pdf': (
        'dane-weekly-pdf', '7c05255c9634e7f9fec2d482368c69bae544c027d49b20d7c4c99f2ac64f90a9',
        'application/pdf', ':jun2014-panela-article-single-price-v1'),
    BASE + 'mayoristas_febrero_20_2017.xls': (
        'daily', '58541524d801feadbce7be1059f9e6d924c58b668785ab3023a2725d5114ac4d',
        'application/vnd.ms-excel', ':feb2017-native-month-review-v1'),
    BASE + 'mayoristas_enero_07_2020.xlsx': (
        'daily', '73e9e87255acfdae1c851920d084f00ed90d21baf754f848c88da6112971fe72',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ':jan2020-day07-native-year-review-v1'),
    BASE + 'mayoristas_enero_08_2020.xlsx': (
        'daily', '74f03719c5227c25c219b4b7475740b0382e61b911d025aeb5f13d71abaa81a1',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ':jan2020-day08-native-year-review-v1'),
    BASE + 'mayoristas_enero_09_2020.xlsx': (
        'daily', 'fe7ca4b678001889d58d945d2098a88877e53e35c77c74bbda0af6ea2123b7a3',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ':jan2020-day09-native-year-review-v1'),
    BASE + 'mayoristas_enero_10_2020.xlsx': (
        'daily', '4632f2426dda197ff7115c7801e28bfbf8eebcf012b6343e656ac1bfdff1e538',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ':jan2020-day10-native-year-review-v1'),
    BASE + 'mayoristas_enero_13_2020.xlsx': (
        'daily', 'eca65a7f770f62021b338f94aae46d96f6421ee5d2337f1db93de013a8c06d2b',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ':jan2020-day13-native-year-review-v1'),
    BASE + 'mayoristas_enero_14_2020.xlsx': (
        'daily', '872320bb98111d27365140203675f28bfbaf8856d437d977aee87de53ddfd5fb',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ':jan2020-day14-native-year-review-v1'),
    BASE + 'mayoristas_enero_15_2020.xlsx': (
        'daily', 'd0eea326eb44186c3ac0be8796da460897d9b78cee3f5f885784cc42d2353219',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ':jan2020-day15-native-year-review-v1'),
    BASE + 'mayoristas_enero_16_2020.xlsx': (
        'daily', '83885449eb25388a124efeed3fa7e642ce487cbd68a11051e6daba3ee460f787',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ':jan2020-day16-native-year-review-v1'),
}


def retained_exact_date_repair(db, url, kind, expected_version):
    """Return an exact retained original, or None for an ineligible asset."""
    case = REPAIRS.get(url)
    if case is None or case[0] != kind:
        return None
    _, sha, media, _ = case
    row = db.execute('''SELECT d.content FROM ingestion_asset a
        JOIN source_document d ON d.id=a.document_id
        WHERE a.url=%s AND a.kind=%s AND a.document_id=%s
          AND a.status IN ('failed','review','pending')
          AND a.processor_version IS DISTINCT FROM %s
          AND d.id=%s AND d.kind='original' AND d.source_url=a.url
          AND d.media_type=%s AND d.metadata->>'ingestion_kind'=%s''',
        (url, kind, sha, expected_version, sha, media, kind)).fetchone()
    if row is None:
        return None
    body = bytes(row[0])
    if hashlib.sha256(body).hexdigest() != sha:
        raise ValueError('Exact retained DANE date repair SHA mismatch')
    magic = (b'%PDF-' if media == 'application/pdf' else
             b'PK' if media == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
             else b'\xd0\xcf\x11\xe0')
    if not body.startswith(magic):
        raise ValueError('Exact retained DANE date repair signature mismatch')
    return body
