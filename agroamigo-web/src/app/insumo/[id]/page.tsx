'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useParams } from 'next/navigation';
import { IoFlask, IoStar, IoStarOutline, IoBarChartOutline, IoListOutline } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOP, formatCOPCompact, formatDateShort } from '@agroamigo/shared';
import { getInsumoById, getInsumoPricesByDepartment } from '@agroamigo/shared/api/insumos';
import { Card } from '@/components/Card';
import { ExpandableSection } from '@/components/ExpandableSection';
import { useWatchlist } from '@/context/WatchlistContext';

export default function InsumoDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { isWatched, toggle } = useWatchlist();
  const [insumo, setInsumo] = useState<any>(null);
  const [deptPrices, setDeptPrices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadInsumo(); }, [id]);

  async function loadInsumo() {
    try {
      const [ins, prices] = await Promise.all([getInsumoById(id!), getInsumoPricesByDepartment(id!, 300)]);
      setInsumo(ins); setDeptPrices(prices || []);
    } catch (err) { console.error(err); } finally { setLoading(false); }
  }

  const latestByDept = useMemo(() => {
    const map = new Map<string, { dept: string; price: number }>();
    for (const p of deptPrices) {
      const deptName = (p as any).dim_department?.canonical_name || 'Desconocido';
      if (!map.has(deptName) && p.avg_price) map.set(deptName, { dept: deptName, price: p.avg_price });
    }
    return map;
  }, [deptPrices]);

  const deptBars = useMemo(() => Array.from(latestByDept.values()).sort((a, b) => b.price - a.price).slice(0, 15), [latestByDept]);
  const maxPrice = deptBars.length > 0 ? Math.max(...deptBars.map(d => d.price)) : 1;

  const detailRows = useMemo(() => {
    const map = new Map<string, any>();
    for (const p of deptPrices) { const deptName = (p as any).dim_department?.canonical_name || 'Desconocido'; if (!map.has(deptName)) map.set(deptName, p); }
    return [...map.values()].sort((a, b) => ((a as any).dim_department?.canonical_name || '').localeCompare((b as any).dim_department?.canonical_name || ''));
  }, [deptPrices]);

  const sharedPresentation = useMemo(() => {
    if (detailRows.length === 0) return null;
    const first = detailRows[0].presentation;
    return detailRows.every((r: any) => r.presentation === first) ? first : null;
  }, [detailRows]);

  if (loading) return <div className="loading-container"><div className="spinner" /></div>;
  if (!insumo) return <div className="loading-container">Insumo no encontrado</div>;

  return (
    <div style={{ paddingBottom: 40 }}>
      <div style={{ display: 'flex', padding: spacing.lg, gap: spacing.lg, backgroundColor: colors.surface, borderBottom: `1px solid ${colors.borderLight}`, alignItems: 'center', position: 'relative' }}>
        <div style={{ width: 64, height: 64, borderRadius: borderRadius.lg, backgroundColor: colors.secondary + '15', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <IoFlask size={36} color={colors.secondary} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary, textTransform: 'uppercase', letterSpacing: 0.5 }}>{insumo.grupo || ''}</div>
          <div style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary }}>{insumo.canonical_name}</div>
          {insumo.subgrupo && <div style={{ fontSize: fontSize.sm, color: colors.text.secondary }}>{insumo.subgrupo}</div>}
          {insumo.cpc_code && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>CPC: {insumo.cpc_code}</div>}
        </div>
        <button onClick={() => toggle(id!, 'insumo', insumo.canonical_name)}
          style={{ position: 'absolute', right: spacing.lg, top: spacing.lg, background: 'none', border: 'none', cursor: 'pointer' }}>
          {isWatched(id!) ? <IoStar size={22} color="#FFD700" /> : <IoStarOutline size={22} color={colors.text.tertiary} />}
        </button>
      </div>

      <div style={{ display: 'flex', padding: `${spacing.md}px ${spacing.lg}px`, gap: spacing.md }}>
        <div style={{ flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, textAlign: 'center' }}>
          <div style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.secondary }}>{latestByDept.size}</div>
          <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>Departamentos</div>
        </div>
        <div style={{ flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, textAlign: 'center' }}>
          <div style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.secondary }}>{deptPrices.length}</div>
          <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>Observaciones</div>
        </div>
      </div>

      <Card style={{ margin: `${spacing.md}px ${spacing.lg}px 0` }}>
        <ExpandableSection title="Precio por departamento" icon={<IoBarChartOutline size={16} color={colors.text.secondary} />} badge={deptBars.length} initiallyExpanded>
          {deptBars.length === 0 ? <p style={{ textAlign: 'center', padding: `${spacing.xl}px 0`, color: colors.text.tertiary, fontSize: fontSize.sm }}>Sin datos</p> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
              {deptBars.map(d => (
                <div key={d.dept} style={{ display: 'flex', alignItems: 'center', gap: spacing.sm }}>
                  <span style={{ width: 80, fontSize: fontSize.xs, color: colors.text.secondary, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.dept}</span>
                  <div style={{ flex: 1, height: 16, backgroundColor: colors.borderLight, borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${(d.price / maxPrice) * 100}%`, backgroundColor: colors.secondary, borderRadius: 4 }} />
                  </div>
                  <span style={{ width: 50, fontSize: fontSize.xs, color: colors.text.primary, fontFamily: 'monospace', fontWeight: 600 }}>{formatCOPCompact(d.price)}</span>
                </div>
              ))}
            </div>
          )}
        </ExpandableSection>
      </Card>

      {detailRows.length > 0 && (
        <Card style={{ margin: `${spacing.md}px ${spacing.lg}px 0` }}>
          <ExpandableSection title="Detalle de precios" icon={<IoListOutline size={16} color={colors.text.secondary} />} badge={detailRows.length}
            subtitle={sharedPresentation ? `Presentaci\u00f3n: ${sharedPresentation}` : undefined} initiallyExpanded={false}>
            {detailRows.map((p: any) => {
              const deptName = p.dim_department?.canonical_name || 'Desconocido';
              const ctx = !sharedPresentation && p.presentation ? p.presentation : '';
              return (
                <div key={deptName} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: `${spacing.sm}px 0`, borderBottom: `1px solid ${colors.borderLight}` }}>
                  <div style={{ flex: 1, marginRight: spacing.sm }}>
                    <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.text.primary }}>{deptName}</div>
                    {ctx && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{ctx}</div>}
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.secondary, fontFamily: 'monospace' }}>{formatCOP(p.avg_price)}</div>
                    <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{formatDateShort(p.price_date)}</div>
                  </div>
                </div>
              );
            })}
          </ExpandableSection>
        </Card>
      )}
    </div>
  );
}
