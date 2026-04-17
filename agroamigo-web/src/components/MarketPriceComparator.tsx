'use client';

import React, { useEffect, useState, useMemo, useRef } from 'react';
import { IoSearch, IoCloseCircle, IoSwapHorizontal } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOP, formatDateShort, formatPriceContext } from '@agroamigo/shared';
import { getMarketProducts, getNationalPriceAverages } from '@agroamigo/shared/api/markets';
import { useLanguage } from '@/context/LanguageContext';

const NATIONAL_AVG = '__national__';

interface Props {
  currentMarket: any;
  products: any[];
  markets: any[];
}

export function MarketPriceComparator({ currentMarket, products, markets }: Props) {
  const { t } = useLanguage();
  const [compId, setCompId] = useState<string | null>(null);
  const [compData, setCompData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [popup, setPopup] = useState<{ date: string; x: number; y: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  useEffect(() => {
    if (!popup) return;
    const timer = setTimeout(() => setPopup(null), 3000);
    const handler = () => setPopup(null);
    document.addEventListener('mousedown', handler);
    return () => { clearTimeout(timer); document.removeEventListener('mousedown', handler); };
  }, [popup]);

  useEffect(() => {
    if (!compId) { setCompData([]); return; }
    setLoading(true);
    const promise = compId === NATIONAL_AVG
      ? getNationalPriceAverages(products.map(p => p.product_id))
      : getMarketProducts(compId, 1000).then(data => {
          const map = new Map<string, any>();
          for (const p of (data || []) as any[]) {
            if (!map.has(p.product_id) || p.price_date > map.get(p.product_id).price_date)
              map.set(p.product_id, p);
          }
          return Array.from(map.values());
        });
    promise.then(setCompData).catch(console.error).finally(() => setLoading(false));
  }, [compId, products]);

  const comparison = useMemo(() => {
    if (!compId || compData.length === 0) return null;

    const bMap = new Map<string, any>();
    for (const p of compData) {
      bMap.set(`${p.product_id}|${p.presentation_id}|${p.units_id}`, p);
    }

    const rows: any[] = [];
    for (const a of products) {
      const key = `${a.product_id}|${a.presentation_id}|${a.units_id}`;
      const b = bMap.get(key);
      const priceA = a.avg_price ?? a.min_price;
      const priceB = b ? (b.avg_price ?? b.min_price) : null;
      const pctDiff = priceA > 0 && priceB != null ? ((priceB - priceA) / priceA) * 100 : null;

      rows.push({
        product_id: a.product_id,
        name: a.dim_product?.canonical_name || 'Producto',
        category: a.dim_product?.dim_subcategory?.dim_category?.canonical_name || 'Otro',
        subcategory: a.dim_product?.dim_subcategory?.canonical_name || 'General',
        context: formatPriceContext(a.dim_presentation?.canonical_name, a.dim_units?.canonical_name),
        priceA, priceB, pctDiff,
        dateA: a.price_date,
        dateB: b?.price_date || null,
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
    return { groups, overallAvg, matchCount: matched.length, totalA: products.length };
  }, [products, compData, compId]);

  const filteredMarkets = useMemo(() => {
    const q = search.toLowerCase();
    return markets
      .filter(m => m.id !== currentMarket.id)
      .filter(m => !q || m.canonical_name.toLowerCase().includes(q) || m.dim_city?.canonical_name?.toLowerCase()?.includes(q));
  }, [markets, search, currentMarket.id]);

  const compName = compId === NATIONAL_AVG
    ? t.compare_national_avg
    : markets.find(m => m.id === compId)?.canonical_name || '';

  const handlePriceClick = (date: string | null, e: React.MouseEvent) => {
    if (!date) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPopup({ date, x: rect.left + rect.width / 2, y: rect.top });
  };

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

  if (products.length === 0) return null;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.sm }}>
        <IoSwapHorizontal size={16} color={colors.primary} />
        <span style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.text.primary }}>{t.compare_prices_title}</span>
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
            <input
              autoFocus
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={t.compare_search_market}
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

          {/* Column headers */}
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
                fontSize: fontSize.xs, fontWeight: 700, color: colors.primary,
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
                        {row.context && <div style={{ fontSize: 10, color: colors.text.tertiary }}>{row.context}</div>}
                      </div>
                      <div
                        style={{ width: 72, textAlign: 'right', fontSize: fontSize.sm, fontFamily: 'monospace', color: colors.text.primary, cursor: 'pointer' }}
                        onClick={e => handlePriceClick(row.dateA, e)}
                      >
                        {formatCOP(row.priceA)}
                      </div>
                      <div
                        style={{ width: 72, textAlign: 'right', fontSize: fontSize.sm, fontFamily: 'monospace', color: row.priceB != null ? colors.text.primary : colors.text.tertiary, cursor: row.dateB ? 'pointer' : 'default' }}
                        onClick={e => handlePriceClick(row.dateB, e)}
                      >
                        {row.priceB != null ? formatCOP(row.priceB) : '\u2014'}
                      </div>
                      <div style={{ width: 54, textAlign: 'right', fontSize: fontSize.xs, fontWeight: 600, fontFamily: 'monospace', color: diffColor(row.pctDiff) }}>
                        {fmtDiff(row.pctDiff)}
                      </div>
                    </div>
                  ))}

                  {sub.avgDiff != null && sub.matchCount > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 2, padding: `3px ${spacing.xs}px`, backgroundColor: colors.background }}>
                      <div style={{ flex: 1, fontSize: fontSize.xs, fontWeight: 600, color: colors.text.secondary, fontStyle: 'italic' }}>
                        {sub.name}
                      </div>
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
              borderTop: `2px solid ${colors.primary}`, marginTop: spacing.sm,
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

      {popup && (
        <div style={{
          position: 'fixed', left: popup.x, top: popup.y,
          transform: 'translate(-50%, calc(-100% - 4px))',
          backgroundColor: colors.dark, color: colors.text.inverse,
          padding: '4px 8px', borderRadius: borderRadius.sm,
          fontSize: fontSize.xs, zIndex: 1000, pointerEvents: 'none',
        }}>
          {t.compare_observed} {formatDateShort(popup.date)}
        </div>
      )}
    </div>
  );
}
