"""
Text standardization utilities for normalizing SIPSA data.

Handles accents, encoding issues, and text normalization
while preserving original values for reference.
"""

import re
import unicodedata
from typing import Dict, Optional


class Standardizer:
    """Standardizes text values for comparison and matching."""

    # Common encoding issues and their corrections
    ENCODING_FIXES = {
        'Medell¡n': 'Medellín',
        'Bogot ': 'Bogotá',
        'Bogot': 'Bogotá',
        'Bogota': 'Bogotá',
        'BogotÃ¡': 'Bogotá',
        'Ã¡': 'á',
        'Ã©': 'é',
        'Ã­': 'í',
        'Ã³': 'ó',
        'Ãº': 'ú',
        'Ã±': 'ñ',
        'Ã': 'í',
        '¡': 'í',
        '¢': 'ó',
        '£': 'ú',
    }

    # Common spelling variations to standardize
    SPELLING_VARIATIONS = {
        'tuberculos': 'tubérculos',
        'tuberculos, raices y platanos': 'tubérculos, raíces y plátanos',
        'raices': 'raíces',
        'platanos': 'plátanos',
        'platano': 'plátano',
        'citricos': 'cítricos',
        'citrico': 'cítrico',
        'limon': 'limón',
        'papa criolla': 'papa criolla',
        'oregano': 'orégano',
    }

    @classmethod
    def fix_encoding(cls, text: str) -> str:
        """
        Fix common encoding issues in text.

        Args:
            text: Input text

        Returns:
            Text with encoding issues fixed
        """
        if not text:
            return ""

        result = text

        # Apply encoding fixes
        for wrong, correct in cls.ENCODING_FIXES.items():
            result = result.replace(wrong, correct)

        return result

    @classmethod
    def normalize_accents(cls, text: str) -> str:
        """
        Normalize accented characters to their base form for comparison.

        Args:
            text: Input text

        Returns:
            Text with accents removed (for comparison keys)
        """
        if not text:
            return ""

        # Normalize unicode and decompose accented characters
        normalized = unicodedata.normalize('NFKD', text)

        # Remove combining characters (accents)
        ascii_text = ''.join(
            c for c in normalized
            if not unicodedata.combining(c)
        )

        return ascii_text

    @classmethod
    def create_comparison_key(cls, text: str) -> str:
        """
        Create a standardized key for comparing text values.

        This is used to identify equivalent values that differ only in
        capitalization, accents, or spacing.

        Args:
            text: Input text

        Returns:
            Standardized comparison key
        """
        if not text:
            return ""

        # Fix encoding first
        result = cls.fix_encoding(text)

        # Convert to lowercase
        result = result.lower()

        # Normalize accents for comparison
        result = cls.normalize_accents(result)

        # Normalize whitespace
        result = ' '.join(result.split())

        # Remove punctuation except hyphens
        result = re.sub(r'[^\w\s-]', '', result)

        return result.strip()

    @classmethod
    def standardize_category(cls, category: str) -> str:
        """
        Standardize a category name while preserving readability.

        Args:
            category: Raw category name

        Returns:
            Standardized category name
        """
        if not category:
            return ""

        result = cls.fix_encoding(category)

        # Apply spelling corrections
        lower = result.lower()
        for wrong, correct in cls.SPELLING_VARIATIONS.items():
            if wrong in lower:
                # Preserve original case pattern
                result = re.sub(wrong, correct, result, flags=re.IGNORECASE)

        # Normalize whitespace
        result = ' '.join(result.split())

        # Capitalize first letter of each major word
        words = result.split()
        if words:
            result = words[0].capitalize() + ' ' + ' '.join(words[1:]) if len(words) > 1 else words[0].capitalize()

        return result.strip()

    @classmethod
    def standardize_city(cls, city: str) -> str:
        """
        Standardize a city name.

        Args:
            city: Raw city name

        Returns:
            Standardized city name
        """
        if not city:
            return ""

        result = cls.fix_encoding(city)

        # Normalize whitespace
        result = ' '.join(result.split())

        # Title case
        # Special handling for "D.C." in Bogotá
        if 'd.c.' in result.lower():
            result = re.sub(r'd\.c\.', 'D.C.', result, flags=re.IGNORECASE)

        return result.strip()

    @classmethod
    def standardize_product(cls, product: str) -> str:
        """
        Standardize a product name.

        Args:
            product: Raw product name

        Returns:
            Standardized product name
        """
        if not product:
            return ""

        result = cls.fix_encoding(product)

        # Remove asterisks (but preserve for original)
        result = result.replace('*', '').strip()

        # Apply spelling corrections
        lower = result.lower()
        for wrong, correct in cls.SPELLING_VARIATIONS.items():
            if wrong in lower:
                result = re.sub(wrong, correct, result, flags=re.IGNORECASE)

        # Normalize whitespace
        result = ' '.join(result.split())

        return result.strip()

    @classmethod
    def get_all_standardizations(cls, text: str, text_type: str = 'generic') -> Dict[str, str]:
        """
        Get all standardization forms for a text value.

        Args:
            text: Input text
            text_type: Type of text ('category', 'city', 'product', 'generic')

        Returns:
            Dict with 'original', 'standardized', and 'comparison_key'
        """
        standardizers = {
            'category': cls.standardize_category,
            'city': cls.standardize_city,
            'product': cls.standardize_product,
            'generic': cls.fix_encoding
        }

        standardize_func = standardizers.get(text_type, cls.fix_encoding)

        return {
            'original': text,
            'standardized': standardize_func(text),
            'comparison_key': cls.create_comparison_key(text)
        }
