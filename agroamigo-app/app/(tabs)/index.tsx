import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, Image, Pressable, FlatList, ActivityIndicator, Modal } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { SectionHeader } from '../../src/components/SectionHeader';
import { Sparkline } from '../../src/components/Sparkline';
import { PriceChangeIndicator } from '../../src/components/PriceChangeIndicator';
import { getCategories, getTrendingProducts } from '../../src/api/products';
import { getCategoryImageUrl } from '../../src/lib/images';
import { formatCOP, formatCOPCompact, pctChange } from '../../src/lib/format';

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
  const [categories, setCategories] = useState<any[]>([]);
  const [trending, setTrending] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showMethodology, setShowMethodology] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [cats, trend] = await Promise.all([
        getCategories(),
        getTrendingProducts(200),
      ]);
      setCategories(cats || []);

      // Aggregate trending by product — compute a simple price change
      const productMap = new Map<string, { name: string; prices: number[]; productId: string }>();
      for (const obs of (trend || [])) {
        const pid = obs.product_id;
        const name = obs.dim_product?.canonical_name || 'Unknown';
        const price = obs.avg_price || obs.max_price || obs.min_price || 0;
        if (!productMap.has(pid)) {
          productMap.set(pid, { name, prices: [], productId: pid });
        }
        productMap.get(pid)!.prices.push(price);
      }

      const trendingList = Array.from(productMap.values())
        .filter(p => p.prices.length >= 2)
        .map(p => {
          const oldest = p.prices[p.prices.length - 1];
          const newest = p.prices[0];
          return {
            ...p,
            change: pctChange(oldest, newest),
            latestPrice: newest,
          };
        })
        .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
        .slice(0, 15);

      setTrending(trendingList);
    } catch (err) {
      console.error('Error loading home data:', err);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingText}>Cargando datos...</Text>
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

      {/* Categories */}
      <SectionHeader title="Categorías" />
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

      {/* Trending */}
      <SectionHeader title="Tendencias de la semana" />
      {trending.map((item) => (
        <Card
          key={item.productId}
          style={styles.trendingCard}
          onPress={() => router.push(`/product/${item.productId}`)}
        >
          <View style={styles.trendingRow}>
            <View style={styles.trendingInfo}>
              <Text style={styles.trendingName} numberOfLines={1}>{item.name}</Text>
              <Text style={styles.trendingPrice}>{formatCOP(item.latestPrice)}</Text>
            </View>
            <View style={styles.trendingRight}>
              <Sparkline data={[...item.prices].reverse()} width={50} height={20} />
              <PriceChangeIndicator value={item.change} size="sm" />
            </View>
          </View>
        </Card>
      ))}

      {/* Help */}
      <Pressable
        style={styles.helpButton}
        onPress={() => setShowMethodology(true)}
      >
        <Ionicons name="help-circle-outline" size={20} color={colors.text.secondary} />
        <Text style={styles.helpButtonText}>Ayuda y metodología</Text>
      </Pressable>

      <Modal
        visible={showMethodology}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowMethodology(false)}
      >
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Ayuda</Text>
            <Pressable onPress={() => setShowMethodology(false)} hitSlop={12}>
              <Ionicons name="close" size={24} color={colors.text.primary} />
            </Pressable>
          </View>
          <ScrollView style={styles.modalBody} contentContainerStyle={{ paddingBottom: 40 }}>

            {/* App Guide */}
            <Text style={styles.helpSectionTitle}>Guía de la aplicación</Text>

            <View style={styles.helpItem}>
              <Ionicons name="home" size={20} color={colors.primary} />
              <View style={styles.helpItemText}>
                <Text style={styles.helpItemTitle}>Inicio</Text>
                <Text style={styles.methodologyText}>Tu panel principal. Muestra las tendencias del día, tus productos favoritos y las categorías disponibles. Configura tu mercado preferido en Perfil para ver datos relevantes.</Text>
              </View>
            </View>

            <View style={styles.helpItem}>
              <Ionicons name="pricetag" size={20} color={colors.primary} />
              <View style={styles.helpItemText}>
                <Text style={styles.helpItemTitle}>Productos</Text>
                <Text style={styles.methodologyText}>Explora más de 700 productos agrícolas. Cada producto muestra precios históricos, comparación entre mercados, volúmenes de abastecimiento y productos relacionados. Puedes agregar series al gráfico para comparar productos o mercados lado a lado.</Text>
              </View>
            </View>

            <View style={styles.helpItem}>
              <Ionicons name="storefront" size={20} color={colors.primary} />
              <View style={styles.helpItemText}>
                <Text style={styles.helpItemTitle}>Mercados</Text>
                <Text style={styles.methodologyText}>Consulta los 43 mercados mayoristas y más de 500 mercados municipales. Ve todos los productos disponibles con precios actuales, comparación con la mediana nacional y origen geográfico de los alimentos.</Text>
              </View>
            </View>

            <View style={styles.helpItem}>
              <Ionicons name="flask" size={20} color={colors.primary} />
              <View style={styles.helpItemText}>
                <Text style={styles.helpItemTitle}>Insumos</Text>
                <Text style={styles.methodologyText}>Precios de más de 2,000 insumos agropecuarios (fertilizantes, herbicidas, medicamentos, etc.) por departamento y municipio. Compara marcas comerciales y sigue la evolución de precios.</Text>
              </View>
            </View>

            <View style={styles.helpItem}>
              <Ionicons name="map" size={20} color={colors.primary} />
              <View style={styles.helpItemText}>
                <Text style={styles.helpItemTitle}>Mapa</Text>
                <Text style={styles.methodologyText}>Visualiza precios y flujos de abastecimiento sobre el mapa de Colombia. Selecciona un producto para ver qué regiones tienen los mejores precios o de dónde provienen los alimentos.</Text>
              </View>
            </View>

            {/* Divider */}
            <View style={styles.helpDivider} />

            {/* Methodology */}
            <Text style={styles.helpSectionTitle}>Fuentes y metodología</Text>

            <Text style={styles.methodologyHeading}>Fuente de datos</Text>
            <Text style={styles.methodologyText}>
              Todos los datos provienen del SIPSA (Sistema de Información de Precios y Abastecimiento del Sector Agropecuario), operado por el DANE de Colombia.
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
              Esta aplicación no es un producto oficial del DANE. Los datos se presentan tal como fueron publicados, con procesamiento automatizado para facilitar su consulta.
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
