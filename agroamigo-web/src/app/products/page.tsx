'use client';

import React, { useEffect, useState, useCallback, useMemo, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { IoLeaf, IoChevronForward } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize } from '@agroamigo/shared';
import { getProducts, getCategories } from '@agroamigo/shared/api/products';
import { Card } from '@/components/Card';
import { SearchBar } from '@/components/SearchBar';
import { ProductImage } from '@/components/ProductImage';

interface Section { title: string; category: string; isFirstInCategory: boolean; data: any[]; }

function buildSections(products: any[]): Section[] {
  const catMap = new Map<string, Map<string, any[]>>();
  for (const p of products) {
    const catName = p.dim_subcategory?.dim_category?.canonical_name || 'Otro';
    const subName = p.dim_subcategory?.canonical_name || 'General';
    if (!catMap.has(catName)) catMap.set(catName, new Map());
    const subMap = catMap.get(catName)!;
    if (!subMap.has(subName)) subMap.set(subName, []);
    subMap.get(subName)!.push(p);
  }
  const sections: Section[] = [];
  for (const [catName, subMap] of [...catMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    let first = true;
    for (const [subName, items] of [...subMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
      sections.push({ title: subName, category: catName, isFirstInCategory: first, data: items });
      first = false;
    }
  }
  return sections;
}

export default function ProductsPage() {
  return <Suspense fallback={<div className="loading-container"><div className="spinner" /></div>}><ProductsContent /></Suspense>;
}

function ProductsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [products, setProducts] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | undefined>(searchParams.get('categoryId') || undefined);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => { getCategories().then(c => setCategories(c || [])); }, []);
  useEffect(() => { loadProducts(); }, [selectedCategory, search]);

  async function loadProducts() {
    setLoading(true);
    try {
      const data = await getProducts({ categoryId: selectedCategory, search: search.length >= 2 ? search : undefined, limit: 600 });
      setProducts(data || []);
    } catch (err) { console.error('Error loading products:', err); }
    finally { setLoading(false); }
  }

  const sections = useMemo(() => buildSections(products), [products]);

  return (
    <div style={{ paddingTop: spacing.md, paddingBottom: 20 }}>
      <SearchBar value={search} onChangeText={setSearch} placeholder="Buscar producto..." />
      <div className="chip-scroll">
        {[{ id: undefined, canonical_name: 'Todos' }, ...categories].map(item => (
          <button key={item.id || 'all'} onClick={() => setSelectedCategory(item.id)}
            style={{
              padding: `${spacing.sm}px ${spacing.md}px`, borderRadius: borderRadius.full, whiteSpace: 'nowrap',
              backgroundColor: selectedCategory === item.id ? colors.primary : colors.surface,
              color: selectedCategory === item.id ? colors.text.inverse : colors.text.secondary,
              border: `1px solid ${selectedCategory === item.id ? colors.primary : colors.borderLight}`,
              cursor: 'pointer', fontSize: fontSize.sm, fontWeight: 500,
            }}>
            {item.canonical_name}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-container"><div className="spinner" /></div>
      ) : sections.length === 0 ? (
        <p style={{ textAlign: 'center', marginTop: 40, fontSize: fontSize.md, color: colors.text.tertiary }}>No se encontraron productos</p>
      ) : (
        sections.map((section, si) => (
          <div key={`${section.category}-${section.title}`}>
            {section.isFirstInCategory && (
              <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.lg}px ${spacing.lg}px ${spacing.xs}px` }}>
                <IoLeaf size={14} color={colors.primary} />
                <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.primary }}>{section.category}</span>
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: `${spacing.xs}px ${spacing.lg}px` }}>
              <span style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.text.secondary }}>{section.title}</span>
              <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{section.data.length}</span>
            </div>
            {section.data.map(item => (
              <Card key={item.id} style={{ margin: `0 ${spacing.lg}px ${spacing.xs}px` }} onPress={() => router.push(`/product/${item.id}`)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: spacing.md }}>
                  <ProductImage productName={item.canonical_name} categoryName={item.dim_subcategory?.dim_category?.canonical_name}
                    style={{ width: 44, height: 44, borderRadius: borderRadius.md, backgroundColor: colors.borderLight }} />
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>{item.canonical_name}</span>
                  </div>
                  <IoChevronForward size={18} color={colors.text.tertiary} />
                </div>
              </Card>
            ))}
          </div>
        ))
      )}
    </div>
  );
}
