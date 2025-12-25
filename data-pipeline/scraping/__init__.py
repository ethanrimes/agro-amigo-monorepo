"""
Web scraping module for downloading SIPSA data from DANE website.
"""

from .scraper_base import ScraperBase
from .current_month import CurrentMonthScraper
from .historical import HistoricalScraper

__all__ = [
    'ScraperBase',
    'CurrentMonthScraper',
    'HistoricalScraper'
]
