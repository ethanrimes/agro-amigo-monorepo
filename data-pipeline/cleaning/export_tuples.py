"""
Export data tuples for manual review before generating dimension tables.

Generates TSV files with raw values, standardized values, and occurrence counts.
"""

import os
from collections import Counter
from pathlib import Path
from typing import List, Dict, Tuple

import sys

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import EXPORTS_DIR
from backend.supabase_client import get_supabase_client
from cleaning.standardizer import Standardizer


def get_processed_prices_data() -> List[Dict]:
    """Fetch all processed prices from the database."""
    client = get_supabase_client()

    # Fetch all records (paginated for large datasets)
    all_records = []
    page_size = 1000
    offset = 0

    while True:
        response = client.table('processed_prices').select(
            'category, subcategory, product, presentation, city, market'
        ).range(offset, offset + page_size - 1).execute()

        if not response.data:
            break

        all_records.extend(response.data)
        offset += page_size

        if len(response.data) < page_size:
            break

    return all_records


def export_categories(records: List[Dict], output_dir: Path) -> int:
    """Export category tuples."""
    # Count occurrences
    counter = Counter(r['category'] for r in records if r.get('category'))

    # Generate export data
    rows = []
    for raw_value, count in counter.most_common():
        std = Standardizer.get_all_standardizations(raw_value, 'category')
        rows.append({
            'raw_value': raw_value,
            'standardized_value': std['standardized'],
            'comparison_key': std['comparison_key'],
            'occurrence_count': count,
            'suggested_id': '',  # User fills in
            'canonical_name': ''  # User fills in
        })

    # Write TSV
    output_path = output_dir / 'categories.tsv'
    write_tsv(output_path, rows, [
        'raw_value', 'standardized_value', 'comparison_key',
        'occurrence_count', 'suggested_id', 'canonical_name'
    ])

    return len(rows)


def export_category_subcategory(records: List[Dict], output_dir: Path) -> int:
    """Export category-subcategory pairs."""
    # Count occurrences
    counter = Counter(
        (r['category'], r['subcategory'])
        for r in records
        if r.get('category') and r.get('subcategory')
    )

    rows = []
    for (cat, subcat), count in counter.most_common():
        cat_std = Standardizer.get_all_standardizations(cat, 'category')
        subcat_std = Standardizer.get_all_standardizations(subcat, 'category')
        rows.append({
            'category_raw': cat,
            'category_standardized': cat_std['standardized'],
            'subcategory_raw': subcat,
            'subcategory_standardized': subcat_std['standardized'],
            'comparison_key': f"{cat_std['comparison_key']}|{subcat_std['comparison_key']}",
            'occurrence_count': count,
            'suggested_id': '',
            'canonical_name': ''
        })

    output_path = output_dir / 'category_subcategory.tsv'
    write_tsv(output_path, rows, [
        'category_raw', 'category_standardized',
        'subcategory_raw', 'subcategory_standardized',
        'comparison_key', 'occurrence_count', 'suggested_id', 'canonical_name'
    ])

    return len(rows)


def export_category_subcategory_product(records: List[Dict], output_dir: Path) -> int:
    """Export category-subcategory-product tuples."""
    counter = Counter(
        (r['category'], r['subcategory'] or '', r['product'])
        for r in records
        if r.get('category') and r.get('product')
    )

    rows = []
    for (cat, subcat, prod), count in counter.most_common():
        cat_std = Standardizer.get_all_standardizations(cat, 'category')
        subcat_std = Standardizer.get_all_standardizations(subcat, 'category')
        prod_std = Standardizer.get_all_standardizations(prod, 'product')

        rows.append({
            'category_raw': cat,
            'category_standardized': cat_std['standardized'],
            'subcategory_raw': subcat,
            'subcategory_standardized': subcat_std['standardized'],
            'product_raw': prod,
            'product_standardized': prod_std['standardized'],
            'comparison_key': f"{cat_std['comparison_key']}|{subcat_std['comparison_key']}|{prod_std['comparison_key']}",
            'occurrence_count': count,
            'suggested_id': '',
            'canonical_name': ''
        })

    output_path = output_dir / 'category_subcategory_product.tsv'
    write_tsv(output_path, rows, [
        'category_raw', 'category_standardized',
        'subcategory_raw', 'subcategory_standardized',
        'product_raw', 'product_standardized',
        'comparison_key', 'occurrence_count', 'suggested_id', 'canonical_name'
    ])

    return len(rows)


def export_full_product_hierarchy(records: List[Dict], output_dir: Path) -> int:
    """Export category-subcategory-product-presentation tuples."""
    counter = Counter(
        (r['category'], r['subcategory'] or '', r['product'], r['presentation'] or '')
        for r in records
        if r.get('category') and r.get('product')
    )

    rows = []
    for (cat, subcat, prod, pres), count in counter.most_common():
        cat_std = Standardizer.get_all_standardizations(cat, 'category')
        subcat_std = Standardizer.get_all_standardizations(subcat, 'category')
        prod_std = Standardizer.get_all_standardizations(prod, 'product')
        pres_std = Standardizer.get_all_standardizations(pres, 'generic')

        rows.append({
            'category_raw': cat,
            'subcategory_raw': subcat,
            'product_raw': prod,
            'presentation_raw': pres,
            'category_std': cat_std['standardized'],
            'subcategory_std': subcat_std['standardized'],
            'product_std': prod_std['standardized'],
            'presentation_std': pres_std['standardized'],
            'comparison_key': f"{cat_std['comparison_key']}|{subcat_std['comparison_key']}|{prod_std['comparison_key']}|{pres_std['comparison_key']}",
            'occurrence_count': count,
            'suggested_id': '',
            'canonical_name': ''
        })

    output_path = output_dir / 'category_subcategory_product_presentation.tsv'
    write_tsv(output_path, rows, [
        'category_raw', 'subcategory_raw', 'product_raw', 'presentation_raw',
        'category_std', 'subcategory_std', 'product_std', 'presentation_std',
        'comparison_key', 'occurrence_count', 'suggested_id', 'canonical_name'
    ])

    return len(rows)


def export_city_market(records: List[Dict], output_dir: Path) -> int:
    """Export city-market tuples."""
    counter = Counter(
        (r['city'], r['market'] or '')
        for r in records
        if r.get('city')
    )

    rows = []
    for (city, market), count in counter.most_common():
        city_std = Standardizer.get_all_standardizations(city, 'city')
        market_std = Standardizer.get_all_standardizations(market, 'generic')

        rows.append({
            'city_raw': city,
            'city_standardized': city_std['standardized'],
            'market_raw': market,
            'market_standardized': market_std['standardized'],
            'comparison_key': f"{city_std['comparison_key']}|{market_std['comparison_key']}",
            'occurrence_count': count,
            'divipola_code': '',  # User fills in
            'department': '',  # User fills in
            'canonical_city': '',
            'canonical_market': ''
        })

    output_path = output_dir / 'city_market.tsv'
    write_tsv(output_path, rows, [
        'city_raw', 'city_standardized', 'market_raw', 'market_standardized',
        'comparison_key', 'occurrence_count',
        'divipola_code', 'department', 'canonical_city', 'canonical_market'
    ])

    return len(rows)


def write_tsv(path: Path, rows: List[Dict], columns: List[str]):
    """Write data to TSV file."""
    with open(path, 'w', encoding='utf-8') as f:
        # Header
        f.write('\t'.join(columns) + '\n')

        # Data rows
        for row in rows:
            values = [str(row.get(col, '')) for col in columns]
            f.write('\t'.join(values) + '\n')


def export_all_tuples(output_dir: str = None) -> int:
    """
    Export all data tuples for manual review.

    Args:
        output_dir: Output directory path

    Returns:
        0 on success, 1 on error
    """
    print("=" * 60)
    print("Exporting Data Tuples for Review")
    print("=" * 60)

    if output_dir:
        out_path = Path(output_dir)
    else:
        out_path = EXPORTS_DIR

    out_path.mkdir(parents=True, exist_ok=True)

    print(f"Output directory: {out_path}")

    # Fetch data
    print("\nFetching processed prices...")
    records = get_processed_prices_data()
    print(f"Found {len(records)} price records")

    if not records:
        print("No records found. Run the pipeline first.")
        return 1

    # Export each tuple type
    print("\nExporting tuples...")

    count = export_categories(records, out_path)
    print(f"  categories.tsv: {count} unique values")

    count = export_category_subcategory(records, out_path)
    print(f"  category_subcategory.tsv: {count} unique pairs")

    count = export_category_subcategory_product(records, out_path)
    print(f"  category_subcategory_product.tsv: {count} unique tuples")

    count = export_full_product_hierarchy(records, out_path)
    print(f"  category_subcategory_product_presentation.tsv: {count} unique tuples")

    count = export_city_market(records, out_path)
    print(f"  city_market.tsv: {count} unique pairs")

    print("\n" + "=" * 60)
    print("Export Complete")
    print("=" * 60)
    print(f"Files saved to: {out_path}")
    print("\nNext steps:")
    print("1. Review the exported TSV files")
    print("2. Fill in 'suggested_id' and 'canonical_name' columns")
    print("3. Run 'generate-dimensions' to create dimension tables")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(export_all_tuples())
