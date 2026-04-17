'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { IoNutrition, IoLeaf, IoEarth, IoRestaurant, IoFish, IoGrid, IoCube, IoWater, IoInformationCircle, IoInformationCircleOutline, IoCloseCircle, IoHelpCircleOutline, IoClose, IoHome, IoPricetag, IoStorefront, IoFlask, IoMap, IoGlobe, IoTrendingUp, IoTrendingDown, IoCube as IoBox, IoChatbubbleOutline, IoPersonCircleOutline } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOP, formatCOPCompact, formatDateShort, formatPriceContext, formatKg, pctChange, getCategoryImageUrl } from '@agroamigo/shared';
import { getCategories, getTrendingProducts, getWatchlistPrices } from '@agroamigo/shared/api/products';
import { getWatchlistInsumoPrices } from '@agroamigo/shared/api/insumos';
import { getTopSuppliedProducts } from '@agroamigo/shared/api/supply';
import { getLatestComments } from '@agroamigo/shared/api/comments';
import { Card } from '@/components/Card';
import { SectionHeader } from '@/components/SectionHeader';
import { Sparkline } from '@/components/Sparkline';
import { PriceChangeIndicator } from '@/components/PriceChangeIndicator';
import { useSettings } from '@/context/SettingsContext';
import { useWatchlist } from '@/context/WatchlistContext';
import { useLanguage } from '@/context/LanguageContext';

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  'Frutas': <IoNutrition size={22} color={colors.text.inverse} />,
  'Verduras y hortalizas': <IoLeaf size={22} color={colors.text.inverse} />,
  'Tub\u00e9rculos, ra\u00edces y pl\u00e1tanos': <IoEarth size={22} color={colors.text.inverse} />,
  'Carnes': <IoRestaurant size={22} color={colors.text.inverse} />,
  'Pescados': <IoFish size={22} color={colors.text.inverse} />,
  'Granos y cereales': <IoGrid size={22} color={colors.text.inverse} />,
  'Procesados': <IoCube size={22} color={colors.text.inverse} />,
  'L\u00e1cteos y huevos': <IoWater size={22} color={colors.text.inverse} />,
};

export default function HomePage() {
  const router = useRouter();
  const { settings } = useSettings();
  const { items: watchlistItems, remove: removeFromWatchlist } = useWatchlist();
  const { t } = useLanguage();
  const [categories, setCategories] = useState<any[]>([]);
  const [trending, setTrending] = useState<any[]>([]);
  const [topSupplied, setTopSupplied] = useState<any[]>([]);
  const [watchlistPrices, setWatchlistPrices] = useState<Map<string, any>>(new Map());
  const [insumoWatchlistPrices, setInsumoWatchlistPrices] = useState<Map<string, any>>(new Map());
  const [loading, setLoading] = useState(true);
  const [latestComments, setLatestComments] = useState<any[]>([]);
  const [showMarketInfo, setShowMarketInfo] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => { loadData(); }, []);
  useEffect(() => { loadWatchlistPrices(); }, [watchlistItems]);

  async function loadWatchlistPrices() {
    const productIds = watchlistItems.filter(i => i.type === 'product').map(i => i.id);
    const insumoIds = watchlistItems.filter(i => i.type === 'insumo').map(i => i.id);

    if (productIds.length > 0) {
      try {
        const data = await getWatchlistPrices(productIds);
        const map = new Map<string, any>();
        for (const obs of (data || [])) {
          if (!map.has(obs.product_id)) map.set(obs.product_id, obs);
        }
        setWatchlistPrices(map);
      } catch (err) { console.error('Error loading watchlist prices:', err); }
    } else {
      setWatchlistPrices(new Map());
    }

    if (insumoIds.length > 0) {
      try {
        const data = await getWatchlistInsumoPrices(insumoIds);
        const map = new Map<string, any>();
        for (const obs of (data || []) as any[]) {
          if (!map.has(obs.insumo_id)) map.set(obs.insumo_id, obs);
        }
        setInsumoWatchlistPrices(map);
      } catch (err) { console.error('Error loading insumo watchlist prices:', err); }
    } else {
      setInsumoWatchlistPrices(new Map());
    }
  }

  async function loadData() {
    try {
      const [cats, trend, supplied] = await Promise.all([
        getCategories(),
        getTrendingProducts(200),
        getTopSuppliedProducts(10).catch(() => []),
      ]);
      setCategories(cats || []);
      setTopSupplied(supplied || []);
      getLatestComments(10).then(c => setLatestComments(c || [])).catch(() => {});

      // Group by product+presentation to avoid comparing different units
      const productMap = new Map<string, { name: string; prices: number[]; productId: string }>();
      for (const obs of (trend || []) as any[]) {
        const key = `${obs.product_id}|${obs.presentation_id || ''}`;
        const name = obs.dim_product?.canonical_name || 'Unknown';
        const price = obs.avg_price || obs.max_price || obs.min_price || 0;
        if (!productMap.has(key)) productMap.set(key, { name, prices: [], productId: obs.product_id });
        productMap.get(key)!.prices.push(price);
      }
      const trendingList = Array.from(productMap.values())
        .filter(p => p.prices.length >= 2)
        .map(p => ({ ...p, change: pctChange(p.prices[p.prices.length - 1], p.prices[0]), latestPrice: p.prices[0] }))
        .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
        .slice(0, 15);
      setTrending(trendingList);
    } catch (err) { console.error('Error loading home data:', err); }
    finally { setLoading(false); }
  }

  const topMoversUp = useMemo(() => trending.filter(t => t.change > 0).slice(0, 5), [trending]);
  const topMoversDown = useMemo(() => trending.filter(t => t.change < 0).sort((a, b) => a.change - b.change).slice(0, 5), [trending]);

  if (loading) {
    return <div className="loading-container"><div className="spinner" /><span>{t.home_loading}</span></div>;
  }

  return (
    <div style={{ paddingBottom: 20 }}>
      {/* Animated Price Ticker */}
      <div style={{ backgroundColor: colors.dark, overflow: 'hidden' }}>
        <div className="ticker-track" style={{ padding: `${spacing.sm}px 0`, gap: spacing.lg }}>
          {[...trending.slice(0, 8), ...trending.slice(0, 8)].map((item, i) => (
            <button key={`${item.productId}-${i}`} onClick={() => router.push(`/product/${item.productId}`)}
              style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, background: 'none', border: 'none', cursor: 'pointer', whiteSpace: 'nowrap', paddingRight: spacing.lg }}>
              <span style={{ color: colors.text.inverse, fontSize: fontSize.sm, fontWeight: 600, maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.name}</span>
              <span style={{ color: colors.text.inverse, fontSize: fontSize.sm, fontFamily: 'monospace' }}>{formatCOPCompact(item.latestPrice)}</span>
              <PriceChangeIndicator value={item.change} size="sm" />
            </button>
          ))}
        </div>
      </div>

      {/* Market Banner */}
      <button onClick={() => setShowMarketInfo(true)} style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: 'calc(100% - 32px)',
        margin: `${spacing.md}px ${spacing.lg}px ${spacing.sm}px`, padding: `${spacing.sm}px ${spacing.md}px`,
        backgroundColor: colors.surface, borderRadius: borderRadius.md, border: `1px solid ${colors.borderLight}`, cursor: 'pointer',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, flex: 1, minWidth: 0 }}>
          {settings.defaultMarket.level === 'nacional' ? <IoGlobe size={16} color={colors.accent.blue} /> : <IoStorefront size={16} color={colors.primary} />}
          <span style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{settings.defaultMarket.name}</span>
        </div>
        <IoInformationCircleOutline size={18} color={colors.text.tertiary} />
      </button>

      {/* Market Info Modal */}
      {showMarketInfo && (
        <div className="modal-overlay" onClick={() => setShowMarketInfo(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md }}>
              <IoInformationCircle size={22} color={colors.primary} />
              <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary }}>{t.home_market_info_title}</span>
            </div>
            <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.sm }}>
              {t.home_market_info_text} <strong>{settings.defaultMarket.name}</strong>.
            </p>
            <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.md }}>
              {t.home_market_info_change} <span style={{ color: colors.primary, fontWeight: 600 }}>{t.nav_settings}</span>.
            </p>
            <button onClick={() => setShowMarketInfo(false)} style={{
              width: '100%', backgroundColor: colors.primary, color: colors.text.inverse, padding: `${spacing.md}px`,
              borderRadius: borderRadius.md, border: 'none', fontSize: fontSize.md, fontWeight: 600, cursor: 'pointer',
            }}>{t.home_understood}</button>
          </div>
        </div>
      )}

      {/* 1. Watchlist */}
      {watchlistItems.length > 0 && (
        <>
          <SectionHeader title={t.home_watchlist} />
          {watchlistItems.map(item => {
            const isProduct = item.type === 'product';
            const priceData = isProduct ? watchlistPrices.get(item.id) : insumoWatchlistPrices.get(item.id);
            const ctx = isProduct
              ? formatPriceContext(priceData?.dim_presentation?.canonical_name, priceData?.dim_units?.canonical_name)
              : priceData?.presentation || '';
            return (
              <Card key={item.id} style={{ margin: `0 ${spacing.lg}px ${spacing.sm}px` }}>
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <div onClick={() => router.push(isProduct ? `/product/${item.id}` : `/insumo/${item.id}`)}
                    style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0, cursor: 'pointer', gap: spacing.md }}>
                    <div style={{ width: 32, height: 32, borderRadius: borderRadius.md, backgroundColor: (isProduct ? colors.primary : colors.secondary) + '15', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      {isProduct ? <IoPricetag size={16} color={colors.primary} /> : <IoFlask size={16} color={colors.secondary} />}
                    </div>
                    <div style={{ flex: 1, gap: 2, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                      <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
                      {priceData ? (
                        <>
                          <span style={{ fontSize: fontSize.sm, fontWeight: 600, color: isProduct ? colors.primary : colors.secondary, fontFamily: 'monospace' }}>
                            {formatCOP(priceData.avg_price || priceData.min_price)}
                            {priceData.max_price && priceData.max_price !== priceData.min_price ? ` - ${formatCOP(priceData.max_price)}` : ''}
                          </span>
                          <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>
                            {[formatDateShort(priceData.price_date), isProduct ? priceData?.dim_market?.canonical_name : priceData?.dim_department?.canonical_name, ctx].filter(Boolean).join(' \u00b7 ')}
                          </span>
                        </>
                      ) : <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.home_no_recent_data}</span>}
                    </div>
                  </div>
                  <button onClick={() => removeFromWatchlist(item.id)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: spacing.xs, marginLeft: spacing.sm, flexShrink: 0 }}>
                    <IoCloseCircle size={20} color={colors.text.tertiary} />
                  </button>
                </div>
              </Card>
            );
          })}
        </>
      )}

      {/* 2. Categories */}
      <SectionHeader title={t.home_categories} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.sm, padding: `0 ${spacing.md}px` }}>
        {categories.map(cat => (
          <button key={cat.id} onClick={() => router.push(`/products?categoryId=${cat.id}`)}
            style={{ position: 'relative', height: 100, borderRadius: borderRadius.lg, overflow: 'hidden', border: 'none', cursor: 'pointer', padding: 0 }}>
            <img src={getCategoryImageUrl(cat.canonical_name)} alt={cat.canonical_name}
              style={{ width: '100%', height: '100%', objectFit: 'cover', position: 'absolute' }} />
            <div style={{ position: 'relative', width: '100%', height: '100%', backgroundColor: 'rgba(26,46,26,0.6)',
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: spacing.sm, gap: 4 }}>
              {CATEGORY_ICONS[cat.canonical_name] || <IoLeaf size={22} color={colors.text.inverse} />}
              <span style={{ color: colors.text.inverse, fontSize: fontSize.sm, fontWeight: 700, textAlign: 'center' }}>{cat.canonical_name}</span>
            </div>
          </button>
        ))}
      </div>

      {/* 3a. Top increases */}
      {topMoversUp.length > 0 && (
        <>
          <SectionHeader title={t.home_top_increases} />
          {topMoversUp.map(item => (
            <Card key={item.productId} style={{ margin: `0 ${spacing.lg}px ${spacing.sm}px` }}
              onPress={() => router.push(`/product/${item.productId}`)}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                  <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
                  <span style={{ fontSize: fontSize.sm, color: colors.text.secondary, fontFamily: 'monospace' }}>{formatCOP(item.latestPrice)}</span>
                  <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.home_last_7_days}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                  <Sparkline data={[...item.prices].reverse()} width={50} height={20} />
                  <PriceChangeIndicator value={item.change} size="sm" />
                </div>
              </div>
            </Card>
          ))}
        </>
      )}

      {/* 3b. Top decreases */}
      {topMoversDown.length > 0 && (
        <>
          <SectionHeader title={t.home_top_decreases} />
          {topMoversDown.map(item => (
            <Card key={item.productId} style={{ margin: `0 ${spacing.lg}px ${spacing.sm}px` }}
              onPress={() => router.push(`/product/${item.productId}`)}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                  <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
                  <span style={{ fontSize: fontSize.sm, color: colors.text.secondary, fontFamily: 'monospace' }}>{formatCOP(item.latestPrice)}</span>
                  <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.home_last_7_days}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                  <Sparkline data={[...item.prices].reverse()} width={50} height={20} />
                  <PriceChangeIndicator value={item.change} size="sm" />
                </div>
              </div>
            </Card>
          ))}
        </>
      )}

      {/* 3c. Top supply */}
      {topSupplied.length > 0 && (
        <>
          <SectionHeader title={t.home_top_supply} />
          {topSupplied.map((item: any) => (
            <Card key={item.product_id} style={{ margin: `0 ${spacing.lg}px ${spacing.sm}px` }}
              onPress={() => router.push(`/product/${item.product_id}`)}>
              <div style={{ display: 'flex', alignItems: 'center', gap: spacing.md }}>
                <div style={{ width: 32, height: 32, borderRadius: borderRadius.md, backgroundColor: colors.accent.blue + '15', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <IoBox size={16} color={colors.accent.blue} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
                  <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.home_last_week}</span>
                </div>
                <span style={{ fontSize: fontSize.sm, fontWeight: 700, color: colors.accent.blue, fontFamily: 'monospace', flexShrink: 0 }}>{formatKg(item.total_kg)}</span>
              </div>
            </Card>
          ))}
        </>
      )}

      {/* Latest Comments */}
      {settings.commentsEnabled && latestComments.length > 0 && (
        <>
          <SectionHeader title={t.comments_latest} />
          {latestComments.map((c: any) => {
            const entityLabel = c.entity_type === 'product' ? t.comments_on_product
              : c.entity_type === 'market' ? t.comments_on_market : t.comments_on_insumo;
            const href = `/${c.entity_type === 'insumo' ? 'insumo' : c.entity_type}/${c.entity_id}`;
            const ts = new Date(c.created_at);
            const dateStr = formatDateShort(c.created_at.split('T')[0]);
            const timeStr = `${ts.getHours().toString().padStart(2, '0')}:${ts.getMinutes().toString().padStart(2, '0')}`;
            return (
              <Card key={c.id} style={{ margin: `0 ${spacing.lg}px ${spacing.sm}px` }} onPress={() => router.push(href)}>
                <div style={{ display: 'flex', gap: spacing.sm }}>
                  <IoPersonCircleOutline size={24} color={colors.text.tertiary} style={{ flexShrink: 0, marginTop: 2 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: spacing.xs, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.text.primary }}>{(c.profiles as any)?.username || '?'}</span>
                      <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{entityLabel}</span>
                      <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{dateStr} {timeStr}</span>
                    </div>
                    <div style={{ fontSize: fontSize.sm, color: colors.text.secondary, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {c.content}
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </>
      )}

      {/* Help */}
      <button onClick={() => setShowHelp(true)} style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, width: 'calc(100% - 32px)',
        margin: `${spacing.md}px ${spacing.lg}px 0`, padding: `${spacing.lg}px 0`, background: 'none', border: 'none',
        borderTop: `1px solid ${colors.border}`, cursor: 'pointer',
      }}>
        <IoHelpCircleOutline size={20} color={colors.text.secondary} />
        <span style={{ fontSize: fontSize.sm, color: colors.text.secondary }}>{t.home_help_methodology}</span>
      </button>

      {/* Help Modal */}
      {showHelp && (
        <div className="modal-overlay" onClick={() => setShowHelp(false)}>
          <div className="modal-card" style={{ maxWidth: 440, maxHeight: '85vh' }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.md, borderBottom: `1px solid ${colors.border}`, paddingBottom: spacing.md }}>
              <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary }}>{t.home_help}</span>
              <button onClick={() => setShowHelp(false)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                <IoClose size={24} color={colors.text.primary} />
              </button>
            </div>
            <div style={{ overflowY: 'auto', maxHeight: 'calc(85vh - 100px)', paddingBottom: 20 }}>
              <h3 style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.primary, margin: `${spacing.md}px 0` }}>{t.home_app_guide}</h3>
              {[
                { icon: <IoHome size={20} color={colors.primary} />, title: t.nav_home_tab, text: t.home_help_home_text },
                { icon: <IoPricetag size={20} color={colors.primary} />, title: t.nav_products, text: t.home_help_products_text },
                { icon: <IoStorefront size={20} color={colors.primary} />, title: t.nav_markets, text: t.home_help_markets_text },
                { icon: <IoFlask size={20} color={colors.primary} />, title: t.nav_inputs, text: t.home_help_inputs_text },
                { icon: <IoMap size={20} color={colors.primary} />, title: t.nav_map, text: t.home_help_map_text },
              ].map(h => (
                <div key={h.title} style={{ display: 'flex', gap: spacing.md, marginBottom: spacing.lg, alignItems: 'flex-start' }}>
                  {h.icon}
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.text.primary, marginBottom: 4 }}>{h.title}</div>
                    <div style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px' }}>{h.text}</div>
                  </div>
                </div>
              ))}
              <hr style={{ border: 'none', borderTop: `1px solid ${colors.border}`, margin: `${spacing.lg}px 0` }} />
              <h3 style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.primary, margin: `${spacing.md}px 0` }}>{t.home_sources_methodology}</h3>
              <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.md }}>
                {t.home_sources_text}
              </p>
              <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', fontStyle: 'italic', marginTop: spacing.lg, opacity: 0.7 }}>
                {t.home_disclaimer}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
