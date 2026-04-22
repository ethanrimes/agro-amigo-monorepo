'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { IoSearchOutline } from 'react-icons/io5';
import { cachedCall } from '@agroamigo/shared';
import { getMarkets } from '@agroamigo/shared/api/markets';

export default function MarketsPage() {
  const router = useRouter();
  const [markets, setMarkets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    cachedCall('markets:all', () => getMarkets())
      .then(m => setMarkets(((m as any[]) || [])))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return markets;
    const q = search.trim().toLowerCase();
    return markets.filter((m: any) =>
      (m.canonical_name || '').toLowerCase().includes(q)
      || (m.dim_city?.canonical_name || '').toLowerCase().includes(q)
      || (m.dim_city?.dim_department?.canonical_name || '').toLowerCase().includes(q),
    );
  }, [markets, search]);

  return (
    <div className="vstack" style={{ gap: 16 }}>
      <section className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <IoSearchOutline size={18} color="var(--color-text-tertiary)" />
          <input
            className="search-input"
            placeholder="Buscar mercados por nombre, ciudad o departamento…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ flex: 1 }}
          />
        </div>
      </section>

      <section className="card">
        {loading ? (
          <div className="loading-container"><div className="spinner" /></div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Mercado</th><th>Ciudad</th><th>Departamento</th></tr>
              </thead>
              <tbody>
                {filtered.map((m: any) => (
                  <tr key={m.id} onClick={() => router.push(`/market/${m.id}`)} style={{ cursor: 'pointer' }}>
                    <td style={{ fontWeight: 600 }}>{m.canonical_name}</td>
                    <td className="muted">{m.dim_city?.canonical_name || '—'}</td>
                    <td className="muted">{m.dim_city?.dim_department?.canonical_name || '—'}</td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={3} style={{ textAlign: 'center', padding: 40 }} className="muted">Sin resultados</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
