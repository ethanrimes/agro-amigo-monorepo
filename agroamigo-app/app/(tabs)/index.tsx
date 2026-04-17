import React, { useEffect, useState, useMemo } from 'react';
import { View, Text, ScrollView, StyleSheet, Image, Pressable, FlatList, ActivityIndicator, Modal } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { SectionHeader } from '../../src/components/SectionHeader';
import { Sparkline } from '../../src/components/Sparkline';
import { PriceChangeIndicator } from '../../src/components/PriceChangeIndicator';
import { getCategories, getTrendingProducts, getWatchlistPrices } from '../../src/api/products';
import { getWatchlistInsumoPrices } from '../../src/api/insumos';
import { getTopSuppliedProducts } from '../../src/api/supply';
import { getMarketTopProducts } from '../../src/api/markets';
import { getLatestComments } from '../../src/api/comments';
import { getCategoryImageUrl } from '../../src/lib/images';
import { formatCOP, formatCOPCompact, formatDateShort, formatPriceContext, formatKg, pctChange } from '../../src/lib/format';
import { useSettings } from '../../src/context/SettingsContext';
import { useWatchlist } from '../../src/context/WatchlistContext';
import { useTranslation } from '../../src/lib/useTranslation';

const CATEGORY_ICONS: Record<string, string> = {
  'Frutas': 'nutrition',
  'Verduras y hortalizas': 'leaf',
  'Tubérculos, raíces y plátanos': 'earth',
  'Carnes': 'restaurant',
  'Pescados': 'fish',
  'Granos y cereales': 'grid',
  'Procesados': 'cube',
  'Lácteos y huevos': 'water',
};

export default function HomeScreen() {
  const router = useRouter();
  const { settings } = useSettings();
  const t = useTranslation();
  const { items: watchlistItems, remove: removeFromWatchlist } = useWatchlist();
  const [categories, setCategories] = useState<any[]>([]);
  const [trending, setTrending] = useState<any[]>([]);
  const [topSupplied, setTopSupplied] = useState<any[]>([]);
  const [marketTopSupplied, setMarketTopSupplied] = useState<{ id: string; name: string; kg: number; date: string | null }[]>([]);
  const [trendingScope, setTrendingScope] = useState<'market' | 'national'>('national');
  const [watchlistPrices, setWatchlistPrices] = useState<Map<string, any>>(new Map());
  const [insumoWatchlistPrices, setInsumoWatchlistPrices] = useState<Map<string, any>>(new Map());
  const [latestComments, setLatestComments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showMethodology, setShowMethodology] = useState(false);
  const [showMarketInfo, setShowMarketInfo] = useState(false);

  useEffect(() => {
    loadData();
  }, [settings.defaultMarket.id, settings.defaultMarket.level]);

  // Reload watchlist prices when watchlist items OR default market change
  useEffect(() => {
    loadWatchlistPrices();
  }, [watchlistItems, settings.defaultMarket.id, settings.defaultMarket.level]);

  async function loadWatchlistPrices() {
    const productIds = watchlistItems.filter(i => i.type === 'product').map(i => i.id);
    const insumoIds = watchlistItems.filter(i => i.type === 'insumo').map(i => i.id);

    const preferredMarketId = settings.defaultMarket.level === 'mercado' ? settings.defaultMarket.id : undefined;

    // Clear the map first so switching markets shows the transition.
    setWatchlistPrices(new Map());

    if (productIds.length > 0) {
      try {
        // getWatchlistPrices applies the default-market filter and falls
        // back to national data for any item missing at that market.
        const data = await getWatchlistPrices(productIds, preferredMarketId);
        const map = new Map<string, any>();
        for (const obs of (data || [])) { if (!map.has(obs.product_id)) map.set(obs.product_id, obs); }
        setWatchlistPrices(map);
      } catch (err) { console.error(err); }
    }

    if (insumoIds.length > 0) {
      try {
        const data = await getWatchlistInsumoPrices(insumoIds);
        const map = new Map<string, any>();
        for (const obs of (data || []) as any[]) { if (!map.has(obs.insumo_id)) map.set(obs.insumo_id, obs); }
        setInsumoWatchlistPrices(map);
      } catch (err) { console.error(err); }
    } else { setInsumoWatchlistPrices(new Map()); }
  }

  async function loadData() {
    // Clear stale lists up front so that switching mercado → nacional (or
    // between two markets) visibly refreshes — without this, the old data
    // keeps showing until every re-fetch resolves, masking the update.
    setTrending([]);
    setMarketTopSupplied([]);

    const preferredMarketId = settings.defaultMarket.level === 'mercado' ? settings.defaultMarket.id : undefined;

    // Each fetch is independent so a single slow/failed endpoint doesn't
    // block the others from refreshing.
    getCategories().then(c => setCategories(c || [])).catch(err => console.error('categories', err));
    getTopSuppliedProducts(10).then(s => setTopSupplied(s || [])).catch(() => {});
    getLatestComments(10).then(c => setLatestComments(c || [])).catch(() => {});

    if (settings.defaultMarket.level === 'mercado' && settings.defaultMarket.id) {
      getMarketTopProducts(settings.defaultMarket.id, 7, null, 8)
        .then(rows => setMarketTopSupplied(rows.map((r: any) => ({
          id: r.product_id,
          name: r.product_name || t.market_product_fallback,
          kg: r.total_kg,
          date: r.newest_obs,
        }))))
        .catch(() => setMarketTopSupplied([]));
    }

    try {
      // Try the default market first. If the mercado scope has too few
      // observations to compute trends (<10 rows), fall back to national.
      // National scope pulls the PostgREST max (1000 rows) so we have
      // enough cross-market samples per (product, presentation).
      const MARKET_LIMIT = 200;
      const NATIONAL_LIMIT = 1000;
      let trend = await getTrendingProducts(preferredMarketId ? MARKET_LIMIT : NATIONAL_LIMIT, preferredMarketId);
      let trendScope: 'market' | 'national' = preferredMarketId ? 'market' : 'national';
      if (preferredMarketId && (!trend || trend.length < 10)) {
        trend = await getTrendingProducts(NATIONAL_LIMIT);
        trendScope = 'national';
      }
      setTrendingScope(trendScope);

      // Aggregation key: include market_id only when we're scoped to a
      // single market (mercado level). For national scope, keying by
      // (product, presentation) lets observations from different markets
      // feed the same bucket so prices.length >= 2 actually matches.
      const productMap = new Map<string, {
        name: string; prices: number[]; productId: string;
        presentation: string; market: string;
      }>();
      const scopedByMarket = trendScope === 'market';
      for (const obs of (trend || [])) {
        const o = obs as any;
        const key = scopedByMarket
          ? `${o.product_id}|${o.presentation_id || ''}|${o.market_id || ''}`
          : `${o.product_id}|${o.presentation_id || ''}`;
        const name = o.dim_product?.canonical_name || 'Unknown';
        const presentation = o.dim_presentation?.canonical_name || '';
        // In national scope we aggregate across markets, so stash "(varios)"
        // rather than pinning to one market's name.
        const market = scopedByMarket
          ? (o.dim_market?.canonical_name || '')
          : t.product_national_avg;
        const price = o.avg_price || o.max_price || o.min_price || 0;
        if (!productMap.has(key)) {
          productMap.set(key, { name, prices: [], productId: o.product_id, presentation, market });
        }
        productMap.get(key)!.prices.push(price);
      }

      const all = Array.from(productMap.values())
        .filter(p => p.prices.length >= 2)
        .map(p => {
          const oldest = p.prices[p.prices.length - 1];
          const newest = p.prices[0];
          return { ...p, change: pctChange(oldest, newest), latestPrice: newest };
        })
        .sort((a, b) => Math.abs(b.change) - Math.abs(a.change));

      // Keep only the single biggest-move entry per product — otherwise
      // the same product fills the list multiple times with different
      // markets/presentations.
      const seen = new Set<string>();
      const trendingList = [];
      for (const p of all) {
        if (seen.has(p.productId)) continue;
        seen.add(p.productId);
        trendingList.push(p);
        if (trendingList.length >= 15) break;
      }

      setTrending(trendingList);
    } catch (err) {
      console.error('Error loading home data:', err);
    } finally {
      setLoading(false);
    }
  }

  const topMoversUp = useMemo(() => trending.filter(t => t.change > 0).slice(0, 5), [trending]);
  const topMoversDown = useMemo(() => trending.filter(t => t.change < 0).sort((a, b) => a.change - b.change).slice(0, 5), [trending]);

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingText}>{t.home_loading}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Price Ticker */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.ticker}
        contentContainerStyle={styles.tickerContent}
      >
        {trending.slice(0, 8).map((item, i) => (
          <Pressable
            key={item.productId}
            style={styles.tickerItem}
            onPress={() => router.push(`/product/${item.productId}`)}
          >
            <Text style={styles.tickerName} numberOfLines={1}>{item.name}</Text>
            <Text style={styles.tickerPrice}>{formatCOPCompact(item.latestPrice)}</Text>
            <PriceChangeIndicator value={item.change} size="sm" />
          </Pressable>
        ))}
      </ScrollView>

      {/* Default Market Banner */}
      <Pressable
        style={styles.marketBanner}
        onPress={() => setShowMarketInfo(true)}
      >
        <View style={styles.marketBannerLeft}>
          <Ionicons
            name={settings.defaultMarket.level === 'nacional' ? 'globe' : 'storefront'}
            size={16}
            color={settings.defaultMarket.level === 'nacional' ? colors.accent.blue : colors.primary}
          />
          <Text style={styles.marketBannerText} numberOfLines={1}>
            {settings.defaultMarket.name}
          </Text>
        </View>
        <Ionicons name="information-circle-outline" size={18} color={colors.text.tertiary} />
      </Pressable>

      {/* Market Info Modal */}
      <Modal
        visible={showMarketInfo}
        animationType="fade"
        transparent
        onRequestClose={() => setShowMarketInfo(false)}
      >
        <Pressable style={styles.infoOverlay} onPress={() => setShowMarketInfo(false)}>
          <View style={styles.infoCard}>
            <View style={styles.infoHeader}>
              <Ionicons name="information-circle" size={22} color={colors.primary} />
              <Text style={styles.infoTitle}>{t.home_market_info_title}</Text>
            </View>
            <Text style={styles.infoBody}>
              {t.home_market_info_text} {<Text style={{ fontWeight: '700' }}>{settings.defaultMarket.name}</Text>}.
            </Text>
            <Text style={styles.infoBody}>
              {settings.defaultMarket.level === 'nacional'
                ? 'Actualmente estás viendo promedios nacionales. Los precios reflejan el comportamiento general del mercado colombiano.'
                : settings.defaultMarket.level === 'departamento'
                ? 'Estás viendo precios promedio del departamento seleccionado.'
                : settings.defaultMarket.level === 'ciudad'
                ? 'Estás viendo precios promedio de la ciudad seleccionada.'
                : 'Estás viendo precios de un mercado específico. Los datos corresponden directamente a las cotizaciones reportadas.'}
            </Text>
            <Text style={styles.infoBody}>
              {t.home_market_info_change}{' '}
              <Text style={{ color: colors.primary, fontWeight: '600' }}>{t.nav_settings}</Text>.
            </Text>
            <View style={styles.infoLegend}>
              <View style={styles.infoLegendRow}>
                <View style={[styles.infoLegendDot, { backgroundColor: colors.primary }]} />
                <Text style={styles.infoLegendText}>Precio del mercado seleccionado</Text>
              </View>
              <View style={styles.infoLegendRow}>
                <View style={[styles.infoLegendDot, { backgroundColor: colors.accent.blue }]} />
                <Text style={styles.infoLegendText}>Promedio nacional (cuando no hay datos locales)</Text>
              </View>
            </View>
            <Pressable style={styles.infoCloseBtn} onPress={() => setShowMarketInfo(false)}>
              <Text style={styles.infoCloseText}>{t.home_understood}</Text>
            </Pressable>
          </View>
        </Pressable>
      </Modal>

      {/* Watchlist */}
      {watchlistItems.length > 0 && (
        <>
          <SectionHeader title={t.home_watchlist} />
          {watchlistItems.map((item) => {
            const isProduct = item.type === 'product';
            const priceData = isProduct ? watchlistPrices.get(item.id) : insumoWatchlistPrices.get(item.id);
            const ctx = isProduct
              ? formatPriceContext(priceData?.dim_presentation?.canonical_name, priceData?.dim_units?.canonical_name)
              : priceData?.presentation || '';

            return (
              <Card key={item.id} style={styles.watchlistCard}
                onPress={() => router.push(isProduct ? `/product/${item.id}` : `/insumo/${item.id}`)}>
                <View style={styles.watchlistRow}>
                  <View style={{ width: 32, height: 32, borderRadius: borderRadius.md, backgroundColor: (isProduct ? colors.primary : colors.secondary) + '15', alignItems: 'center', justifyContent: 'center', marginRight: spacing.md }}>
                    <Ionicons name={isProduct ? 'pricetag' : 'flask'} size={16} color={isProduct ? colors.primary : colors.secondary} />
                  </View>
                  <View style={styles.watchlistInfo}>
                    <Text style={styles.watchlistName} numberOfLines={1}>{item.name}</Text>
                    {priceData ? (
                      <>
                        <Text style={[styles.watchlistPrice, !isProduct && { color: colors.secondary }]}>
                          {formatCOP(priceData.avg_price || priceData.min_price)}
                          {priceData.max_price && priceData.max_price !== priceData.min_price ? ` - ${formatCOP(priceData.max_price)}` : ''}
                        </Text>
                        <Text style={styles.watchlistMeta} numberOfLines={1}>
                          {[
                            formatDateShort(priceData.price_date),
                            isProduct
                              ? (priceData._from_default ? priceData?.dim_market?.canonical_name : t.product_national_avg)
                              : (priceData?.dim_department as any)?.canonical_name,
                            ctx,
                          ].filter(Boolean).join(' · ')}
                        </Text>
                      </>
                    ) : (
                      <Text style={styles.watchlistMeta}>{t.home_no_recent_data}</Text>
                    )}
                  </View>
                  <Pressable onPress={() => removeFromWatchlist(item.id)} hitSlop={12} style={styles.watchlistRemove}>
                    <Ionicons name="close-circle" size={20} color={colors.text.tertiary} />
                  </Pressable>
                </View>
              </Card>
            );
          })}
        </>
      )}

      {/* Categories */}
      <SectionHeader title={t.home_categories} />
      <View style={styles.categoryGrid}>
        {categories.map((cat) => (
          <Pressable
            key={cat.id}
            style={styles.categoryCard}
            onPress={() => router.push({ pathname: '/products', params: { categoryId: cat.id } } as any)}
          >
            <Image
              source={{ uri: getCategoryImageUrl(cat.canonical_name) }}
              style={styles.categoryImage}
            />
            <View style={styles.categoryOverlay}>
              <Ionicons
                name={(CATEGORY_ICONS[cat.canonical_name] || 'leaf') as any}
                size={22}
                color={colors.text.inverse}
              />
              <Text style={styles.categoryName} numberOfLines={2}>
                {cat.canonical_name}
              </Text>
            </View>
          </Pressable>
        ))}
      </View>

      {/* Top Increases */}
      {topMoversUp.length > 0 && (
        <>
          <SectionHeader title={`${t.home_top_increases}${trendingScope === 'market' ? ` — ${settings.defaultMarket.name}` : ` — ${t.product_national_avg}`}`} />
          {topMoversUp.map((item: any) => (
            <Card key={item.productId} style={styles.trendingCard} onPress={() => router.push(`/product/${item.productId}`)}>
              <View style={styles.trendingRow}>
                <View style={styles.trendingInfo}>
                  <Text style={styles.trendingName} numberOfLines={1}>{item.name}</Text>
                  {(item.presentation || item.market) && (
                    <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }} numberOfLines={1}>
                      {[item.presentation, item.market].filter(Boolean).join(' \u00b7 ')}
                    </Text>
                  )}
                  <Text style={styles.trendingPrice}>{formatCOP(item.latestPrice)}</Text>
                  <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.home_last_7_days}</Text>
                </View>
                <View style={styles.trendingRight}>
                  <Sparkline data={[...item.prices].reverse()} width={50} height={20} />
                  <PriceChangeIndicator value={item.change} size="sm" />
                </View>
              </View>
            </Card>
          ))}
        </>
      )}

      {/* Top Decreases */}
      {topMoversDown.length > 0 && (
        <>
          <SectionHeader title={`${t.home_top_decreases}${trendingScope === 'market' ? ` — ${settings.defaultMarket.name}` : ` — ${t.product_national_avg}`}`} />
          {topMoversDown.map((item: any) => (
            <Card key={item.productId} style={styles.trendingCard} onPress={() => router.push(`/product/${item.productId}`)}>
              <View style={styles.trendingRow}>
                <View style={styles.trendingInfo}>
                  <Text style={styles.trendingName} numberOfLines={1}>{item.name}</Text>
                  {(item.presentation || item.market) && (
                    <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }} numberOfLines={1}>
                      {[item.presentation, item.market].filter(Boolean).join(' \u00b7 ')}
                    </Text>
                  )}
                  <Text style={styles.trendingPrice}>{formatCOP(item.latestPrice)}</Text>
                  <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.home_last_7_days}</Text>
                </View>
                <View style={styles.trendingRight}>
                  <Sparkline data={[...item.prices].reverse()} width={50} height={20} />
                  <PriceChangeIndicator value={item.change} size="sm" />
                </View>
              </View>
            </Card>
          ))}
        </>
      )}

      {/* Top Supply */}
      {marketTopSupplied.length > 0 && (
        <>
          <SectionHeader title={`${t.home_top_supply} — ${settings.defaultMarket.name}`} />
          {marketTopSupplied.map((item) => (
            <Card key={item.id} style={styles.trendingCard} onPress={() => router.push(`/product/${item.id}`)}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
                <View style={{ width: 32, height: 32, borderRadius: borderRadius.md, backgroundColor: colors.accent.blue + '15', alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="cube" size={16} color={colors.accent.blue} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.trendingName}>{item.name}</Text>
                  <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>
                    {[t.home_last_week, item.date ? formatDateShort(item.date) : null].filter(Boolean).join(' \u00b7 ')}
                  </Text>
                </View>
                <Text style={{ fontSize: fontSize.sm, fontWeight: '700', color: colors.accent.blue, fontFamily: 'monospace' }}>{formatKg(item.kg)}</Text>
              </View>
            </Card>
          ))}
        </>
      )}

      {/* National top-supplied — only shown when the user doesn't have a
          specific market selected (otherwise the market-specific section
          above covers it). */}
      {marketTopSupplied.length === 0 && topSupplied.length > 0 && (
        <>
          <SectionHeader title={`${t.home_top_supply} — ${t.product_national_avg}`} />
          {topSupplied.map((item: any) => (
            <Card key={item.product_id} style={styles.trendingCard} onPress={() => router.push(`/product/${item.product_id}`)}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
                <View style={{ width: 32, height: 32, borderRadius: borderRadius.md, backgroundColor: colors.accent.blue + '15', alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="cube" size={16} color={colors.accent.blue} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.trendingName} numberOfLines={1}>{item.name}</Text>
                  <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>
                    {[t.home_last_week, item.newest_obs ? formatDateShort(item.newest_obs) : null].filter(Boolean).join(' \u00b7 ')}
                  </Text>
                </View>
                <Text style={{ fontSize: fontSize.sm, fontWeight: '700', color: colors.accent.blue, fontFamily: 'monospace' }}>{formatKg(item.total_kg)}</Text>
              </View>
            </Card>
          ))}
        </>
      )}

      {/* Latest Comments */}
      {settings.commentsEnabled && latestComments.length > 0 && (
        <>
          <SectionHeader title={t.comments_latest} />
          {latestComments.map((c: any) => {
            const entityLabel = c.entity_name
              ? `${t.comments_on} ${c.entity_name}`
              : c.entity_type === 'product' ? t.comments_on_product
              : c.entity_type === 'market' ? t.comments_on_market
              : t.comments_on_insumo;
            const href = `/${c.entity_type === 'insumo' ? 'insumo' : c.entity_type}/${c.entity_id}`;
            const ts = new Date(c.created_at);
            const dateStr = formatDateShort(c.created_at.split('T')[0]);
            const timeStr = `${ts.getHours().toString().padStart(2, '0')}:${ts.getMinutes().toString().padStart(2, '0')}`;
            return (
              <Card key={c.id} style={styles.trendingCard} onPress={() => router.push(href as any)}>
                <View style={{ flexDirection: 'row', gap: spacing.sm }}>
                  <Ionicons name="person-circle-outline" size={24} color={colors.text.tertiary} />
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.xs, flexWrap: 'wrap' }}>
                      <Text style={{ fontSize: fontSize.sm, fontWeight: '600', color: colors.text.primary }}>{(c.profiles as any)?.username || '?'}</Text>
                      <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{entityLabel}</Text>
                      <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{dateStr} {timeStr}</Text>
                    </View>
                    <Text style={{ fontSize: fontSize.sm, color: colors.text.secondary, marginTop: 2 }} numberOfLines={2}>{c.content}</Text>
                  </View>
                </View>
              </Card>
            );
          })}
        </>
      )}

      {/* Help */}
      <Pressable
        style={styles.helpButton}
        onPress={() => setShowMethodology(true)}
      >
        <Ionicons name="help-circle-outline" size={20} color={colors.text.secondary} />
        <Text style={styles.helpButtonText}>{t.home_help_methodology}</Text>
      </Pressable>

      <Modal
        visible={showMethodology}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowMethodology(false)}
      >
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{t.home_help}</Text>
            <Pressable onPress={() => setShowMethodology(false)} hitSlop={12}>
              <Ionicons name="close" size={24} color={colors.text.primary} />
            </Pressable>
          </View>
          <ScrollView style={styles.modalBody} contentContainerStyle={{ paddingBottom: 40 }}>

            {/* App Guide */}
            <Text style={styles.helpSectionTitle}>{t.home_app_guide}</Text>

            <View style={styles.helpItem}>
              <Ionicons name="home" size={20} color={colors.primary} />
              <View style={styles.helpItemText}>
                <Text style={styles.helpItemTitle}>{t.nav_home_tab}</Text>
                <Text style={styles.methodologyText}>{t.home_help_home_text}</Text>
              </View>
            </View>

            <View style={styles.helpItem}>
              <Ionicons name="pricetag" size={20} color={colors.primary} />
              <View style={styles.helpItemText}>
                <Text style={styles.helpItemTitle}>{t.nav_products}</Text>
                <Text style={styles.methodologyText}>{t.home_help_products_text}</Text>
              </View>
            </View>

            <View style={styles.helpItem}>
              <Ionicons name="storefront" size={20} color={colors.primary} />
              <View style={styles.helpItemText}>
                <Text style={styles.helpItemTitle}>{t.nav_markets}</Text>
                <Text style={styles.methodologyText}>{t.home_help_markets_text}</Text>
              </View>
            </View>

            <View style={styles.helpItem}>
              <Ionicons name="flask" size={20} color={colors.primary} />
              <View style={styles.helpItemText}>
                <Text style={styles.helpItemTitle}>{t.nav_inputs}</Text>
                <Text style={styles.methodologyText}>{t.home_help_inputs_text}</Text>
              </View>
            </View>

            <View style={styles.helpItem}>
              <Ionicons name="map" size={20} color={colors.primary} />
              <View style={styles.helpItemText}>
                <Text style={styles.helpItemTitle}>{t.nav_map}</Text>
                <Text style={styles.methodologyText}>{t.home_help_map_text}</Text>
              </View>
            </View>

            {/* Divider */}
            <View style={styles.helpDivider} />

            {/* Methodology */}
            <Text style={styles.helpSectionTitle}>{t.home_sources_methodology}</Text>

            <Text style={styles.methodologyHeading}>Fuente de datos</Text>
            <Text style={styles.methodologyText}>
              {t.home_sources_text}
            </Text>

            <Text style={styles.methodologyHeading}>Precios mayoristas</Text>
            <Text style={styles.methodologyText}>
              Publicados diariamente en boletines PDF por mercado. Incluyen precios mínimo y máximo en dos rondas de negociación. Cubren 43 mercados en 23 ciudades desde junio de 2012. Los documentos escaneados se procesan mediante OCR con inteligencia artificial.
            </Text>

            <Text style={styles.methodologyHeading}>Abastecimiento</Text>
            <Text style={styles.methodologyText}>
              Registran los kilogramos de alimentos que ingresan diariamente a los mercados mayoristas, con departamento y municipio de origen. Disponibles desde 2013 para 18 mercados.
            </Text>

            <Text style={styles.methodologyHeading}>Insumos agropecuarios</Text>
            <Text style={styles.methodologyText}>
              Precios promedio mensuales a nivel de municipio y departamento. Incluyen marca comercial y código CPC. Disponibles desde 2013.
            </Text>

            <Text style={styles.methodologyHeading}>Leche y arroz</Text>
            <Text style={styles.methodologyText}>
              Precios mensuales de leche cruda en finca (por litro) y arroz en molino (por tonelada), por municipio. Desde 2013.
            </Text>

            <Text style={styles.methodologyHeading}>Procesamiento y normalización</Text>
            <Text style={styles.methodologyText}>
              Los datos se extraen automáticamente de los archivos del DANE, se normalizan para unificar variaciones en nombres de productos, mercados y presentaciones, y se almacenan con identificadores únicos para seguimiento consistente. Cada producto se clasifica por categoría, subcategoría y código CPC.
            </Text>

            <Text style={styles.methodologyHeading}>Frecuencia de actualización</Text>
            <Text style={styles.methodologyText}>
              Precios mayoristas: diaria. Abastecimiento: diaria (publicación mensual). Leche, arroz e insumos: mensual.
            </Text>

            <Text style={[styles.methodologyText, { marginTop: spacing.lg, fontStyle: 'italic', color: colors.text.secondary, opacity: 0.7 }]}>
              {t.home_disclaimer}
            </Text>
          </ScrollView>
        </View>
      </Modal>

      <View style={{ height: 20 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    paddingBottom: 20,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.background,
    gap: spacing.md,
  },
  loadingText: {
    fontSize: fontSize.md,
    color: colors.text.secondary,
  },
  // Ticker
  ticker: {
    backgroundColor: colors.dark,
    maxHeight: 56,
  },
  tickerContent: {
    paddingHorizontal: spacing.md,
    gap: spacing.lg,
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  tickerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingRight: spacing.lg,
  },
  tickerName: {
    color: colors.text.inverse,
    fontSize: fontSize.sm,
    fontWeight: '600',
    maxWidth: 80,
  },
  tickerPrice: {
    color: colors.text.inverse,
    fontSize: fontSize.sm,
    fontFamily: 'monospace',
  },
  // Market Banner
  marketBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  marketBannerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flex: 1,
  },
  marketBannerText: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    color: colors.text.primary,
    flex: 1,
  },
  // Market Info Modal
  infoOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
  },
  infoCard: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.xl,
    width: '100%',
    maxWidth: 360,
  },
  infoHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  infoTitle: {
    fontSize: fontSize.lg,
    fontWeight: '700',
    color: colors.text.primary,
  },
  infoBody: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
    lineHeight: 20,
    marginBottom: spacing.sm,
  },
  infoLegend: {
    marginTop: spacing.sm,
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.background,
    borderRadius: borderRadius.sm,
    marginBottom: spacing.md,
  },
  infoLegendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  infoLegendDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  infoLegendText: {
    fontSize: fontSize.xs,
    color: colors.text.secondary,
  },
  infoCloseBtn: {
    backgroundColor: colors.primary,
    paddingVertical: spacing.md,
    borderRadius: borderRadius.md,
    alignItems: 'center',
  },
  infoCloseText: {
    color: colors.text.inverse,
    fontSize: fontSize.md,
    fontWeight: '600',
  },
  // Watchlist
  watchlistCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  watchlistRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  watchlistInfo: {
    flex: 1,
    gap: 2,
  },
  watchlistName: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.text.primary,
  },
  watchlistPrice: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    color: colors.primary,
    fontFamily: 'monospace',
  },
  watchlistMeta: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  watchlistRemove: {
    padding: spacing.xs,
    marginLeft: spacing.sm,
  },
  // Categories
  categoryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
  },
  categoryCard: {
    width: '48%' as any,
    height: 100,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
    flexGrow: 1,
    flexBasis: '46%',
  },
  categoryImage: {
    width: '100%',
    height: '100%',
    position: 'absolute',
  },
  categoryOverlay: {
    flex: 1,
    backgroundColor: 'rgba(26, 46, 26, 0.6)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.sm,
    gap: 4,
  },
  categoryName: {
    color: colors.text.inverse,
    fontSize: fontSize.sm,
    fontWeight: '700',
    textAlign: 'center',
  },
  // Trending
  trendingCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  trendingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  trendingInfo: {
    flex: 1,
    gap: 2,
  },
  trendingName: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.text.primary,
  },
  trendingPrice: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
    fontFamily: 'monospace',
  },
  trendingRight: {
    alignItems: 'flex-end',
    gap: 4,
  },
  // Help
  helpButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.lg,
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  helpButtonText: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
  },
  helpSectionTitle: {
    fontSize: fontSize.lg,
    fontWeight: '700',
    color: colors.primary,
    marginTop: spacing.md,
    marginBottom: spacing.md,
  },
  helpItem: {
    flexDirection: 'row',
    gap: spacing.md,
    marginBottom: spacing.lg,
    alignItems: 'flex-start',
  },
  helpItemText: {
    flex: 1,
    gap: 4,
  },
  helpItemTitle: {
    fontSize: fontSize.md,
    fontWeight: '700',
    color: colors.text.primary,
  },
  helpDivider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
    marginVertical: spacing.lg,
  },
  modalContainer: {
    flex: 1,
    backgroundColor: colors.background,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  modalTitle: {
    fontSize: fontSize.lg,
    fontWeight: '700',
    color: colors.text.primary,
  },
  modalBody: {
    flex: 1,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
  },
  methodologyHeading: {
    fontSize: fontSize.md,
    fontWeight: '700',
    color: colors.text.primary,
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
  },
  methodologyText: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
    lineHeight: 20,
  },
});
