'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { IoNutrition, IoLeaf, IoEarth, IoRestaurant, IoFish, IoGrid, IoCube, IoWater, IoInformationCircle, IoInformationCircleOutline, IoCloseCircle, IoHelpCircleOutline, IoClose, IoHome, IoPricetag, IoStorefront, IoFlask, IoMap, IoGlobe } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOP, formatCOPCompact, formatDateShort, formatPriceContext, pctChange, getCategoryImageUrl } from '@agroamigo/shared';
import { getCategories, getTrendingProducts, getWatchlistPrices } from '@agroamigo/shared/api/products';
import { Card } from '@/components/Card';
import { SectionHeader } from '@/components/SectionHeader';
import { Sparkline } from '@/components/Sparkline';
import { PriceChangeIndicator } from '@/components/PriceChangeIndicator';
import { useSettings } from '@/context/SettingsContext';
import { useWatchlist } from '@/context/WatchlistContext';

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
  const [categories, setCategories] = useState<any[]>([]);
  const [trending, setTrending] = useState<any[]>([]);
  const [watchlistPrices, setWatchlistPrices] = useState<Map<string, any>>(new Map());
  const [loading, setLoading] = useState(true);
  const [showMarketInfo, setShowMarketInfo] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => { loadData(); }, []);
  useEffect(() => { loadWatchlistPrices(); }, [watchlistItems]);

  async function loadWatchlistPrices() {
    const productIds = watchlistItems.filter(i => i.type === 'product').map(i => i.id);
    if (productIds.length === 0) { setWatchlistPrices(new Map()); return; }
    try {
      const data = await getWatchlistPrices(productIds);
      const map = new Map<string, any>();
      for (const obs of (data || [])) {
        if (!map.has(obs.product_id)) map.set(obs.product_id, obs);
      }
      setWatchlistPrices(map);
    } catch (err) { console.error('Error loading watchlist prices:', err); }
  }

  async function loadData() {
    try {
      const [cats, trend] = await Promise.all([getCategories(), getTrendingProducts(200)]);
      setCategories(cats || []);
      const productMap = new Map<string, { name: string; prices: number[]; productId: string }>();
      for (const obs of (trend || []) as any[]) {
        const pid = obs.product_id;
        const name = obs.dim_product?.canonical_name || 'Unknown';
        const price = obs.avg_price || obs.max_price || obs.min_price || 0;
        if (!productMap.has(pid)) productMap.set(pid, { name, prices: [], productId: pid });
        productMap.get(pid)!.prices.push(price);
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

  if (loading) {
    return <div className="loading-container"><div className="spinner" /><span>Cargando datos...</span></div>;
  }

  return (
    <div style={{ paddingBottom: 20 }}>
      {/* Price Ticker */}
      <div style={{ backgroundColor: colors.dark, overflow: 'hidden' }}>
        <div className="chip-scroll" style={{ padding: `${spacing.sm}px ${spacing.md}px`, gap: spacing.lg }}>
          {trending.slice(0, 8).map((item) => (
            <button key={item.productId} onClick={() => router.push(`/product/${item.productId}`)}
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
              <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary }}>Mercado predeterminado</span>
            </div>
            <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.sm }}>
              Los precios que ves en la pantalla de inicio provienen de tu mercado predeterminado: <strong>{settings.defaultMarket.name}</strong>.
            </p>
            <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.md }}>
              Puedes cambiar tu mercado en <span style={{ color: colors.primary, fontWeight: 600 }}>Configuraci&oacute;n</span>.
            </p>
            <button onClick={() => setShowMarketInfo(false)} style={{
              width: '100%', backgroundColor: colors.primary, color: colors.text.inverse, padding: `${spacing.md}px`,
              borderRadius: borderRadius.md, border: 'none', fontSize: fontSize.md, fontWeight: 600, cursor: 'pointer',
            }}>Entendido</button>
          </div>
        </div>
      )}

      {/* Watchlist */}
      {watchlistItems.length > 0 && (
        <>
          <SectionHeader title="Seguimiento" />
          {watchlistItems.map(item => {
            const priceData = watchlistPrices.get(item.id);
            const ctx = formatPriceContext(priceData?.dim_presentation?.canonical_name, priceData?.dim_units?.canonical_name);
            return (
              <Card key={item.id} style={{ margin: `0 ${spacing.lg}px ${spacing.sm}px` }}
                onPress={() => router.push(item.type === 'product' ? `/product/${item.id}` : `/insumo/${item.id}`)}>
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <div style={{ flex: 1, gap: 2, display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
                    {priceData ? (
                      <>
                        <span style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.primary, fontFamily: 'monospace' }}>
                          {formatCOP(priceData.avg_price || priceData.min_price)}
                          {priceData.max_price && priceData.max_price !== priceData.min_price ? ` - ${formatCOP(priceData.max_price)}` : ''}
                        </span>
                        <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>
                          {[formatDateShort(priceData.price_date), priceData?.dim_market?.canonical_name, ctx].filter(Boolean).join(' \u00b7 ')}
                        </span>
                      </>
                    ) : <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>Sin datos recientes</span>}
                  </div>
                  <button onClick={e => { e.stopPropagation(); removeFromWatchlist(item.id); }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: spacing.xs, marginLeft: spacing.sm }}>
                    <IoCloseCircle size={20} color={colors.text.tertiary} />
                  </button>
                </div>
              </Card>
            );
          })}
        </>
      )}

      {/* Categories */}
      <SectionHeader title="Categor\u00edas" />
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

      {/* Trending */}
      <SectionHeader title="Tendencias de la semana" />
      {trending.map(item => (
        <Card key={item.productId} style={{ margin: `0 ${spacing.lg}px ${spacing.sm}px` }}
          onPress={() => router.push(`/product/${item.productId}`)}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
              <span style={{ fontSize: fontSize.sm, color: colors.text.secondary, fontFamily: 'monospace' }}>{formatCOP(item.latestPrice)}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
              <Sparkline data={[...item.prices].reverse()} width={50} height={20} />
              <PriceChangeIndicator value={item.change} size="sm" />
            </div>
          </div>
        </Card>
      ))}

      {/* Help */}
      <button onClick={() => setShowHelp(true)} style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, width: 'calc(100% - 32px)',
        margin: `${spacing.md}px ${spacing.lg}px 0`, padding: `${spacing.lg}px 0`, background: 'none', border: 'none',
        borderTop: `1px solid ${colors.border}`, cursor: 'pointer',
      }}>
        <IoHelpCircleOutline size={20} color={colors.text.secondary} />
        <span style={{ fontSize: fontSize.sm, color: colors.text.secondary }}>Ayuda y metodolog&iacute;a</span>
      </button>

      {/* Help Modal */}
      {showHelp && (
        <div className="modal-overlay" onClick={() => setShowHelp(false)}>
          <div className="modal-card" style={{ maxWidth: 440, maxHeight: '85vh' }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.md, borderBottom: `1px solid ${colors.border}`, paddingBottom: spacing.md }}>
              <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary }}>Ayuda</span>
              <button onClick={() => setShowHelp(false)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                <IoClose size={24} color={colors.text.primary} />
              </button>
            </div>
            <div style={{ overflowY: 'auto', maxHeight: 'calc(85vh - 100px)', paddingBottom: 20 }}>
              <h3 style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.primary, margin: `${spacing.md}px 0` }}>Gu&iacute;a de la aplicaci&oacute;n</h3>
              {[
                { icon: <IoHome size={20} color={colors.primary} />, title: 'Inicio', text: 'Tu panel principal con tendencias, favoritos y categor\u00edas.' },
                { icon: <IoPricetag size={20} color={colors.primary} />, title: 'Productos', text: 'M\u00e1s de 700 productos con precios hist\u00f3ricos y comparaci\u00f3n entre mercados.' },
                { icon: <IoStorefront size={20} color={colors.primary} />, title: 'Mercados', text: '43 mercados mayoristas y 500+ mercados municipales.' },
                { icon: <IoFlask size={20} color={colors.primary} />, title: 'Insumos', text: 'Precios de 2,000+ insumos agropecuarios por departamento.' },
                { icon: <IoMap size={20} color={colors.primary} />, title: 'Mapa', text: 'Visualiza precios y flujos de abastecimiento sobre el mapa de Colombia.' },
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
              <h3 style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.primary, margin: `${spacing.md}px 0` }}>Fuentes y metodolog&iacute;a</h3>
              <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.md }}>
                Todos los datos provienen del SIPSA (Sistema de Informaci&oacute;n de Precios y Abastecimiento del Sector Agropecuario), operado por el DANE de Colombia.
              </p>
              <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', fontStyle: 'italic', marginTop: spacing.lg, opacity: 0.7 }}>
                Esta aplicaci&oacute;n no es un producto oficial del DANE.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
