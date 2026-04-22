'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { IoArrowBack, IoFlask } from 'react-icons/io5';
import { colors, formatCOP, formatCOPCompact, formatDateShort, cachedCall } from '@agroamigo/shared';
import { getInsumoById, getInsumoPricesByDepartment, getInsumoPricesByMunicipality, getCpcLatestPrices, getCpcTitle } from '@agroamigo/shared/api/insumos';
import { LazyPanel } from '@/components/LazyPanel';
import { ResponsiveChart } from '@/components/ResponsiveChart';

export default function InsumoDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [insumo, setInsumo] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [cpcTitle, setCpcTitle] = useState('');
  const [deptPrices, setDeptPrices] = useState<any[]>([]);
  const [muniPrices, setMuniPrices] = useState<any[]>([]);
  const [cpcPrices, setCpcPrices] = useState<any[]>([]);

  const [priceExpanded, setPriceExpanded] = useState(false);
  const [cpcExpanded, setCpcExpanded] = useState(false);

  const [series, setSeries] = useState<'dept' | 'muni'>('dept');

  useEffect(() => {
    cachedCall(`insumo:${id}:entity`, () => getInsumoById(id!))
      .then(d => setInsumo(d))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!id || !priceExpanded) return;
    Promise.all([
      cachedCall(`insumo:${id}:prices:dept:2000`, () => getInsumoPricesByDepartment(id, 2000)).catch(() => []),
      cachedCall(`insumo:${id}:prices:muni:2000`, () => getInsumoPricesByMunicipality(id, undefined, 2000)).catch(() => []),
    ]).then(([d, m]) => {
      setDeptPrices((d as any[]) || []);
      setMuniPrices((m as any[]) || []);
      if ((!d || (d as any[]).length === 0) && m && (m as any[]).length > 0) setSeries('muni');
    });
  }, [id, priceExpanded]);

  useEffect(() => {
    if (!id || !cpcExpanded || !insumo?.cpc_id) return;
    Promise.all([
      cachedCall(`cpc:${insumo.cpc_id}:latestPrices`, () => getCpcLatestPrices(insumo.cpc_id)).catch(() => []),
      cachedCall(`cpc:${insumo.cpc_id}:title`, () => getCpcTitle(insumo.cpc_id)).catch(() => ''),
    ]).then(([rows, title]) => {
      setCpcPrices((rows as any[]) || []);
      if (title) setCpcTitle(title as string);
    });
  }, [id, cpcExpanded, insumo]);

  const chartData = useMemo(() => {
    const rows = series === 'dept' ? deptPrices : muniPrices;
    const byDate = new Map<string, { sum: number; count: number }>();
    for (const p of rows) {
      if (!p.avg_price || !p.price_date) continue;
      const e = byDate.get(p.price_date);
      if (e) { e.sum += Number(p.avg_price); e.count++; }
      else byDate.set(p.price_date, { sum: Number(p.avg_price), count: 1 });
    }
    return Array.from(byDate.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([date, v]) => ({ date, value: v.sum / v.count }));
  }, [series, deptPrices, muniPrices]);

  if (loading) return <div className="loading-container"><div className="spinner" /></div>;
  if (!insumo) return <div className="card"><h2>Insumo no encontrado</h2></div>;

  return (
    <div className="vstack" style={{ gap: 20 }}>
      <div className="hstack">
        <button onClick={() => router.back()} className="chip"><IoArrowBack size={14} /> Volver</button>
      </div>

      <section className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{
            width: 56, height: 56, borderRadius: 14,
            background: `color-mix(in srgb, ${colors.secondary} 15%, transparent)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <IoFlask size={28} color={colors.secondary} />
          </div>
          <div>
            <div className="muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4 }}>{insumo.grupo}</div>
            <h1 style={{ margin: '4px 0', fontSize: 24, fontWeight: 700 }}>{insumo.canonical_name}</h1>
            <div className="muted" style={{ fontSize: 13 }}>
              {insumo.subgrupo}{insumo.cpc_id ? ` · CPC ${insumo.cpc_id}` : ''}{cpcTitle ? ` — ${cpcTitle}` : ''}
            </div>
          </div>
        </div>
      </section>

      <LazyPanel
        title="Historial de precios"
        subtitle="Serie departamental / municipal"
        initiallyExpanded={false}
        onExpandChange={setPriceExpanded}
        right={priceExpanded && (
          <div style={{ display: 'flex', gap: 4 }} onClick={e => e.stopPropagation()}>
            <button onClick={() => setSeries('dept')} className={`chip ${series === 'dept' ? 'active' : ''}`} style={{ padding: '4px 10px', fontSize: 11 }}>Departamento</button>
            <button onClick={() => setSeries('muni')} className={`chip ${series === 'muni' ? 'active' : ''}`} style={{ padding: '4px 10px', fontSize: 11 }}>Municipio</button>
          </div>
        )}
      >
        {chartData.length > 1 ? (
          <ResponsiveChart data={chartData} height={280} color={colors.secondary} formatValue={formatCOPCompact} />
        ) : priceExpanded ? (
          <p className="muted" style={{ textAlign: 'center', padding: 40 }}>Sin suficientes datos.</p>
        ) : null}
      </LazyPanel>

      {insumo.cpc_id && (
        <LazyPanel
          title={`Precios CPC ${insumo.cpc_id}`}
          subtitle={cpcTitle || undefined}
          badge={cpcPrices.length > 0 ? cpcPrices.length : undefined}
          initiallyExpanded={false}
          onExpandChange={setCpcExpanded}
        >
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Artículo</th><th>Marca</th><th>Presentación</th><th>Departamento</th><th className="num">Precio</th><th>Fecha</th></tr></thead>
              <tbody>
                {cpcPrices.slice(0, 60).map((r: any, i: number) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{r.articulo || '—'}</td>
                    <td className="muted">{r.casa_comercial_name || '—'}</td>
                    <td className="muted">{r.presentation || '—'}</td>
                    <td className="muted">{r.dept_name || '—'}</td>
                    <td className="num" style={{ color: colors.secondary, fontWeight: 600 }}>{formatCOP(r.avg_price)}</td>
                    <td className="muted">{formatDateShort(r.price_date)}</td>
                  </tr>
                ))}
                {cpcExpanded && cpcPrices.length === 0 && (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: 40 }} className="muted">Sin datos CPC para este insumo.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </LazyPanel>
      )}
    </div>
  );
}
