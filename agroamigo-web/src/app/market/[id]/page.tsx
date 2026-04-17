'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { IoStorefront, IoLocation, IoLeaf, IoPricetagsOutline, IoCubeOutline } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOP, formatDateShort, formatPriceContext, formatKg } from '@agroamigo/shared';
import { getMarketById, getMarketProducts, getMarketSupply, getMarkets } from '@agroamigo/shared/api/markets';
import { Card } from '@/components/Card';
import { ExpandableSection } from '@/components/ExpandableSection';
import { useLanguage } from '@/context/LanguageContext';
import { MarketPriceComparator } from '@/components/MarketPriceComparator';
import { MarketSupplyComparator } from '@/components/MarketSupplyComparator';
import { CommentsSection } from '@/components/CommentsSection';

export default function MarketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useLanguage();
  const [market, setMarket] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [supply, setSupply] = useState<any[]>([]);
  const [markets, setMarkets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadMarket(); }, [id]);

  async function loadMarket() {
    try {
      const [mkt, prods, sup, allMarkets] = await Promise.all([
        getMarketById(id!),
        getMarketProducts(id!, 200),
        getMarketSupply(id!, 30).catch(() => []),
        getMarkets().catch(() => []),
      ]);
      setMarket(mkt);
      const productMap = new Map<string, any>();
      for (const p of (prods || [])) {
        const pid = p.product_id;
        if (!productMap.has(pid) || p.price_date > productMap.get(pid).price_date) productMap.set(pid, p);
      }
      setProducts(Array.from(productMap.values()));
      setSupply(sup || []);
      setMarkets(allMarkets || []);
    } catch (err) { console.error(err); } finally { setLoading(false); }
  }

  const categoryGroups = useMemo(() => {
    const catMap = new Map<string, { subcategories: Map<string, any[]> }>();
    for (const p of products) {
      const catName = p.dim_product?.dim_subcategory?.dim_category?.canonical_name || 'Otro';
      const subName = p.dim_product?.dim_subcategory?.canonical_name || 'General';
      if (!catMap.has(catName)) catMap.set(catName, { subcategories: new Map() });
      const subMap = catMap.get(catName)!.subcategories;
      if (!subMap.has(subName)) subMap.set(subName, []);
      subMap.get(subName)!.push(p);
    }
    return [...catMap.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([catName, { subcategories }]) => ({
      category: catName,
      subcategories: [...subcategories.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([name, items]) => ({ name, items })),
    }));
  }, [products]);

  const sharedDate = useMemo(() => {
    if (products.length === 0) return null;
    const first = products[0].price_date;
    return products.every(p => p.price_date === first) ? first : null;
  }, [products]);

  const totalSupplyKg = useMemo(() => supply.reduce((sum, s) => sum + (s.quantity_kg || 0), 0), [supply]);

  const supplyDateRange = useMemo(() => {
    if (supply.length === 0) return null;
    let min = supply[0].observation_date, max = supply[0].observation_date;
    for (const s of supply) {
      if (s.observation_date < min) min = s.observation_date;
      if (s.observation_date > max) max = s.observation_date;
    }
    return { from: min, to: max };
  }, [supply]);

  const topSuppliedProducts = useMemo(() => {
    const map = new Map<string, { name: string; kg: number }>();
    for (const s of supply) {
      const pid = s.product_id;
      const existing = map.get(pid);
      if (existing) existing.kg += s.quantity_kg || 0;
      else {
        const name = (s as any).dim_product?.canonical_name
          || products.find(p => p.product_id === pid)?.dim_product?.canonical_name
          || 'Producto';
        map.set(pid, { name, kg: s.quantity_kg || 0 });
      }
    }
    return Array.from(map.values()).sort((a, b) => b.kg - a.kg).slice(0, 10);
  }, [supply, products]);

  if (loading) return <div className="loading-container"><div className="spinner" /></div>;
  if (!market) return <div className="loading-container">{t.market_not_found}</div>;

  const cityName = market.dim_city?.canonical_name || '';
  const deptName = market.dim_city?.dim_department?.canonical_name || '';

  return (
    <div style={{ paddingBottom: 40 }}>
      {/* Header */}
      <div style={{ display: 'flex', padding: spacing.lg, gap: spacing.lg, backgroundColor: colors.surface, borderBottom: `1px solid ${colors.borderLight}`, alignItems: 'center' }}>
        <div style={{ width: 64, height: 64, borderRadius: borderRadius.lg, backgroundColor: colors.primary + '15', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <IoStorefront size={36} color={colors.primary} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary }}>{market.canonical_name}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <IoLocation size={14} color={colors.text.tertiary} />
            <span style={{ fontSize: fontSize.sm, color: colors.text.secondary }}>{cityName}, {deptName}</span>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', padding: `${spacing.md}px ${spacing.lg}px`, gap: spacing.md }}>
        <div style={{ flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, textAlign: 'center' }}>
          <div style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.primary }}>{products.length}</div>
          <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{t.market_products}</div>
        </div>
        <div style={{ flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, textAlign: 'center' }}>
          <div style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.primary }}>{categoryGroups.length}</div>
          <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{t.market_categories}</div>
        </div>
      </div>

      {/* ── PRICE SECTION ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.lg}px ${spacing.lg}px ${spacing.xs}px` }}>
        <IoPricetagsOutline size={18} color={colors.primary} />
        <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary }}>{t.product_price_section}</span>
      </div>

      <Card style={{ margin: `${spacing.xs}px ${spacing.lg}px 0` }}>
        <div style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.xs }}>{t.market_recent_products}</div>
        {sharedDate && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary, marginBottom: spacing.md }}>{t.market_prices_at} {formatDateShort(sharedDate)}</div>}
        {products.length === 0 ? <p style={{ textAlign: 'center', padding: `${spacing.xl}px 0`, color: colors.text.tertiary, fontSize: fontSize.sm }}>{t.market_no_recent_data}</p> :
          categoryGroups.map((group, gi) => (
            <ExpandableSection key={group.category} title={group.category} icon={<IoLeaf size={16} color={colors.primary} />}
              badge={group.subcategories.reduce((s, sub) => s + sub.items.length, 0)} initiallyExpanded={gi < 3}>
              {group.subcategories.map(sub => (
                <div key={sub.name}>
                  {group.subcategories.length > 1 && <div style={{ fontSize: fontSize.xs, fontWeight: 600, color: colors.text.tertiary, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: spacing.sm, marginBottom: spacing.xs }}>{sub.name}</div>}
                  {sub.items.map((p: any) => {
                    const ctx = formatPriceContext(p.dim_presentation?.canonical_name, p.dim_units?.canonical_name);
                    return (
                      <Card key={p.product_id} style={{ marginBottom: spacing.xs, backgroundColor: colors.background }} padding={spacing.sm} onPress={() => router.push(`/product/${p.product_id}`)}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ flex: 1, marginRight: spacing.sm }}>
                            <div style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.dim_product?.canonical_name || t.market_product_fallback}</div>
                            {ctx && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{ctx}</div>}
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.primary, fontFamily: 'monospace' }}>{formatCOP(p.min_price ?? p.avg_price)}{p.max_price != null && p.max_price !== p.min_price ? ` - ${formatCOP(p.max_price)}` : ''}</div>
                            {!sharedDate && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{formatDateShort(p.price_date)}</div>}
                          </div>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              ))}
            </ExpandableSection>
          ))}
      </Card>

      <Card style={{ margin: `${spacing.sm}px ${spacing.lg}px 0` }}>
        <MarketPriceComparator currentMarket={market} products={products} markets={markets} />
      </Card>

      {/* ── SUPPLY SECTION ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.lg}px ${spacing.lg}px ${spacing.xs}px` }}>
        <IoCubeOutline size={18} color={colors.accent.blue} />
        <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary }}>{t.product_supply_section}</span>
      </div>

      <Card style={{ margin: `${spacing.xs}px ${spacing.lg}px 0` }}>
        {supply.length === 0 ? (
          <p style={{ textAlign: 'center', padding: `${spacing.xl}px 0`, color: colors.text.tertiary, fontSize: fontSize.sm }}>{t.product_no_supply_data}</p>
        ) : (
          <>
            {supplyDateRange && (
              <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary, marginBottom: spacing.sm }}>
                {formatDateShort(supplyDateRange.from)} – {formatDateShort(supplyDateRange.to)}
              </div>
            )}
            <div style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.md }}>
              <div style={{ flex: 1, backgroundColor: colors.accent.blue + '10', borderRadius: borderRadius.md, padding: spacing.sm, textAlign: 'center' }}>
                <div style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.accent.blue }}>{formatKg(totalSupplyKg)}</div>
                <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{t.product_total}</div>
              </div>
            </div>
            {topSuppliedProducts.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
                {topSuppliedProducts.map(d => (
                  <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: spacing.sm }}>
                    <span style={{ width: 100, fontSize: fontSize.xs, color: colors.text.secondary, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</span>
                    <div style={{ flex: 1, height: 16, backgroundColor: colors.borderLight, borderRadius: 4, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${(d.kg / topSuppliedProducts[0].kg) * 100}%`, backgroundColor: colors.accent.blue, borderRadius: 4 }} />
                    </div>
                    <span style={{ width: 55, fontSize: fontSize.xs, color: colors.text.primary, fontFamily: 'monospace', fontWeight: 600 }}>{formatKg(d.kg)}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </Card>

      <Card style={{ margin: `${spacing.sm}px ${spacing.lg}px 0` }}>
        <MarketSupplyComparator currentMarket={market} supply={supply} products={products} markets={markets} />
      </Card>

      {/* ── COMMENTS SECTION ── */}
      <Card style={{ margin: `${spacing.lg}px ${spacing.lg}px 0` }}>
        <CommentsSection entityType="market" entityId={id!} />
      </Card>
    </div>
  );
}
