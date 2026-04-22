'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { IoSearchOutline } from 'react-icons/io5';
import { cachedCall } from '@agroamigo/shared';
import { getInsumos } from '@agroamigo/shared/api/insumos';

export default function InsumosPage() {
  const router = useRouter();
  const [insumos, setInsumos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [grupo, setGrupo] = useState<string | null>(null);

  useEffect(() => {
    cachedCall('insumos:list:200', () => getInsumos({ limit: 200 }))
      .then(d => setInsumos(((d as any[]) || [])))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  const grupos = useMemo(() => Array.from(new Set(insumos.map((i: any) => i.grupo).filter(Boolean))).sort() as string[], [insumos]);

  const filtered = useMemo(() => {
    let rows = insumos;
    if (grupo) rows = rows.filter((i: any) => i.grupo === grupo);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      rows = rows.filter((i: any) => (i.canonical_name || '').toLowerCase().includes(q));
    }
    return rows;
  }, [insumos, grupo, search]);

  return (
    <div className="vstack" style={{ gap: 16 }}>
      <section className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <IoSearchOutline size={18} color="var(--color-text-tertiary)" />
          <input className="search-input" placeholder="Buscar insumos…" value={search} onChange={e => setSearch(e.target.value)} style={{ flex: 1 }} />
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className={`chip ${!grupo ? 'active' : ''}`} onClick={() => setGrupo(null)}>Todos</button>
          {grupos.map(g => (
            <button key={g} className={`chip ${grupo === g ? 'active' : ''}`} onClick={() => setGrupo(g)}>{g}</button>
          ))}
        </div>
      </section>

      <section className="card">
        {loading ? <div className="loading-container"><div className="spinner" /></div> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Insumo</th><th>Grupo</th><th>Subgrupo</th><th>CPC</th></tr></thead>
              <tbody>
                {filtered.map((i: any) => (
                  <tr key={i.id} onClick={() => router.push(`/insumo/${i.id}`)} style={{ cursor: 'pointer' }}>
                    <td style={{ fontWeight: 600 }}>{i.canonical_name}</td>
                    <td className="muted">{i.grupo || '—'}</td>
                    <td className="muted">{i.subgrupo || '—'}</td>
                    <td className="muted">{i.cpc_id || '—'}</td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan={4} style={{ textAlign: 'center', padding: 40 }} className="muted">Sin resultados</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
