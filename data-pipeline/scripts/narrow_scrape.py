"""One-off: scrape only 2025+2026 abastecimiento + 2021+ insumos for the 1-year window."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraping.abastecimiento_scraper import AbastecimientoScraper, CURRENT_URL as ABAST_CURRENT
from scraping.insumos_scraper import InsumosScraper, CURRENT_MUN_URL, DEPT_URL

ABAST_2025 = "https://www.dane.gov.co/files/operaciones/SIPSA/anex-Microdato-abastecimiento-2025.xlsx"

print("=== Scraping abast: 2025 + 2026 only ===", flush=True)
a = AbastecimientoScraper()
res = a._download_urls([ABAST_2025, ABAST_CURRENT])
print(res, flush=True)

print("=== Scraping insumos: 2021-2026 mun + 2018-2026 dept (skip 2013-2020) ===", flush=True)
i = InsumosScraper()
res = i._download_urls([CURRENT_MUN_URL, DEPT_URL])
print(res, flush=True)
print("=== Narrow scrapes done ===", flush=True)
