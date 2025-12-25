"""
Geographic mapping utilities for matching cities to DIVIPOLA codes.

Provides fuzzy matching between city names in price data and
official Colombian municipality codes from DIVIPOLA.
"""

import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from difflib import SequenceMatcher

import sys

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from backend.supabase_client import get_supabase_client
from cleaning.standardizer import Standardizer


class GeographicMapper:
    """Maps city names to DIVIPOLA municipality codes."""

    def __init__(self):
        """Initialize the mapper and load DIVIPOLA data."""
        self.divipola_data = {}
        self.city_index = {}
        self._load_divipola()

    def _load_divipola(self):
        """Load DIVIPOLA data from database."""
        try:
            client = get_supabase_client()
            response = client.table('divipola_municipios').select('*').execute()

            if response.data:
                for row in response.data:
                    code = row['codigo_municipio']
                    self.divipola_data[code] = {
                        'codigo_municipio': code,
                        'codigo_departamento': row['codigo_departamento'],
                        'nombre_municipio': row['nombre_municipio'],
                        'nombre_departamento': row['nombre_departamento'],
                        'latitud': row['latitud'],
                        'longitud': row['longitud']
                    }

                    # Build city name index
                    city_key = Standardizer.create_comparison_key(row['nombre_municipio'])
                    if city_key not in self.city_index:
                        self.city_index[city_key] = []
                    self.city_index[city_key].append(code)

        except Exception as e:
            print(f"Error loading DIVIPOLA data: {e}")

    def find_match(self, city_name: str) -> Optional[Dict]:
        """
        Find best DIVIPOLA match for a city name.

        Args:
            city_name: City name to match

        Returns:
            DIVIPOLA entry dict or None if no match found
        """
        if not city_name:
            return None

        # Standardize input
        std_city = Standardizer.standardize_city(city_name)
        city_key = Standardizer.create_comparison_key(city_name)

        # Try exact match first
        if city_key in self.city_index:
            codes = self.city_index[city_key]
            return self.divipola_data[codes[0]]

        # Try fuzzy matching
        best_match = None
        best_score = 0.0
        threshold = 0.85  # Minimum similarity score

        for key, codes in self.city_index.items():
            score = SequenceMatcher(None, city_key, key).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_match = self.divipola_data[codes[0]]

        return best_match

    def find_all_matches(self, city_name: str, threshold: float = 0.7) -> List[Tuple[Dict, float]]:
        """
        Find all possible DIVIPOLA matches with confidence scores.

        Args:
            city_name: City name to match
            threshold: Minimum similarity score

        Returns:
            List of (entry, score) tuples sorted by score descending
        """
        if not city_name:
            return []

        city_key = Standardizer.create_comparison_key(city_name)
        matches = []

        for key, codes in self.city_index.items():
            score = SequenceMatcher(None, city_key, key).ratio()
            if score >= threshold:
                for code in codes:
                    matches.append((self.divipola_data[code], score))

        return sorted(matches, key=lambda x: x[1], reverse=True)

    def get_department(self, city_name: str) -> Optional[str]:
        """
        Get department name for a city.

        Args:
            city_name: City name

        Returns:
            Department name or None
        """
        match = self.find_match(city_name)
        return match['nombre_departamento'] if match else None

    def get_municipality_code(self, city_name: str) -> Optional[str]:
        """
        Get DIVIPOLA municipality code for a city.

        Args:
            city_name: City name

        Returns:
            5-digit municipality code or None
        """
        match = self.find_match(city_name)
        return match['codigo_municipio'] if match else None

    def generate_mapping_report(self, city_names: List[str]) -> List[Dict]:
        """
        Generate a mapping report for a list of city names.

        Args:
            city_names: List of city names to map

        Returns:
            List of mapping results with match details
        """
        results = []

        for city in city_names:
            matches = self.find_all_matches(city, threshold=0.6)

            result = {
                'input_city': city,
                'input_standardized': Standardizer.standardize_city(city),
                'input_key': Standardizer.create_comparison_key(city),
                'match_count': len(matches),
                'best_match': None,
                'best_score': 0.0,
                'all_matches': []
            }

            if matches:
                best = matches[0]
                result['best_match'] = best[0]['nombre_municipio']
                result['best_score'] = best[1]
                result['best_code'] = best[0]['codigo_municipio']
                result['best_department'] = best[0]['nombre_departamento']

                result['all_matches'] = [
                    {
                        'name': m[0]['nombre_municipio'],
                        'code': m[0]['codigo_municipio'],
                        'department': m[0]['nombre_departamento'],
                        'score': m[1]
                    }
                    for m in matches[:5]
                ]

            results.append(result)

        return results

    def export_city_mapping(self, output_path: str):
        """
        Export city mapping results to TSV for review.

        Args:
            output_path: Path to output TSV file
        """
        # Get unique cities from processed prices
        client = get_supabase_client()
        response = client.table('processed_prices').select('city').execute()

        if not response.data:
            print("No price data found")
            return

        cities = list(set(r['city'] for r in response.data if r.get('city')))
        print(f"Found {len(cities)} unique cities")

        # Generate mapping report
        report = self.generate_mapping_report(cities)

        # Write TSV
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\t'.join([
                'input_city', 'input_standardized', 'match_count',
                'best_match', 'best_code', 'best_department', 'best_score',
                'approved'  # User fills in 'yes' or 'no'
            ]) + '\n')

            for r in report:
                f.write('\t'.join([
                    r['input_city'],
                    r['input_standardized'],
                    str(r['match_count']),
                    r.get('best_match', ''),
                    r.get('best_code', ''),
                    r.get('best_department', ''),
                    f"{r['best_score']:.3f}" if r['best_score'] else '',
                    ''
                ]) + '\n')

        print(f"Mapping report saved to: {output_path}")
