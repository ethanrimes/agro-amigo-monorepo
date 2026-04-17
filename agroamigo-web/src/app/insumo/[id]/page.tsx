'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useParams } from 'next/navigation';
import { IoFlask, IoStar, IoStarOutline, IoListOutline, IoArrowUp, IoArrowDown } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOP, formatCOPCompact, formatDateShort } from '@agroamigo/shared';
import { getInsumoById, getInsumoPricesByDepartment, getInsumoPricesByMunicipality, getCpcLatestPrices, getCpcTitle } from '@agroamigo/shared/api/insumos';

type PriceSeries = 'department' | 'municipality';
import { Card } from '@/components/Card';
import { ExpandableSection } from '@/components/ExpandableSection';
import { LineChart, LineChartPoint } from '@/components/LineChart';
import { useWatchlist } from '@/context/WatchlistContext';
import { useLanguage } from '@/context/LanguageContext';
import { CommentsSection } from '@/components/CommentsSection';

const chipStyle = (active: boolean, color: string = colors.secondary) => ({
  padding: `${spacing.xs}px ${spacing.md}px`,
  borderRadius: borderRadius.full,
  whiteSpace: 'nowrap' as const,
  backgroundColor: active ? color : colors.surface,
  color: active ? colors.text.inverse : colors.text.secondary,
  border: `1px solid ${active ? color : colors.borderLight}`,
  cursor: 'pointer',
  fontSize: fontSize.xs,
  fontWeight: 500 as const,
  outline: 'none',
});

/** Blur after click so focus ring doesn't linger */
const chipClick = (handler: () => void) => (e: React.MouseEvent) => {
  (e.target as HTMLElement).blur();
  handler();
};

export default function InsumoDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { isWatched, toggle } = useWatchlist();
  const { t } = useLanguage();

  const [insumo, setInsumo] = useState<any>(null);
  const [cpcTitle, setCpcTitle] = useState('');
  const [deptPrices, setDeptPrices] = useState<any[]>([]);
  const [muniPrices, setMuniPrices] = useState<any[]>([]);
  const [cpcPrices, setCpcPrices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Chart filters
  const [series, setSeries] = useState<PriceSeries>('department');
  const [chartPresentation, setChartPresentation] = useState<string | null>(null);
  const [chartDept, setChartDept] = useState<string | null>(null);

  // CPC detail filters (multi-select arrays — empty = all)
  const [cpcSortAsc, setCpcSortAsc] = useState(false);
  const [cpcDept, setCpcDept] = useState<string[]>([]);
  const [cpcCasa, setCpcCasa] = useState<string[]>([]);
  const [cpcArticulo, setCpcArticulo] = useState<string[]>([]);
  const [cpcPresentation, setCpcPresentation] = useState<string[]>([]);

  const chartWidth = 440;

  useEffect(() => { loadInsumo(); }, [id]);

  async function loadInsumo() {
    try {
      const [ins, dept, muni] = await Promise.all([
        getInsumoById(id!),
        getInsumoPricesByDepartment(id!, 2000),
        getInsumoPricesByMunicipality(id!, undefined, 2000),
      ]);
      setInsumo(ins);
      setDeptPrices(dept || []);
      setMuniPrices(muni || []);
      if ((!dept || dept.length === 0) && muni && muni.length > 0) setSeries('municipality');

      // Fetch CPC title and CPC-wide prices
      if (ins?.cpc_id) {
        const [cpcData, title] = await Promise.all([
          getCpcLatestPrices(ins.cpc_id),
          getCpcTitle(ins.cpc_id),
        ]);
        setCpcPrices(cpcData || []);
        if (title) setCpcTitle(title);
      }
    } catch (err) { console.error(err); } finally { setLoading(false); }
  }

  const hasDept = deptPrices.length > 0;
  const hasMuni = muniPrices.length > 0;
  const activePrices = series === 'department' ? deptPrices : muniPrices;

  // Location counts
  const deptLocationCount = useMemo(() => new Set(deptPrices.map(p => p.department_id)).size, [deptPrices]);
  const muniLocationCount = useMemo(() => new Set(muniPrices.map(p => p.department_id)).size, [muniPrices]);

  // ═══ CHART CASCADE: series → presentation → department ═══

  // 1. Presentations from active series
  const chartPresentations = useMemo(() => {
    const set = new Set<string>();
    for (const p of activePrices) if (p.presentation) set.add(p.presentation);
    return Array.from(set).sort();
  }, [activePrices]);

  useEffect(() => {
    if (chartPresentation && !chartPresentations.includes(chartPresentation))
      setChartPresentation(chartPresentations[0] || null);
    else if (!chartPresentation && chartPresentations.length > 0)
      setChartPresentation(chartPresentations[0]);
  }, [chartPresentations]);

  // 2. Departments from presentation-filtered data
  const presFilteredPrices = useMemo(() => {
    if (!chartPresentation) return activePrices;
    return activePrices.filter(p => p.presentation === chartPresentation);
  }, [activePrices, chartPresentation]);

  const chartDepts = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of presFilteredPrices) {
      const name = (p as any).dim_department?.canonical_name;
      if (name && p.department_id) map.set(p.department_id, name);
    }
    return Array.from(map.entries()).sort(([, a], [, b]) => a.localeCompare(b));
  }, [presFilteredPrices]);

  useEffect(() => {
    if (chartDept && !chartDepts.some(([id]) => id === chartDept))
      setChartDept(null);
  }, [chartDepts]);

  // 3. Chart data from fully filtered prices
  const chartData: LineChartPoint[] = useMemo(() => {
    let filtered = presFilteredPrices;
    if (chartDept) filtered = filtered.filter(p => p.department_id === chartDept);

    const byDate = new Map<string, { sum: number; count: number }>();
    for (const p of filtered) {
      if (!p.avg_price || !p.price_date) continue;
      const existing = byDate.get(p.price_date);
      if (existing) { existing.sum += Number(p.avg_price); existing.count++; }
      else byDate.set(p.price_date, { sum: Number(p.avg_price), count: 1 });
    }
    return Array.from(byDate.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, { sum, count }]) => ({ date, value: sum / count }));
  }, [presFilteredPrices, chartDept]);

  // ═══ CPC FILTERS: independent multi-select at each level ═══

  const cpcDepts = useMemo(() => Array.from(new Set(cpcPrices.map(p => p.dept_name).filter(Boolean))).sort(), [cpcPrices]);
  const cpcCasas = useMemo(() => Array.from(new Set(cpcPrices.map(p => p.casa_comercial_name).filter(Boolean))).sort(), [cpcPrices]);
  const cpcArticulos = useMemo(() => Array.from(new Set(cpcPrices.map(p => p.articulo).filter(Boolean))).sort(), [cpcPrices]);
  const cpcPresentations = useMemo(() => Array.from(new Set(cpcPrices.map(p => p.presentation).filter(Boolean))).sort(), [cpcPrices]);

  const toggleCpc = (arr: string[], val: string, setter: (v: string[]) => void) => {
    setter(arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val]);
  };

  const cpcFilteredRows = useMemo(() => {
    let rows = cpcPrices;
    if (cpcDept.length > 0) rows = rows.filter(r => cpcDept.includes(r.dept_name));
    if (cpcCasa.length > 0) rows = rows.filter(r => cpcCasa.includes(r.casa_comercial_name));
    if (cpcArticulo.length > 0) rows = rows.filter(r => cpcArticulo.includes(r.articulo));
    if (cpcPresentation.length > 0) rows = rows.filter(r => cpcPresentation.includes(r.presentation));
    return [...rows].sort((a, b) => {
      const diff = (Number(a.avg_price) || 0) - (Number(b.avg_price) || 0);
      return cpcSortAsc ? diff : -diff;
    });
  }, [cpcPrices, cpcDept, cpcCasa, cpcArticulo, cpcPresentation, cpcSortAsc]);

  if (loading) return <div className="loading-container"><div className="spinner" /></div>;
  if (!insumo) return <div className="loading-container">{t.input_not_found}</div>;

  return (
    <div style={{ paddingBottom: 40 }}>
      {/* Header */}
      <div style={{ display: 'flex', padding: spacing.lg, gap: spacing.lg, backgroundColor: colors.surface, borderBottom: `1px solid ${colors.borderLight}`, alignItems: 'center', position: 'relative' }}>
        <div style={{ width: 64, height: 64, borderRadius: borderRadius.lg, backgroundColor: colors.secondary + '15', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <IoFlask size={36} color={colors.secondary} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary, textTransform: 'uppercase', letterSpacing: 0.5 }}>{insumo.grupo || ''}</div>
          <div style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary }}>{insumo.canonical_name}</div>
          {insumo.subgrupo && <div style={{ fontSize: fontSize.sm, color: colors.text.secondary }}>{insumo.subgrupo}</div>}
          {insumo.cpc_id && (
            <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>
              CPC {insumo.cpc_id}{cpcTitle ? ` — ${cpcTitle}` : ''}
            </div>
          )}
        </div>
        <button onClick={() => toggle(id!, 'insumo', insumo.canonical_name)}
          style={{ position: 'absolute', right: spacing.lg, top: spacing.lg, background: 'none', border: 'none', cursor: 'pointer' }}>
          {isWatched(id!) ? <IoStar size={22} color="#FFD700" /> : <IoStarOutline size={22} color={colors.text.tertiary} />}
        </button>
      </div>

      {/* Stats tiles */}
      <div style={{ display: 'flex', padding: `${spacing.md}px ${spacing.lg}px`, gap: spacing.md }}>
        <div style={{ flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, textAlign: 'center' }}>
          <div style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.secondary }}>{deptLocationCount}</div>
          <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{t.input_departments}</div>
          <div style={{ fontSize: 9, color: colors.text.tertiary, marginTop: 2 }}>Serie departamental</div>
        </div>
        <div style={{ flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, textAlign: 'center' }}>
          <div style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.secondary }}>{muniLocationCount}</div>
          <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{t.input_municipalities}</div>
          <div style={{ fontSize: 9, color: colors.text.tertiary, marginTop: 2 }}>Serie municipal</div>
        </div>
      </div>

      {/* Series explanation */}
      <div style={{ padding: `0 ${spacing.lg}px ${spacing.sm}px`, fontSize: fontSize.xs, color: colors.text.tertiary, lineHeight: '16px' }}>
        DANE publica dos series independientes: precios promedio por <strong>departamento</strong> (incluye marca comercial y artículo) y precios promedio por <strong>municipio</strong> (sin detalle de marca). Seleccione la serie para visualizar.
      </div>

      {/* Price history chart */}
      <Card style={{ margin: `${spacing.sm}px ${spacing.lg}px 0` }}>
        <div style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.sm }}>
          {t.input_price_history}
        </div>

        {/* Series toggle */}
        <div style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.sm }}>
          <button onClick={chipClick(() => { setSeries('department'); setChartDept(null); setChartPresentation(null); })}
            disabled={!hasDept} style={{ ...chipStyle(series === 'department'), opacity: hasDept ? 1 : 0.4 }}>
            Departamento ({deptLocationCount})
          </button>
          <button onClick={chipClick(() => { setSeries('municipality'); setChartDept(null); setChartPresentation(null); })}
            disabled={!hasMuni} style={{ ...chipStyle(series === 'municipality'), opacity: hasMuni ? 1 : 0.4 }}>
            Municipio ({muniLocationCount})
          </button>
        </div>

        {/* Presentation filter (no "All" — always select one) */}
        {chartPresentations.length >= 1 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
            {chartPresentations.map(p => (
              <button key={p} onClick={chipClick(() => setChartPresentation(p))}
                style={chipStyle(chartPresentation === p || chartPresentations.length === 1, colors.primaryDark)}>
                {p}
              </button>
            ))}
          </div>
        )}

        {/* Department filter (cascaded from presentation) */}
        {chartDepts.length >= 1 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
            {chartDepts.length > 1 && (
              <button onClick={chipClick(() => setChartDept(null))} style={chipStyle(!chartDept, colors.accent.blue)}>
                Nacional
              </button>
            )}
            {chartDepts.map(([deptId, name]) => (
              <button key={deptId} onClick={chipClick(() => setChartDept(chartDepts.length === 1 ? deptId : (chartDept === deptId ? null : deptId)))}
                style={chipStyle(chartDept === deptId || chartDepts.length === 1, colors.accent.blue)}>
                {name}
              </button>
            ))}
          </div>
        )}

        {chartData.length > 1 ? (
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <LineChart data={chartData} width={chartWidth} height={200} color={colors.secondary} formatValue={formatCOPCompact} />
          </div>
        ) : (
          <p style={{ textAlign: 'center', padding: `${spacing.xl}px 0`, color: colors.text.tertiary, fontSize: fontSize.sm }}>
            {t.input_no_data}
          </p>
        )}
      </Card>

      {/* CPC-wide price detail */}
      {cpcPrices.length > 0 && (
        <Card style={{ margin: `${spacing.md}px ${spacing.lg}px 0` }}>
          <ExpandableSection
            title={`Precios CPC ${insumo.cpc_id}`}
            subtitle={cpcTitle || undefined}
            icon={<IoListOutline size={16} color={colors.text.secondary} />}
            badge={cpcFilteredRows.length}
            initiallyExpanded
          >
            {/* Sort toggle */}
            <div style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.sm, alignItems: 'center' }}>
              <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>Ordenar:</span>
              <button onClick={chipClick(() => setCpcSortAsc(false))} style={chipStyle(!cpcSortAsc, colors.dark)}>
                Mayor <IoArrowDown size={10} style={{ verticalAlign: 'middle' }} />
              </button>
              <button onClick={chipClick(() => setCpcSortAsc(true))} style={chipStyle(cpcSortAsc, colors.dark)}>
                Menor <IoArrowUp size={10} style={{ verticalAlign: 'middle' }} />
              </button>
            </div>

            <p style={{ fontSize: fontSize.xs, color: colors.text.tertiary, fontStyle: 'italic', marginBottom: spacing.sm }}>
              Puedes seleccionar varios filtros a la vez en cada nivel.
            </p>

            {/* Geo filter */}
            {cpcDepts.length >= 1 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
                <button onClick={chipClick(() => setCpcDept([]))} style={chipStyle(cpcDept.length === 0, colors.accent.blue)}>
                  Todos los departamentos
                </button>
                {cpcDepts.map(d => (
                  <button key={d} onClick={chipClick(() => toggleCpc(cpcDept, d, setCpcDept))} style={chipStyle(cpcDept.includes(d), colors.accent.blue)}>
                    {d}
                  </button>
                ))}
              </div>
            )}

            {/* Casa comercial filter */}
            {cpcCasas.length >= 1 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
                <button onClick={chipClick(() => setCpcCasa([]))} style={chipStyle(cpcCasa.length === 0, colors.secondary)}>
                  Todas las marcas
                </button>
                {cpcCasas.map(c => (
                  <button key={c} onClick={chipClick(() => toggleCpc(cpcCasa, c, setCpcCasa))} style={chipStyle(cpcCasa.includes(c), colors.secondary)}>
                    {c}
                  </button>
                ))}
              </div>
            )}

            {/* Artículo filter */}
            {cpcArticulos.length >= 1 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
                <button onClick={chipClick(() => setCpcArticulo([]))} style={chipStyle(cpcArticulo.length === 0, colors.primary)}>
                  Todos los artículos
                </button>
                {cpcArticulos.map(a => (
                  <button key={a} onClick={chipClick(() => toggleCpc(cpcArticulo, a, setCpcArticulo))} style={chipStyle(cpcArticulo.includes(a), colors.primary)}>
                    {a}
                  </button>
                ))}
              </div>
            )}

            {/* Presentation filter */}
            {cpcPresentations.length >= 1 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
                <button onClick={chipClick(() => setCpcPresentation([]))} style={chipStyle(cpcPresentation.length === 0, colors.primaryDark)}>
                  Todas las presentaciones
                </button>
                {cpcPresentations.map(p => (
                  <button key={p} onClick={chipClick(() => toggleCpc(cpcPresentation, p, setCpcPresentation))} style={chipStyle(cpcPresentation.includes(p), colors.primaryDark)}>
                    {p}
                  </button>
                ))}
              </div>
            )}

            {/* Table rows */}
            {cpcFilteredRows.length === 0 ? (
              <p style={{ textAlign: 'center', padding: `${spacing.xl}px 0`, color: colors.text.tertiary, fontSize: fontSize.sm }}>
                {t.input_no_data}
              </p>
            ) : (
              cpcFilteredRows.map((row: any, i: number) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                  padding: `${spacing.sm}px 0`,
                  borderBottom: `1px solid ${colors.borderLight}`,
                }}>
                  <div style={{ flex: 1, marginRight: spacing.sm, minWidth: 0 }}>
                    <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row.articulo || '—'}
                    </div>
                    <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>
                      {row.dept_name}
                    </div>
                    <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>
                      {[row.casa_comercial_name, row.presentation].filter(Boolean).join(' · ')}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.secondary, fontFamily: 'monospace' }}>
                      {formatCOP(row.avg_price)}
                    </div>
                    <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>
                      {formatDateShort(row.price_date)}
                    </div>
                  </div>
                </div>
              ))
            )}
          </ExpandableSection>
        </Card>
      )}

      {/* ── COMMENTS SECTION ── */}
      <Card style={{ margin: `${spacing.lg}px ${spacing.lg}px 0` }}>
        <CommentsSection entityType="insumo" entityId={id!} />
      </Card>
    </div>
  );
}
