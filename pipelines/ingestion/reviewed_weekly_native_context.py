"""Exact-source reviews for fully readable weekly XLS bodies.

Bind the original URL, bytes, metadata, sheet layout, and native row count.
Companion PDFs are independently ingested and do not type workbook rows.
"""
import hashlib
import math
from pathlib import Path

from . import dane_weekly

VERSION_SUFFIX = ":native-context-review-v1"
REVIEW_MARKER = "DANE weekly native rows lack explicit workbook period or unit; retained as untyped source review"
REVIEW_LOCATOR = "XLS document-level native context review"
KIND = "dane-weekly-xlsx"
# Three February 2014 workbooks retain their separately reviewed paired-original route.
ORIGINALS = {'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_nov01_2014.xls': {'sha256': 'dd18960746517e8dc133c93bc34c4a8902a344df61c8be89917988def9943531',
                                                                                                       'bytes': 193988,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_nov01_2014.xls',
                                                                                                       'native_rows': 4601,
                                                                                                       'format': 'ooxml-zip',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_nov08_2014.xls': {'sha256': 'b79b6ceca9da5a5c0e446337445569de1c40a932e297bf801d25e8df23a394a6',
                                                                                                       'bytes': 444416,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_nov08_2014.xls',
                                                                                                       'native_rows': 4600,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anex_Bol_Semanal_dic6_dic12_2014.xls': {'sha256': 'f131265e2f050946f41ce7f21bf1294e8b35d34c985ee45c3e414e474ce66ac2',
                                                                                                           'bytes': 443392,
                                                                                                           'media_type': 'application/vnd.ms-excel',
                                                                                                           'filename': 'Anex_Bol_Semanal_dic6_dic12_2014.xls',
                                                                                                           'native_rows': 4584,
                                                                                                           'format': 'ole-biff',
                                                                                                           'sheets': ['Información '
                                                                                                                      'Boletin'],
                                                                                                           'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anex_Bol_Semanal_nov15_2014.xls': {'sha256': '669b89e9b313563c163566d240b2d1871a7b4f9af64768b8696221dea70669ed',
                                                                                                      'bytes': 192249,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anex_Bol_Semanal_nov15_2014.xls',
                                                                                                      'native_rows': 4572,
                                                                                                      'format': 'ooxml-zip',
                                                                                                      'sheets': ['Información '
                                                                                                                 'Boletin'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anex_Bol_Semanal_nov22_2014.xls': {'sha256': 'f88f3bb6fbf8939a740defa4a2135d7bc5e2e43d84627e293f66de14cf3e9c45',
                                                                                                      'bytes': 421376,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anex_Bol_Semanal_nov22_2014.xls',
                                                                                                      'native_rows': 4594,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Información '
                                                                                                                 'Boletin'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anex_Bol_Semanal_nov29_05dic_2014.xls': {'sha256': 'c7545b0314091314b6fc25536246a2b7cfe214f504f71436ee405b5f52d7bce5',
                                                                                                            'bytes': 420352,
                                                                                                            'media_type': 'application/vnd.ms-excel',
                                                                                                            'filename': 'Anex_Bol_Semanal_nov29_05dic_2014.xls',
                                                                                                            'native_rows': 4582,
                                                                                                            'format': 'ole-biff',
                                                                                                            'sheets': ['Información '
                                                                                                                       'Boletin'],
                                                                                                            'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_18_24abr_2015.xls': {'sha256': '95ea434eb95de174e208022e8ea7b5a2dd0b3e3eea5e7f13f3aa16aa1f53db79',
                                                                                              'bytes': 458752,
                                                                                              'media_type': 'application/vnd.ms-excel',
                                                                                              'filename': 'Anexo_18_24abr_2015.xls',
                                                                                              'native_rows': 4529,
                                                                                              'format': 'ole-biff',
                                                                                              'sheets': ['Información '
                                                                                                         'Boletin'],
                                                                                              'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_25_30abr_2015.xls': {'sha256': 'a34a972e6167108b8b4a5aad7de631ed45257c56b43d812fa8a2e082a9fe92fd',
                                                                                              'bytes': 447488,
                                                                                              'media_type': 'application/vnd.ms-excel',
                                                                                              'filename': 'Anexo_25_30abr_2015.xls',
                                                                                              'native_rows': 4396,
                                                                                              'format': 'ole-biff',
                                                                                              'sheets': ['Información '
                                                                                                         'Boletin'],
                                                                                              'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_4_10abr_2015.xls': {'sha256': 'd432b1429e0c5a188dc83b12c61a3da5daae80ba7132d7aaede2595471beadcc',
                                                                                             'bytes': 429056,
                                                                                             'media_type': 'application/vnd.ms-excel',
                                                                                             'filename': 'Anexo_4_10abr_2015.xls',
                                                                                             'native_rows': 4462,
                                                                                             'format': 'ole-biff',
                                                                                             'sheets': ['Información '
                                                                                                        'Boletin'],
                                                                                             'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_100may10_2014.xls': {'sha256': '2c14a26104fe8bf29252f2a6a908e0953039ac719f8cf4c4f24d188ac61e3ac1',
                                                                                                          'bytes': 443392,
                                                                                                          'media_type': 'application/vnd.ms-excel',
                                                                                                          'filename': 'Anexo_Bol_Semanal_100may10_2014.xls',
                                                                                                          'native_rows': 4633,
                                                                                                          'format': 'ole-biff',
                                                                                                          'sheets': ['Información '
                                                                                                                     'Boletin'],
                                                                                                          'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_abr16_2014.xls': {'sha256': '23729c1c7b184ae6a0af44243739ab18c04def19f99d6ced1d6f85485e37b22c',
                                                                                                       'bytes': 442368,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_abr16_2014.xls',
                                                                                                       'native_rows': 4530,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Boletin-35'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_abr19_2014.xls': {'sha256': '2e6a423f196ef8327015a7efe46fbfedc694b89e67ee2e49f83782d4d914d020',
                                                                                                       'bytes': 448000,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_abr19_2014.xls',
                                                                                                       'native_rows': 4598,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Boletin-27'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_abr5_2014.xls': {'sha256': 'a49578903992b35a2b06a8cd74b9624c9af1d25c790a142dd86b3f0dc91cb580',
                                                                                                      'bytes': 451072,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_abr5_2014.xls',
                                                                                                      'native_rows': 4642,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Boletin-30'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_ago11_2014.xls': {'sha256': '0426a000b04d8cabeccb136ac809e1cb6b76153a55d942beafd06f486d7c5d47',
                                                                                                       'bytes': 444416,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_ago11_2014.xls',
                                                                                                       'native_rows': 4636,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 1},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_ago2_2014.xls': {'sha256': 'a62d0394d1e884168e4edf642d6da9cd3b0790c6c5af2221db0a423c501bc6a3',
                                                                                                      'bytes': 193017,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_ago2_2014.xls',
                                                                                                      'native_rows': 4583,
                                                                                                      'format': 'ooxml-zip',
                                                                                                      'sheets': ['Información '
                                                                                                                 'Boletin'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_ago22_2014.xls': {'sha256': '20e65d729e42dd7af6c7f726f2c86e9fbbc4135ab850584e4ac7f52eede091ba',
                                                                                                       'bytes': 436736,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_ago22_2014.xls',
                                                                                                       'native_rows': 4552,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_ago23_2014.xls': {'sha256': '1541c70a7469bf619117f2859db3d5d94cbdd8f90fd7b047844e531852136b14',
                                                                                                       'bytes': 440832,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_ago23_2014.xls',
                                                                                                       'native_rows': 4603,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_ago30_2014.xls': {'sha256': 'aa11d5a06ff91d8ec778754abe06c7c6df47294363d4bea8d91b43e4594459d8',
                                                                                                       'bytes': 440832,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_ago30_2014.xls',
                                                                                                       'native_rows': 4601,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_ene11_2014.xls': {'sha256': '051c847d87034f0cb446195a60f9ebfa80d565dc51ce9998a6119a160bc4eb1c',
                                                                                                       'bytes': 421888,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_ene11_2014.xls',
                                                                                                       'native_rows': 4554,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Boletin-61'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_ene18_2014.xls': {'sha256': '5269884656e01a06614dbfcebaf245e72a3a0b405a971c24def67168ca95bef0',
                                                                                                       'bytes': 445440,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_ene18_2014.xls',
                                                                                                       'native_rows': 4558,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Boletin-61'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_ene25_2014.xls': {'sha256': 'cd4a2e931be7ebedd660c74645ba0fd84808cbd731dcdee1d3ba5bd179be4c28',
                                                                                                       'bytes': 446976,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_ene25_2014.xls',
                                                                                                       'native_rows': 4574,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Boletin-61'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_ene3_2014.xls': {'sha256': '08e88bb56952a94f037bfd5210de2e6cdf58bc778587505488f20720bc6f32da',
                                                                                                      'bytes': 438272,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_ene3_2014.xls',
                                                                                                      'native_rows': 4469,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Boletin-58'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_ene4_2014.xls': {'sha256': '51e45cd1e5bb53de5e126a73d480057ba7f0b978b064b73eb20344d5ed26b35b',
                                                                                                      'bytes': 443904,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_ene4_2014.xls',
                                                                                                      'native_rows': 4543,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Boletin-59'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_feb1_2014.xls': {'sha256': 'f9fd678f355e3ea5fa1d391ac853c38e526ff548d2d6545f9a60d4d353b725ce',
                                                                                                      'bytes': 446464,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_feb1_2014.xls',
                                                                                                      'native_rows': 4570,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Boletin '
                                                                                                                 'Semanal '
                                                                                                                 'Salida '
                                                                                                                 '2'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_jul11_2014.xls': {'sha256': '01fe61ff560fe4f6770458c3cdcf139ee5e8f612580164e8000d84c74b0ffdbf',
                                                                                                       'bytes': 443392,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_jul11_2014.xls',
                                                                                                       'native_rows': 4627,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_jul18_2014.xls': {'sha256': '8ca5276e7c10d9866643e9119d80440b3f10ec5fe57bf0b66696cb9d17a229f6',
                                                                                                       'bytes': 441856,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_jul18_2014.xls',
                                                                                                       'native_rows': 4604,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_jul19_2014.xls': {'sha256': '38393c882b8660982de37c9c4817b205d98ce60bc4f3b9d6e8015dc5b30bca66',
                                                                                                       'bytes': 441344,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_jul19_2014.xls',
                                                                                                       'native_rows': 4609,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_jul26_2014.xls': {'sha256': 'cda2edc8baa7db1adcfd76bc0276a2cc10ca36846e2a75717a442deee53eaeee',
                                                                                                       'bytes': 442368,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_jul26_2014.xls',
                                                                                                       'native_rows': 4617,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_jun16_2014.xls': {'sha256': 'c9f7de480912d20a62507407c0741a3996ef9eb67d61f7c11caf262ee30af475',
                                                                                                       'bytes': 443392,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_jun16_2014.xls',
                                                                                                       'native_rows': 4631,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_jun21_2014.xls': {'sha256': '7618b270d12c4a2d1da41e77c4ce82c7e3867400c5de6ce298e20e2e61c6e620',
                                                                                                       'bytes': 442880,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_jun21_2014.xls',
                                                                                                       'native_rows': 4623,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_jun28_2014.xls': {'sha256': '7c858c7688e91eacfac83769d7982a9ab89fd89c82aee8e15a384e05e1edc836',
                                                                                                       'bytes': 443392,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_jun28_2014.xls',
                                                                                                       'native_rows': 4632,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 1},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_jun6_2014.xls': {'sha256': '573b0d6efa6862ba0d86d72168031a5a6a1d4eced60dc7d985f56665fd15df58',
                                                                                                      'bytes': 442368,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_jun6_2014.xls',
                                                                                                      'native_rows': 4616,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Información '
                                                                                                                 'Boletin'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_jun7_2014.xls': {'sha256': 'e0486f33009f298273f9490fb63b9ec99347ea4b340a2e27dd81c22a02d83834',
                                                                                                      'bytes': 443392,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_jun7_2014.xls',
                                                                                                      'native_rows': 4632,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Información '
                                                                                                                 'Boletin'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_mar1_2014.xls': {'sha256': '6f477580d6d21c8be9e95d18ee1409a6d08cd77a4c6cd8a4293eabb10b094677',
                                                                                                      'bytes': 449024,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_mar1_2014.xls',
                                                                                                      'native_rows': 4603,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Boletin-26'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_mar15_2014.xls': {'sha256': 'd2e3e8dad1a5a3d470df8d3a9bab73590b00dca43d35462a5d33faf1167466f3',
                                                                                                       'bytes': 449536,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_mar15_2014.xls',
                                                                                                       'native_rows': 4611,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Boletin-30'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_mar22_2014.xls': {'sha256': '0685f4a6c7d02acbed3970456a307e2e5347431aa4787e2d32b6a151fb4fad3b',
                                                                                                       'bytes': 194421,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_mar22_2014.xls',
                                                                                                       'native_rows': 4617,
                                                                                                       'format': 'ooxml-zip',
                                                                                                       'sheets': ['Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_mar29_2014.xls': {'sha256': 'd02d0b689396d199764601fd5949cab28cdd711688ef51905ee69d2892a6ffac',
                                                                                                       'bytes': 451072,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_mar29_2014.xls',
                                                                                                       'native_rows': 4633,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Boletin-25'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_mar8_2014.xls': {'sha256': '315fc31bfb9bcc1eb107ba3dfa9d7bc630e7b35452b02f2f5c4344ef087f817f',
                                                                                                      'bytes': 431104,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_mar8_2014.xls',
                                                                                                      'native_rows': 4619,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Boletin-4'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_may17_2014.xls': {'sha256': '8615becdd05185077d97c23491f9d89fc3f743bfce340b1a2cc19078b13b7396',
                                                                                                       'bytes': 443904,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_may17_2014.xls',
                                                                                                       'native_rows': 4634,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_may2_2014.xls': {'sha256': 'f210d5277dedae91afb84a0389e26e1f1897757268a0d0899b3edc1edc0059f4',
                                                                                                      'bytes': 194727,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_may2_2014.xls',
                                                                                                      'native_rows': 4618,
                                                                                                      'format': 'ooxml-zip',
                                                                                                      'sheets': ['Boletin-34'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_may24_2014.xls': {'sha256': 'b2e44edc6fb3fec40367c69952191fdd2b73bdde3ef5673a1ad396679806a5dc',
                                                                                                       'bytes': 443392,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_may24_2014.xls',
                                                                                                       'native_rows': 4625,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_may3_2014.xls': {'sha256': '4de137982621bb52ccb9daf14005230ee979245fcb647bb8cbd366ba480480ae',
                                                                                                      'bytes': 195376,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_may3_2014.xls',
                                                                                                      'native_rows': 4622,
                                                                                                      'format': 'ooxml-zip',
                                                                                                      'sheets': ['Boletin-30'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_oct11_2014.xls': {'sha256': '5e7a57d8697ab59dd5fc36d46dd6cbe3c2cccf650d4baec1be722897e5351e02',
                                                                                                       'bytes': 439808,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_oct11_2014.xls',
                                                                                                       'native_rows': 4589,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_oct24_2014.xls': {'sha256': '60b43e76f90f003d096c9b373b45e10463779486f604f69981374b49a6fb56ba',
                                                                                                       'bytes': 443904,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_oct24_2014.xls',
                                                                                                       'native_rows': 4589,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_oct25_2014.xls': {'sha256': 'bbe297155fc28348dd93fcdf9d8da9449557dd57f651dd35b15883d5bfa8070d',
                                                                                                       'bytes': 193731,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_oct25_2014.xls',
                                                                                                       'native_rows': 4609,
                                                                                                       'format': 'ooxml-zip',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_oct4_2014.xls': {'sha256': '93338cc5780a0a1d7fb5378a375c182b89edb8316a3289cd0a9f18ee222f07bf',
                                                                                                      'bytes': 439808,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_oct4_2014.xls',
                                                                                                      'native_rows': 4586,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Información '
                                                                                                                 'Boletin'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_sep13_2014.xls': {'sha256': '90cd03ba2e4b485f80ddf29aa74d171aac210390f8677e7104e850e6e6dff304',
                                                                                                       'bytes': 442368,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_sep13_2014.xls',
                                                                                                       'native_rows': 4622,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_sep26_2014.xls': {'sha256': '78d1f5ca1d7629971d1c7809f1c09c1e1095be67a2eeb430f02165fdcde34d56',
                                                                                                       'bytes': 440320,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_sep26_2014.xls',
                                                                                                       'native_rows': 4595,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_sep27_2014.xls': {'sha256': '8a1a56f47e8d213934ed9ea548c8d0c7c6ad38d250ab2c58b4f9075f1e89fad2',
                                                                                                       'bytes': 439296,
                                                                                                       'media_type': 'application/vnd.ms-excel',
                                                                                                       'filename': 'Anexo_Bol_Semanal_sep27_2014.xls',
                                                                                                       'native_rows': 4580,
                                                                                                       'format': 'ole-biff',
                                                                                                       'sheets': ['Información '
                                                                                                                  'Boletin'],
                                                                                                       'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_sep6_2014.xls': {'sha256': '41c2dae8700ab2618276cbb70a9b667874ff3493807c5ae27fb618838c1f0420',
                                                                                                      'bytes': 442368,
                                                                                                      'media_type': 'application/vnd.ms-excel',
                                                                                                      'filename': 'Anexo_Bol_Semanal_sep6_2014.xls',
                                                                                                      'native_rows': 4626,
                                                                                                      'format': 'ole-biff',
                                                                                                      'sheets': ['Información '
                                                                                                                 'Boletin'],
                                                                                                      'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_SIPSA_enero_11_2013.xls': {'sha256': '155978d5665f0e181d741c251a8cd628bc10c9473e01855d96a919d70479363c',
                                                                                                                'bytes': 381440,
                                                                                                                'media_type': 'application/vnd.ms-excel',
                                                                                                                'filename': 'Anexo_Bol_Semanal_SIPSA_enero_11_2013.xls',
                                                                                                                'native_rows': 4126,
                                                                                                                'format': 'ole-biff',
                                                                                                                'sheets': ['Boletin-3',
                                                                                                                           'Hoja1'],
                                                                                                                'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_13abr_21abr_2017.xls': {'sha256': '0aabdb3805a254d5b310ad0eb74ac3a2d4dd84bc3fb9550874d9f2c6f49d6a6d',
                                                                                               'bytes': 453120,
                                                                                               'media_type': 'application/vnd.ms-excel',
                                                                                               'filename': 'Sem_13abr_21abr_2017.xls',
                                                                                               'native_rows': 4657,
                                                                                               'format': 'ole-biff',
                                                                                               'sheets': ['Información '
                                                                                                          'Boletin'],
                                                                                               'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_27dic_02ne_2015.xls': {'sha256': 'c583c6f5d115615b8628532a6e26736e8abb8b0dd87de5f871dae8b0c1c6f2c4',
                                                                                              'bytes': 427520,
                                                                                              'media_type': 'application/vnd.ms-excel',
                                                                                              'filename': 'Sem_27dic_02ne_2015.xls',
                                                                                              'native_rows': 4512,
                                                                                              'format': 'ole-biff',
                                                                                              'sheets': ['Información '
                                                                                                         'Boletin'],
                                                                                              'partial_rows': 0},
 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_13_17abr_2015.xls': {
     'sha256': 'e40c3580914f8dd1bac08e62483f2cf957ab999f3a103e392f2560082baa2553',
     'bytes': 430592,
     'media_type': 'application/vnd.ms-excel',
     'filename': 'Anexo_13_17abr_2015.xls',
     'native_rows': 4503,
     'format': 'ole-biff',
     'sheets': ['Información Boletin'],
     'partial_rows': 0,
     'layout': 'exact-product-min-max-mean-short-trend-v1',
     'dimensions': [4852, 6],
     'header': ['Producto', 'Min(1)', 'Max(1)', 'P(1)', 'Tend', ''],
 }}

URLS = frozenset(ORIGINALS)


def inspect_original(body, url, document_id):
    expected = ORIGINALS.get(url)
    if expected is None:
        return None
    actual_sha = hashlib.sha256(body).hexdigest()
    if actual_sha != expected["sha256"]:
        # A mutable publisher URL may later serve a normal, newly typed
        # workbook. Only the exact old body enters the untyped-review path;
        # changed bytes continue through the ordinary native parser.
        return None
    if document_id != expected["sha256"] or len(body) != expected["bytes"]:
        raise ValueError("Audited DANE weekly workbook document identity changed")
    if expected["format"] == "ooxml-zip" and not body.startswith(b"PK"):
        raise ValueError("Audited DANE weekly workbook format changed")
    if expected["format"] == "ole-biff" and not body.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError("Audited DANE weekly workbook format changed")

    from .worker import workbooks

    names = []
    rows_count = 0
    notes = []
    headers = 0
    partial_rows = 0
    compact_layout = expected.get("layout") == "exact-product-min-max-mean-short-trend-v1"
    rows_seen = 0
    columns_seen = 0
    active = False
    in_group = False
    for name, iterator in workbooks(body):
        names.append(name)
        if name not in expected.get("sheets", ["Información Boletin"]):
            raise ValueError("Audited DANE weekly workbook sheet layout changed")
        for row_number, row in enumerate(iterator, start=1):
            rows_seen += 1
            cells = list(row)
            columns_seen = max(columns_seen, len(cells))
            notes.extend(dane_weekly.clean(v) for v in cells if isinstance(v, str) and v.strip())
            label = dane_weekly.clean(cells[0]) if cells else ""
            folded = dane_weekly.folded(label)
            if compact_layout and row_number == 1:
                if cells[:6] != expected["header"]:
                    raise ValueError("Audited DANE weekly compact workbook headings changed")
                headers += 1
                active = True
                in_group = True
                continue
            if compact_layout and folded == "producto":
                raise ValueError("Audited DANE weekly compact workbook repeated its header")
            if label.startswith("Cuadro "):
                active = False
                in_group = True
                continue
            if (not compact_layout and len(cells) >= 4
                    and folded == "productos y mercados"):
                cols = [dane_weekly.folded(dane_weekly.clean(v)) for v in cells[1:4]]
                if cols != ["precio minimo", "precio maximo", "precio medio"]:
                    raise ValueError("Audited DANE weekly workbook headings changed")
                headers += 1
                active = True
                in_group = True
                continue
            if not active or not label:
                continue
            prices = cells[1:4]
            populated = [v not in (None, "") for v in prices]
            numeric = [isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(float(v)) for v in prices]
            if not any(populated):
                continue  # A product/category label, with no money values.
            if not all(numeric):
                partial_rows += 1
                continue
            if not isinstance(label, str) or not label.strip():
                raise ValueError("Audited DANE weekly workbook market identity changed")
            rows_count += 1
    if compact_layout and [rows_seen, columns_seen] != expected["dimensions"]:
        raise ValueError("Audited DANE weekly compact workbook dimensions changed")
    if compact_layout:
        if (names != expected.get("sheets", ["Información Boletin"])
                or headers != 1 or not in_group):
            raise ValueError("Audited DANE weekly compact workbook layout changed")
    elif (names != expected.get("sheets", ["Información Boletin"])
            or headers < 1 or not in_group):
        raise ValueError("Audited DANE weekly workbook grouped layout changed")
    if partial_rows != expected.get("partial_rows", 0):
        raise ValueError("Audited DANE weekly workbook partial price row count changed")
    if rows_count != expected["native_rows"]:
        raise ValueError("Audited DANE weekly workbook native row count changed")

    text = "\n".join(notes)
    if dane_weekly._period(text) is not None or dane_weekly._url_period(url) is not None:
        raise ValueError("Audited workbook now contains an explicit weekly period")
    if "pesos por kilogramo" in dane_weekly.folded(text):
        raise ValueError("Audited workbook now declares its monetary unit")
    return {
        "source_locator": REVIEW_LOCATOR,
        "price": None,
        "details": {
            "quality_issue": REVIEW_MARKER,
            "original_sha256": expected["sha256"],
            "source_url": url,
            "native_layout": (
                "compact-product-min-max-mean-short-trend"
                if compact_layout else "grouped-min-max-mean"
            ),
            "native_workbook_format": expected["format"],
            "native_numeric_rows_untyped": rows_count,
            **({"native_partial_rows_untyped": partial_rows} if partial_rows else {}),
            "source_period": None,
            "literal_unit_heading": None,
            "typed_price_rows": 0,
            "review_basis": "Workbook is native-readable, but its cells and URL do not prove the reporting period and monetary unit. Its companion PDF is independently ingested and is not used to type workbook rows.",
        },
    }


def rows_for(db, body, url, document_id, revision, prior_asset_document_id=None):
    row = inspect_original(body, url, document_id)
    if row is None:
        return None

    expected = ORIGINALS[url]
    retained = db.execute(
        "SELECT source_url,media_type,kind,reference_period,metadata,content "
        "FROM source_document WHERE id=%s", (document_id,)
    ).fetchone()
    if retained is None:
        raise ValueError("Audited DANE weekly workbook original is not retained")
    source_url, media_type, document_kind, period, metadata, content = retained
    expected_metadata = {
        "retention": "permanent",
        "ingestion_kind": KIND,
        "original_filename": expected["filename"],
    }
    if (source_url != url or media_type != expected["media_type"]
            or document_kind != "original" or period != "Serie histórica completa"
            or metadata != expected_metadata or bytes(content or b"") != body
            or hashlib.sha256(bytes(content or b"")).hexdigest() != document_id):
        raise ValueError("Audited DANE weekly retained source metadata or body changed")

    ids = {document_id}
    if prior_asset_document_id:
        ids.add(prior_asset_document_id)
    ids.update(r[0] for r in db.execute(
        "SELECT id FROM source_document WHERE source_url=%s AND kind='original' "
        "AND metadata->>'ingestion_kind'=%s", (url, KIND)
    ).fetchall())
    ids.update(r[0] for r in db.execute(
        "SELECT document_id FROM ingestion_asset WHERE url=%s AND kind=%s "
        "AND document_id IS NOT NULL", (url, KIND)
    ).fetchall())
    if db.execute(
        "SELECT 1 FROM official_price_quote WHERE document_id=ANY(%s::text[]) LIMIT 1",
        (sorted(ids),),
    ).fetchone():
        raise ValueError("Native weekly document review is blocked by prior quote history")

    reason = REVIEW_MARKER
    existing = db.execute(
        "SELECT record,reason FROM official_source_review WHERE document_id=%s "
        "AND source_locator=%s AND parser_version=%s",
        (document_id, REVIEW_LOCATOR, revision),
    ).fetchone()
    expected_review = (row, reason)
    if existing is not None and existing != expected_review:
        raise ValueError("Native weekly retained review differs")
    return (row,), reason


# Private generic native-readability guard for unregistered weekly workbooks.
# This is intentionally separate from ORIGINALS/URLS: it adds no URL whitelist.
GENERIC_REVIEW_LOCATOR = "XLS document-level native context review"
GENERIC_REVIEW_MARKER = "DANE weekly native rows lack explicit workbook period or unit; retained as untyped source review"


class GenericWeeklyContextBindingError(ValueError):
    """A concurrent asset/source binding changed before generic review commit."""

def inspect_generic(body, url, document_id):
    """Return an untyped review only for a complete retained DANE weekly XLS body.

    No publication period, monetary unit, or price values are inferred.
    """
    from urllib.parse import urlsplit
    from . import dane_weekly
    from .worker import workbooks

    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "www.dane.gov.co"
            or parts.port not in (None, 443) or parts.query or parts.fragment
            or not parts.path.lower().startswith((
                "/files/investigaciones/agropecuario/sipsa/",
                "/files/operaciones/sipsa/",
            ))
            or not parts.path.lower().endswith((".xls", ".xlsx"))):
        raise ValueError("Weekly native review URL is outside the official XLS scope")
    actual_sha = hashlib.sha256(body).hexdigest()
    if document_id != actual_sha:
        raise ValueError("Weekly native review body is not content-addressed")
    # Existing exact-body/source-specific routes retain priority and semantics;
    # changed bytes at the same mutable URL are evaluated independently.
    if url in ORIGINALS and actual_sha == ORIGINALS[url]["sha256"]:
        return None
    if not (body.startswith(b"PK") or body.startswith(b"\xd0\xcf\x11\xe0")):
        raise ValueError("Weekly native review body has an unsupported workbook format")

    sheet_names = []
    total_headers = 0
    total_numeric = 0
    total_partial = 0
    notes = []
    supported = False
    for name, iterator in workbooks(body):
        if name in sheet_names:
            raise ValueError("Weekly native workbook has duplicate sheet names")
        sheet_names.append(name)
        active = False
        sheet_headers = 0
        for raw in iterator:
            cells = list(raw)
            notes.extend(dane_weekly.clean(v) for v in cells
                         if isinstance(v, str) and v.strip())
            label = dane_weekly.clean(cells[0]) if cells else ""
            folded = dane_weekly.folded(label)
            if label.startswith("Cuadro "):
                active = False
                continue
            if len(cells) >= 4 and folded == "productos y mercados":
                columns = [dane_weekly.folded(dane_weekly.clean(v)) for v in cells[1:4]]
                if columns != ["precio minimo", "precio maximo", "precio medio"]:
                    raise ValueError("Weekly native grouped monetary headers are unsupported")
                supported = True
                active = True
                sheet_headers += 1
                total_headers += 1
                continue
            if not active or not label:
                continue
            vals = cells[1:4]
            present = [v not in (None, "") for v in vals]
            if not any(present):
                continue
            numeric = [isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(float(v)) for v in vals]
            if all(numeric):
                total_numeric += 1
            else:
                total_partial += 1
    if not sheet_names or not supported or total_headers < 1 or total_numeric < 1:
        raise ValueError("Weekly native workbook lacks a complete supported grouped price table")
    text = "\n".join(notes)
    # The route is reached only after normal parser reports missing context.
    # Independently reject any period found natively or by the accepted URL grammar.
    if dane_weekly._period(text) is not None or dane_weekly._url_period(url) is not None:
        raise ValueError("Weekly native workbook contains explicit period context")
    unit_headings = []
    for note in notes:
        folded_note = dane_weekly.folded(note)
        if ("pesos por kilogramo" in folded_note
                or "pesos por kg" in folded_note
                or "$ / kg" in folded_note
                or "$/kg" in folded_note):
            if note not in unit_headings:
                unit_headings.append(note)
    result = {
        "source_locator": GENERIC_REVIEW_LOCATOR,
        "price": None,
        "details": {
            "quality_issue": GENERIC_REVIEW_MARKER,
            "original_sha256": actual_sha,
            "source_url": url,
            "native_layout": "grouped-min-max-mean",
            "native_workbook_format": "ooxml-zip" if body.startswith(b"PK") else "ole-biff",
            "native_sheet_names": sheet_names,
            "native_grouped_headers": total_headers,
            "native_numeric_rows_untyped": total_numeric,
            "native_partial_rows_untyped": total_partial,
            "source_period": None,
            "literal_unit_heading": unit_headings[0] if len(unit_headings) == 1 else None,
            "typed_price_rows": 0,
            "review_basis": (
                "All workbook sheets were read natively. No explicit weekly period is present in cells or the accepted URL range; no date, unit, or prices are inferred."
                if not unit_headings else
                "All workbook sheets were read natively. No explicit weekly period is present in cells or the accepted URL range; no date or prices are inferred. The literal unit heading is retained as evidence but does not type any rows."
            ),
        },
    }
    if unit_headings:
        result["details"]["literal_unit_headings"] = unit_headings
    return result

def rows_for_generic(db, body, url, document_id, revision, prior_asset_document_id=None):
    row = inspect_generic(body, url, document_id)
    if row is None:
        return None
    from urllib.parse import urlsplit
    filename = Path(urlsplit(url).path).name
    retained = db.execute(
        "SELECT source_url,media_type,kind,reference_period,metadata,content "
        "FROM source_document WHERE id=%s", (document_id,)
    ).fetchone()
    if retained is None:
        raise ValueError("Weekly native review original is not retained")
    source_url, media_type, source_kind, period, metadata, content = retained
    expected_media = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if filename.lower().endswith(".xlsx") else "application/vnd.ms-excel"
    )
    if (source_url != url or media_type != expected_media
            or source_kind != "original" or period != "Serie histórica completa"
            or metadata != {"retention": "permanent", "ingestion_kind": KIND,
                            "original_filename": filename}
            or bytes(content or b"") != body
            or hashlib.sha256(bytes(content or b"")).hexdigest() != document_id):
        raise ValueError("Weekly native retained source metadata or body changed")
    ids = {document_id}
    if prior_asset_document_id:
        ids.add(prior_asset_document_id)
    ids.update(r[0] for r in db.execute(
        "SELECT id FROM source_document WHERE source_url=%s AND kind='original' "
        "AND metadata->>'ingestion_kind'=%s", (url, KIND)
    ).fetchall())
    ids.update(r[0] for r in db.execute(
        "SELECT document_id FROM ingestion_asset WHERE url=%s AND kind=%s "
        "AND document_id IS NOT NULL", (url, KIND)
    ).fetchall())
    if db.execute(
        "SELECT 1 FROM official_price_quote WHERE document_id=ANY(%s::text[]) LIMIT 1",
        (sorted(ids),),
    ).fetchone():
        raise ValueError("Generic weekly native review is blocked by prior quote history")
    expected = (row, GENERIC_REVIEW_MARKER)
    existing = db.execute(
        "SELECT record,reason FROM official_source_review WHERE document_id=%s "
        "AND source_locator=%s AND parser_version=%s",
        (document_id, GENERIC_REVIEW_LOCATOR, revision),
    ).fetchone()
    if existing is not None and existing != expected:
        raise ValueError("Generic weekly native review differs from its retained record")
    return (row,), GENERIC_REVIEW_MARKER
