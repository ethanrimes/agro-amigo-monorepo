'use client';

import React, { useEffect, useState, useMemo, useRef } from 'react';
import { IoSearch, IoCloseCircle, IoSwapHorizontal } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatKg } from '@agroamigo/shared';
import { getMarketSupply, getNationalSupplyAverages } from '@agroamigo/shared/api/markets';
import { useLanguage } from '@/context/LanguageContext';

const NATIONAL_AVG = '__national__';

interface Props {
  currentMarket: any;
  supply: any[];
  products: any[];
  markets: any[];
}

export function MarketSupplyComparator({ currentMarket, supply, products, markets }: Props) {
  const { t } = useLanguage();
  const [compId, setCompId] = useState<string | null>(null);
  const [compData, setCompData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const supplyA = useMemo(() => {
    const map = new Map<string, number>();
    for (const s of supply) map.set(s.product_id, (map.get(s.product_id) || 0) + (s.quantity_kg || 0));
    return map;
  }, [supply]);

  const productInfo = useMemo(() => {
    const map = new Map<string, { name: string; category: string; subcategory: string }>();
    for (const p of products) {
      map.set(p.product_id, {
        name: p.dim_product?.canonical_name || 'Producto',
        category: p.dim_product?.dim_subcategory?.dim_category?.canonical_name || 'Otro',
        subcategory: p.dim_product?.dim_subcategory?.canonical_name || 'General',
      });
    }
    for (const s of supply) {
      if (!map.has(s.product_id)) {
        map.set(s.product_id, {
          name: (s as any).dim_product?.canonical_name || 'Producto',
          category: 'Otro',
          subcategory: 'General',
        });
      }
    }
    return map;
  }, [products, supply]);

  useEffect(() => {
    if (!compId) { setCompData([]); return; }
    setLoading(true);
    const pids = Array.from(supplyA.keys());
    const promise = compId === NATIONAL_AVG
      ? getNationalSupplyAverages(pids, 30)
      : getMarketSupply(compId, 30).then(data => {
          const map = new Map<string, number>();
          for (const s of (data || []) as any[]) map.set(s.product_id, (map.get(s.product_id) || 0) + (s.quantity_kg || 0));
          return Array.from(map.entries()).map(([product_id, quantity_kg]) => ({ product_id, quantity_kg }));
        });
    promise.then(setCompData).catch(console.error).finally(() => setLoading(false));
  }, [compId, supplyA]);

  const comparison = useMemo(() => {
    if (!compId || compData.length === 0) return null;

    const bMap = new Map<string, number>();
    for (const s of compData) bMap.set(s.product_id, s.quantity_kg);

    const rows: any[] = [];
    for (const [pid, kgA] of supplyA) {
      const kgB = bMap.get(pid);
      if (kgB == null) continue;
      const info = productInfo.get(pid);
      const pctDiff = kgA > 0 ? ((kgB - kgA) / kgA) * 100 : null;
      rows.push({
        product_id: pid,
        name: info?.name || 'Producto',
        category: info?.category || 'Otro',
        subcategory: info?.subcategory || 'General',
        kgA, kgB, pctDiff,
      });
    }

    const catMap = new Map<string, Map<string, any[]>>();
    for (const r of rows) {
      if (!catMap.has(r.category)) catMap.set(r.category, new Map());
      const sub = catMap.get(r.category)!;
      if (!sub.has(r.subcategory)) sub.set(r.subcategory, []);
      sub.get(r.subcategory)!.push(r);
    }

    const groups = [...catMap.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([cat, subMap]) => ({
        category: cat,
        subcategories: [...subMap.entries()]
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([name, items]) => {
            const matched = items.filter((r: any) => r.pctDiff != null);
            return {
              name,
              items: items.sort((a: any, b: any) => a.name.localeCompare(b.name)),
              avgDiff: matched.length > 0 ? matched.reduce((s: number, r: any) => s + r.pctDiff, 0) / matched.length : null,
              matchCount: matched.length,
            };
          }),
      }));

    const matched = rows.filter(r => r.pctDiff != null);
    const overallAvg = matched.length > 0 ? matched.reduce((s, r) => s + r.pctDiff, 0) / matched.length : null;
    return { groups, overallAvg, matchCount: matched.length, totalA: supplyA.size };
  }, [supplyA, compData, productInfo, compId]);

  const filteredMarkets = useMemo(() => {
    const q = search.toLowerCase();
    return markets
      .filter(m => m.id !== currentMarket.id)
      .filter(m => !q || m.canonical_name.toLowerCase().includes(q) || m.dim_city?.canonical_name?.toLowerCase()?.includes(q));
  }, [markets, search, currentMarket.id]);

  const compName = compId === NATIONAL_AVG ? t.compare_national_avg : markets.find(m => m.id === compId)?.canonical_name || '';

  const diffColor = (pct: number | null) => {
    if (pct == null) return colors.text.tertiary;
    if (pct > 2) return colors.price.up;
    if (pct < -2) return colors.price.down;
    return colors.text.tertiary;
  };

  const fmtDiff = (pct: number | null) => {
    if (pct == null) return '\u2014';
    return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
  };

  if (supply.length === 0) return null;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.sm }}>
        <IoSwapHorizontal size={16} color={colors.accent.blue} />
        <span style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.text.primary }}>{t.compare_supply_title}</span>
      </div>

      {/* Market dropdown */}
      <div ref={ref} style={{ position: 'relative', marginBottom: spacing.md }}>
        <div
          onClick={() => { setOpen(!open); if (!open) setSearch(''); }}
          style={{
            display: 'flex', alignItems: 'center', gap: spacing.sm,
            padding: `${spacing.sm}px ${spacing.md}px`,
            backgroundColor: colors.background, border: `1px solid ${colors.borderLight}`,
            borderRadius: borderRadius.md, cursor: 'pointer',
          }}
        >
          <IoSearch size={14} color={colors.text.tertiary} />
          {open ? (
            <input autoFocus value={search} onChange={e => setSearch(e.target.value)} placeholder={t.compare_search_market}
              onClick={e => e.stopPropagation()}
              style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', fontSize: fontSize.sm, color: colors.text.primary, fontFamily: 'inherit' }}
            />
          ) : (
            <span style={{ flex: 1, fontSize: fontSize.sm, color: compId ? colors.text.primary : colors.text.tertiary }}>
              {compId ? compName : t.compare_select_market}
            </span>
          )}
          {compId && !open && (
            <button onClick={e => { e.stopPropagation(); setCompId(null); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex' }}>
              <IoCloseCircle size={16} color={colors.text.tertiary} />
            </button>
          )}
        </div>

        {open && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
            backgroundColor: colors.surface, border: `1px solid ${colors.borderLight}`,
            borderRadius: borderRadius.md, marginTop: 2, maxHeight: 240, overflowY: 'auto',
            boxShadow: `0 4px 12px ${colors.shadow}`,
          }}>
            <div
              onClick={() => { setCompId(NATIONAL_AVG); setOpen(false); }}
              style={{ padding: `${spacing.sm}px ${spacing.md}px`, cursor: 'pointer', borderBottom: `1px solid ${colors.borderLight}` }}
              onMouseEnter={e => (e.currentTarget.style.backgroundColor = colors.primary + '10')}
              onMouseLeave={e => (e.currentTarget.style.backgroundColor = 'transparent')}
            >
              <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.primary }}>{t.compare_national_avg}</div>
              <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.compare_all_markets}</div>
            </div>
            {filteredMarkets.map(m => (
              <div
                key={m.id}
                onClick={() => { setCompId(m.id); setOpen(false); }}
                style={{ padding: `${spacing.sm}px ${spacing.md}px`, cursor: 'pointer' }}
                onMouseEnter={e => (e.currentTarget.style.backgroundColor = colors.primary + '10')}
                onMouseLeave={e => (e.currentTarget.style.backgroundColor = 'transparent')}
              >
                <div style={{ fontSize: fontSize.sm, color: colors.text.primary }}>{m.canonical_name}</div>
                <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>
                  {m.dim_city?.canonical_name}{m.dim_city?.dim_department ? `, ${m.dim_city.dim_department.canonical_name}` : ''}
                </div>
              </div>
            ))}
            {filteredMarkets.length === 0 && (
              <div style={{ padding: spacing.md, textAlign: 'center', color: colors.text.tertiary, fontSize: fontSize.sm }}>
                {t.compare_no_results}
              </div>
            )}
          </div>
        )}
      </div>

      {loading && <div style={{ textAlign: 'center', padding: spacing.xl, color: colors.text.tertiary, fontSize: fontSize.sm }}>{t.compare_loading}</div>}

      {!loading && compId && comparison && comparison.matchCount > 0 && (
        <>
          <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary, marginBottom: spacing.sm }}>
            {comparison.matchCount} / {comparison.totalA} {t.compare_matching}
          </div>

          <div style={{ display: 'flex', gap: 2, padding: `0 ${spacing.xs}px`, marginBottom: spacing.xs }}>
            <div style={{ flex: 1, fontSize: fontSize.xs, color: colors.text.tertiary, fontWeight: 600 }}>{t.compare_product}</div>
            <div style={{ width: 72, fontSize: fontSize.xs, color: colors.text.tertiary, fontWeight: 600, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {currentMarket.canonical_name}
            </div>
            <div style={{ width: 72, fontSize: fontSize.xs, color: colors.text.tertiary, fontWeight: 600, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {compName}
            </div>
            <div style={{ width: 54, fontSize: fontSize.xs, color: colors.text.tertiary, fontWeight: 600, textAlign: 'right' }}>{t.compare_diff}</div>
          </div>

          {comparison.groups.map(group => (
            <div key={group.category}>
              <div style={{
                fontSize: fontSize.xs, fontWeight: 700, color: colors.accent.blue,
                textTransform: 'uppercase', letterSpacing: 0.5,
                padding: `${spacing.xs}px`, marginTop: spacing.xs,
                borderBottom: `1px solid ${colors.borderLight}`,
              }}>
                {group.category}
              </div>

              {group.subcategories.map(sub => (
                <div key={sub.name}>
                  {group.subcategories.length > 1 && (
                    <div style={{ fontSize: fontSize.xs, fontWeight: 600, color: colors.text.secondary, padding: `${spacing.xs}px`, marginTop: 2 }}>
                      {sub.name}
                    </div>
                  )}

                  {sub.items.map((row: any) => (
                    <div key={row.product_id} style={{ display: 'flex', alignItems: 'center', gap: 2, padding: `3px ${spacing.xs}px`, borderBottom: `1px solid ${colors.borderLight}20` }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: fontSize.sm, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.name}</div>
                      </div>
                      <div style={{ width: 72, textAlign: 'right', fontSize: fontSize.sm, fontFamily: 'monospace', color: colors.text.primary }}>
                        {formatKg(row.kgA)}
                      </div>
                      <div style={{ width: 72, textAlign: 'right', fontSize: fontSize.sm, fontFamily: 'monospace', color: colors.text.primary }}>
                        {formatKg(row.kgB)}
                      </div>
                      <div style={{ width: 54, textAlign: 'right', fontSize: fontSize.xs, fontWeight: 600, fontFamily: 'monospace', color: diffColor(row.pctDiff) }}>
                        {fmtDiff(row.pctDiff)}
                      </div>
                    </div>
                  ))}

                  {sub.avgDiff != null && sub.matchCount > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 2, padding: `3px ${spacing.xs}px`, backgroundColor: colors.background }}>
                      <div style={{ flex: 1, fontSize: fontSize.xs, fontWeight: 600, color: colors.text.secondary, fontStyle: 'italic' }}>{sub.name}</div>
                      <div style={{ width: 72 }} />
                      <div style={{ width: 72 }} />
                      <div style={{ width: 54, textAlign: 'right', fontSize: fontSize.xs, fontWeight: 700, fontFamily: 'monospace', color: diffColor(sub.avgDiff) }}>
                        {fmtDiff(sub.avgDiff)}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))}

          {comparison.overallAvg != null && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 2,
              padding: `${spacing.sm}px ${spacing.xs}px`,
              borderTop: `2px solid ${colors.accent.blue}`, marginTop: spacing.sm,
            }}>
              <div style={{ flex: 1, fontSize: fontSize.sm, fontWeight: 700, color: colors.text.primary }}>{t.compare_overall_avg}</div>
              <div style={{ width: 72 }} />
              <div style={{ width: 72 }} />
              <div style={{ width: 54, textAlign: 'right', fontSize: fontSize.sm, fontWeight: 700, fontFamily: 'monospace', color: diffColor(comparison.overallAvg) }}>
                {fmtDiff(comparison.overallAvg)}
              </div>
            </div>
          )}
        </>
      )}

      {!loading && compId && (!comparison || comparison.matchCount === 0) && (
        <div style={{ textAlign: 'center', padding: spacing.xl, color: colors.text.tertiary, fontSize: fontSize.sm }}>{t.compare_no_match}</div>
      )}
    </div>
  );
}
