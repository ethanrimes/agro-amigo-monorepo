'use client';

import React, { Suspense, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { IoSearchOutline, IoChevronDown, IoChevronUp } from 'react-icons/io5';
import { colors, formatCOP, formatDateShort, cachedCall } from '@agroamigo/shared';
import { getCategories, getProducts } from '@agroamigo/shared/api/products';

type SortKey = 'name' | 'price' | 'date';
type SortDir = 'asc' | 'desc';

export default function ProductsPage() {
  return (
    <Suspense fallback={<div className="loading-container"><div className="spinner" /></div>}>
      <ProductsPageInner />
    </Suspense>
  );
}

function ProductsPageInner() {
  const router = useRouter();
  const sp = useSearchParams();
  const initialCategory = sp.get('category') || null;

  const [categories, setCategories] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string | null>(initialCategory);
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  useEffect(() => {
    (async () => {
      try {
        const [cats, prods] = await Promise.all([
          cachedCall('home:categories', () => getCategories()),
          cachedCall('products:list:200', () => getProducts({ limit: 200 })),
        ]);
        setCategories(((cats as any[]) || []));
        setProducts(((prods as any[]) || []));
      } catch (err) { console.error(err); }
      finally { setLoading(false); }
    })();
  }, []);

  const filtered = useMemo(() => {
    let rows = products;
    if (category) {
      rows = rows.filter((p: any) => (p.dim_subcategory?.dim_category?.canonical_name || '').toLowerCase() === category.toLowerCase());
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      rows = rows.filter((p: any) => (p.canonical_name || '').toLowerCase().includes(q));
    }
    rows = [...rows].sort((a: any, b: any) => {
      let cmp = 0;
      if (sortKey === 'name') cmp = (a.canonical_name || '').localeCompare(b.canonical_name || '');
      else if (sortKey === 'price') cmp = (a.latest_avg_price || 0) - (b.latest_avg_price || 0);
      else if (sortKey === 'date') cmp = (a.latest_date || '').localeCompare(b.latest_date || '');
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return rows;
  }, [products, category, search, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir(key === 'name' ? 'asc' : 'desc'); }
  }

  function SortHeader({ k, label, align }: { k: SortKey; label: string; align?: 'right' }) {
    return (
      <th style={{ cursor: 'pointer', textAlign: align || 'left' }} onClick={() => toggleSort(k)}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          {label}
          {sortKey === k && (sortDir === 'asc' ? <IoChevronUp size={10} /> : <IoChevronDown size={10} />)}
        </span>
      </th>
    );
  }

  return (
    <div className="vstack" style={{ gap: 16 }}>
      <section className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <IoSearchOutline size={18} color="var(--color-text-tertiary)" />
          <input
            className="search-input"
            placeholder="Buscar productos…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ flex: 1 }}
          />
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className={`chip ${!category ? 'active' : ''}`} onClick={() => setCategory(null)}>Todas</button>
          {categories.map(c => (
            <button
              key={c.id}
              className={`chip ${category?.toLowerCase() === c.canonical_name.toLowerCase() ? 'active' : ''}`}
              onClick={() => setCategory(c.canonical_name)}
            >
              {c.canonical_name}
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        {loading ? (
          <div className="loading-container"><div className="spinner" /></div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <SortHeader k="name" label="Producto" />
                  <th>Categoría</th>
                  <SortHeader k="price" label="Precio" align="right" />
                  <SortHeader k="date" label="Última observación" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((p: any) => (
                  <tr
                    key={p.id}
                    onClick={() => router.push(`/product/${p.id}`)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ fontWeight: 600 }}>{p.canonical_name}</td>
                    <td className="muted">{p.dim_subcategory?.dim_category?.canonical_name || '—'}</td>
                    <td className="num" style={{ color: colors.primary, fontWeight: 600 }}>
                      {p.latest_avg_price ? formatCOP(p.latest_avg_price) : '—'}
                    </td>
                    <td className="muted">{p.latest_date ? formatDateShort(p.latest_date) : '—'}</td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={4} style={{ textAlign: 'center', padding: 40 }} className="muted">Sin resultados</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
