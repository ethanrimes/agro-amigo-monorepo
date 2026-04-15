'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { IoStorefront, IoLocation, IoLeaf } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOP, formatDateShort, formatPriceContext } from '@agroamigo/shared';
import { getMarketById, getMarketProducts } from '@agroamigo/shared/api/markets';
import { Card } from '@/components/Card';
import { ExpandableSection } from '@/components/ExpandableSection';

export default function MarketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [market, setMarket] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadMarket(); }, [id]);

  async function loadMarket() {
    try {
      const [mkt, prods] = await Promise.all([getMarketById(id!), getMarketProducts(id!, 200)]);
      setMarket(mkt);
      const productMap = new Map<string, any>();
      for (const p of (prods || [])) {
        const pid = p.product_id;
        if (!productMap.has(pid) || p.price_date > productMap.get(pid).price_date) productMap.set(pid, p);
      }
      setProducts(Array.from(productMap.values()));
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

  if (loading) return <div className="loading-container"><div className="spinner" /></div>;
  if (!market) return <div className="loading-container">Mercado no encontrado</div>;

  const cityName = market.dim_city?.canonical_name || '';
  const deptName = market.dim_city?.dim_department?.canonical_name || '';

  return (
    <div style={{ paddingBottom: 40 }}>
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
          <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>Productos</div>
        </div>
        <div style={{ flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, textAlign: 'center' }}>
          <div style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.primary }}>{categoryGroups.length}</div>
          <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>Categor&iacute;as</div>
        </div>
      </div>

      <Card style={{ margin: `${spacing.md}px ${spacing.lg}px 0` }}>
        <div style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.xs }}>Productos recientes</div>
        {sharedDate && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary, marginBottom: spacing.md }}>Precios al {formatDateShort(sharedDate)}</div>}
        {products.length === 0 ? <p style={{ textAlign: 'center', padding: `${spacing.xl}px 0`, color: colors.text.tertiary, fontSize: fontSize.sm }}>Sin datos recientes</p> :
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
                            <div style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.dim_product?.canonical_name || 'Producto'}</div>
                            {ctx && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{ctx}</div>}
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.primary, fontFamily: 'monospace' }}>{formatCOP(p.min_price)}{p.max_price !== p.min_price ? ` - ${formatCOP(p.max_price)}` : ''}</div>
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
    </div>
  );
}
