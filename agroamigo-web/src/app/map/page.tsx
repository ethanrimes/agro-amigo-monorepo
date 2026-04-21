'use client';

import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { IoCash, IoTrendingUp, IoSearch, IoCloseCircle, IoChevronDown } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOPCompact, formatKg, cachedCall } from '@agroamigo/shared';
import { getPricesByDepartment, getSupplyByDepartment, getDepartments, getMarketLocations, getMarketsWithProductData, getProductPresentationsForMap } from '@agroamigo/shared/api/map';
import { getProducts } from '@agroamigo/shared/api/products';
import { useLanguage } from '@/context/LanguageContext';
import dynamic from 'next/dynamic';

const MapComponent = dynamic(() => import('./map-component'), { ssr: false, loading: () => <div className="loading-container"><div className="spinner" /><span>Loading...</span></div> });

const PRICE_COLORS = ['#2D7D46', '#4CAF50', '#8BC34A', '#CDDC39', '#FFC107', '#FF9800', '#F44336'];
const SUPPLY_COLORS = ['#E3F2FD', '#90CAF9', '#42A5F5', '#1E88E5', '#1565C0', '#0D47A1', '#1A237E'];

type Mode = 'price' | 'supply';

export default function MapPage() {
  const router = useRouter();
  const { t } = useLanguage();
  const [mode, setMode] = useState<Mode>('price');
  const [loading, setLoading] = useState(true);
  const [departments, setDepartments] = useState<any[]>([]);
  const [priceData, setPriceData] = useState<any[]>([]);
  const [supplyData, setSupplyData] = useState<any[]>([]);
  const [allMarkets, setAllMarkets] = useState<any[]>([]);

  // Product selector
  const [selectedProduct, setSelectedProduct] = useState<{ id: string; name: string } | null>(null);
  const [showProductPicker, setShowProductPicker] = useState(false);
  const [productSearch, setProductSearch] = useState('');
  const [productResults, setProductResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [activeMarketIds, setActiveMarketIds] = useState<Set<string> | null>(null);
  const [presentations, setPresentations] = useState<any[]>([]);
  const [selectedPresentation, setSelectedPresentation] = useState<{ presentation_id: string; units_id: string; label: string } | null>(null);

  // Load base data (departments + all market locations). Cached so tabbing
  // away and back is instant.
  useEffect(() => {
    (async () => {
      try {
        const [depts, mkts] = await Promise.all([
          cachedCall(`map:departments`, () => getDepartments()),
          cachedCall(`map:marketLocations`, () => getMarketLocations()),
        ]);
        setDepartments(((depts as any[]) || []));
        setAllMarkets((((mkts as any[]) || [])).filter((m: any) => m.lat && m.lng));
      } catch (err) { console.error(err); }
    })();
  }, []);

  // Presentations — deferred until a product is picked, cached per-product.
  useEffect(() => {
    if (selectedProduct && mode === 'price') {
      cachedCall(`map:presentations:${selectedProduct.id}:30`, () => getProductPresentationsForMap(selectedProduct.id, 30))
        .then(p => {
          const list = ((p as any[]) || []);
          setPresentations(list);
          setSelectedPresentation(list.length > 0 ? list[0] : null);
        })
        .catch(() => { setPresentations([]); setSelectedPresentation(null); });
    } else {
      setPresentations([]);
      setSelectedPresentation(null);
    }
  }, [selectedProduct, mode]);

  // Price/supply choropleth data. Does nothing (no network) until a product
  // is picked — avoids the cross-product aggregate that caused timeouts.
  useEffect(() => { loadMapData(); }, [selectedProduct, mode, selectedPresentation]);

  async function loadMapData() {
    const pid = selectedProduct?.id;
    const presId = selectedPresentation?.presentation_id;
    const uId = selectedPresentation?.units_id;
    if (!pid) {
      setPriceData([]); setSupplyData([]); setActiveMarketIds(null); setLoading(false);
      return;
    }
    if (mode === 'price' && !presId) return;
    setLoading(true);
    try {
      const keySuffix = `${pid}:${mode}:30:${presId ?? ''}:${uId ?? ''}`;
      const [prices, supply] = await Promise.all([
        mode === 'price'
          ? cachedCall(`map:prices:${keySuffix}`, () => getPricesByDepartment(pid, 30, presId, uId))
          : Promise.resolve([]),
        mode === 'supply'
          ? cachedCall(`map:supply:${keySuffix}`, () => getSupplyByDepartment(pid, 30))
          : Promise.resolve([]),
      ]);
      setPriceData(((prices as any[]) || []));
      setSupplyData(((supply as any[]) || []));
      const ids = await cachedCall(`map:activeMarkets:${keySuffix}`, () => getMarketsWithProductData(pid, mode, 30, presId, uId));
      setActiveMarketIds(new Set(ids as string[]));
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }

  // Search products with debounce
  const searchProducts = useCallback(async (query: string) => {
    if (query.length < 2) { setProductResults([]); return; }
    setSearchLoading(true);
    try {
      const data = await getProducts({ search: query, limit: 20 });
      setProductResults(data || []);
    } catch (err) { console.error(err); }
    finally { setSearchLoading(false); }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => searchProducts(productSearch), 300);
    return () => clearTimeout(timer);
  }, [productSearch, searchProducts]);

  const deptIdToDivipola = useMemo(() => {
    const codeMap = new Map<string, string>();
    for (const d of departments) { if (d.divipola_code) codeMap.set(d.id, d.divipola_code); }
    return codeMap;
  }, [departments]);

  const divipolaToValue = useMemo(() => {
    const map = new Map<string, number>();
    const dataset = mode === 'price' ? priceData : supplyData;
    const valueKey = mode === 'price' ? 'avg_price' : 'total_kg';
    for (const row of dataset) {
      const code = deptIdToDivipola.get(row.department_id);
      if (code) map.set(code, (row as any)[valueKey] || 0);
    }
    return map;
  }, [mode, priceData, supplyData, deptIdToDivipola]);

  const { minVal, maxVal } = useMemo(() => {
    const values = Array.from(divipolaToValue.values()).filter(v => v > 0);
    if (values.length === 0) return { minVal: 0, maxVal: 1 };
    return { minVal: Math.min(...values), maxVal: Math.max(...values) };
  }, [divipolaToValue]);

  // Filter markets to only those with data
  const visibleMarkets = useMemo(() => {
    if (!activeMarketIds) return allMarkets;
    return allMarkets.filter(m => activeMarketIds.has(m.id));
  }, [allMarkets, activeMarketIds]);

  const colorScale = mode === 'price' ? PRICE_COLORS : SUPPLY_COLORS;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
      {!loading && <MapComponent mode={mode} divipolaToValue={divipolaToValue} minVal={minVal} maxVal={maxVal} colorScale={colorScale} markets={visibleMarkets} onMarketClick={(id: string) => router.push(`/market/${id}`)} />}
      {loading && <div className="loading-container"><div className="spinner" /><span>{t.map_loading}</span></div>}

      {/* Controls */}
      <div style={{ position: 'absolute', top: spacing.md, left: spacing.md, right: spacing.md, backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.md, boxShadow: `0 2px 8px ${colors.shadow}`, zIndex: 1000, display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
        {/* Product selector */}
        <button onClick={() => setShowProductPicker(!showProductPicker)} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%',
          padding: `${spacing.sm}px ${spacing.md}px`, borderRadius: borderRadius.md,
          border: `1px solid ${selectedProduct ? colors.primary : colors.borderLight}`,
          backgroundColor: selectedProduct ? colors.primary + '08' : colors.surface,
          cursor: 'pointer', fontSize: fontSize.sm, fontWeight: 500,
          color: selectedProduct ? colors.primary : colors.text.secondary,
        }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {selectedProduct ? selectedProduct.name : t.map_all_products}
          </span>
          <IoChevronDown size={14} />
        </button>

        {/* Product picker dropdown */}
        {showProductPicker && (
          <div style={{ backgroundColor: colors.surface, borderRadius: borderRadius.md, border: `1px solid ${colors.borderLight}`, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.sm}px ${spacing.md}px`, borderBottom: `1px solid ${colors.borderLight}` }}>
              <IoSearch size={14} color={colors.text.tertiary} />
              <input type="text" value={productSearch} onChange={e => setProductSearch(e.target.value)}
                placeholder={t.map_search_product} autoFocus
                style={{ flex: 1, fontSize: fontSize.sm, color: colors.text.primary, border: 'none', outline: 'none', background: 'transparent', fontFamily: 'inherit' }} />
              {productSearch && <button onClick={() => setProductSearch('')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}><IoCloseCircle size={14} color={colors.text.tertiary} /></button>}
            </div>
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {/* All products option */}
              <button onClick={() => { setSelectedProduct(null); setShowProductPicker(false); setProductSearch(''); }} style={{
                display: 'block', width: '100%', textAlign: 'left', padding: `${spacing.sm}px ${spacing.md}px`,
                borderBottom: `1px solid ${colors.borderLight}`, background: !selectedProduct ? colors.primary + '08' : 'none',
                border: 'none', borderBlockEnd: `1px solid ${colors.borderLight}`, cursor: 'pointer',
                fontSize: fontSize.sm, fontWeight: !selectedProduct ? 600 : 400,
                color: !selectedProduct ? colors.primary : colors.text.primary,
              }}>{t.map_all_products}</button>
              {searchLoading && <div style={{ padding: spacing.md, textAlign: 'center' }}><div className="spinner" style={{ margin: '0 auto', width: 20, height: 20 }} /></div>}
              {productResults.map((p: any) => (
                <button key={p.id} onClick={() => { setSelectedProduct({ id: p.id, name: p.canonical_name }); setShowProductPicker(false); setProductSearch(''); }} style={{
                  display: 'block', width: '100%', textAlign: 'left', padding: `${spacing.sm}px ${spacing.md}px`,
                  background: selectedProduct?.id === p.id ? colors.primary + '08' : 'none',
                  border: 'none', borderBlockEnd: `1px solid ${colors.borderLight}`, cursor: 'pointer',
                }}>
                  <div style={{ fontSize: fontSize.sm, fontWeight: selectedProduct?.id === p.id ? 600 : 400, color: selectedProduct?.id === p.id ? colors.primary : colors.text.primary }}>{p.canonical_name}</div>
                  <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{p.dim_subcategory?.dim_category?.canonical_name}</div>
                </button>
              ))}
              {productSearch.length >= 2 && !searchLoading && productResults.length === 0 && (
                <div style={{ padding: spacing.md, textAlign: 'center', fontSize: fontSize.sm, color: colors.text.tertiary }}>{t.settings_no_results}</div>
              )}
            </div>
          </div>
        )}

        {/* Presentation selector (only when product selected and price mode) */}
        {selectedProduct && mode === 'price' && presentations.length > 0 && (
          <div style={{ display: 'flex', gap: spacing.xs, flexWrap: 'wrap' }}>
            {presentations.map(p => (
              <button key={`${p.presentation_id}|${p.units_id}`}
                onClick={() => setSelectedPresentation(p)}
                style={{
                  padding: `${spacing.xs}px ${spacing.sm}px`, borderRadius: borderRadius.full,
                  backgroundColor: selectedPresentation?.presentation_id === p.presentation_id && selectedPresentation?.units_id === p.units_id ? colors.primary : colors.surface,
                  color: selectedPresentation?.presentation_id === p.presentation_id && selectedPresentation?.units_id === p.units_id ? colors.text.inverse : colors.text.secondary,
                  border: `1px solid ${selectedPresentation?.presentation_id === p.presentation_id && selectedPresentation?.units_id === p.units_id ? colors.primary : colors.borderLight}`,
                  cursor: 'pointer', fontSize: fontSize.xs,
                }}>
                {p.label}
              </button>
            ))}
          </div>
        )}

        {/* Mode toggle */}
        <div style={{ display: 'flex', gap: spacing.sm }}>
          {([['price', t.map_prices, IoCash], ['supply', t.map_supply, IoTrendingUp]] as const).map(([m, label, Icon]) => (
            <button key={m} onClick={() => setMode(m)} style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: spacing.xs,
              padding: `${spacing.sm}px`, borderRadius: borderRadius.md, border: 'none', cursor: 'pointer',
              backgroundColor: mode === m ? colors.primary : colors.borderLight,
              color: mode === m ? colors.text.inverse : colors.text.secondary, fontSize: fontSize.sm, fontWeight: 600,
            }}>
              <Icon size={16} />{label}
            </button>
          ))}
        </div>
        <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary, textAlign: 'center' }}>
          {selectedProduct
            ? `${selectedProduct.name} — ${mode === 'price' ? t.map_price_legend : t.map_supply_legend}`
            : (mode === 'price' ? t.map_price_legend : t.map_supply_legend)}
        </div>
      </div>

      {/* Legend */}
      {!loading && (
        <div style={{ position: 'absolute', bottom: spacing.lg, left: spacing.md, right: spacing.md, backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.md, boxShadow: `0 -2px 8px ${colors.shadow}`, zIndex: 1000 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: spacing.xs, justifyContent: 'center', flexWrap: 'wrap' }}>
            <div style={{ width: 20, height: 12, borderRadius: 2, backgroundColor: colorScale[0] }} />
            <span style={{ fontSize: fontSize.xs, color: colors.text.secondary, marginRight: spacing.xs }}>{mode === 'price' ? formatCOPCompact(minVal) : formatKg(minVal)}</span>
            <div style={{ width: 20, height: 12, borderRadius: 2, backgroundColor: colorScale[3] }} />
            <div style={{ width: 20, height: 12, borderRadius: 2, backgroundColor: colorScale[6] }} />
            <span style={{ fontSize: fontSize.xs, color: colors.text.secondary, marginRight: spacing.xs }}>{mode === 'price' ? formatCOPCompact(maxVal) : formatKg(maxVal)}</span>
            <div style={{ width: 20, height: 12, borderRadius: 2, backgroundColor: '#E0E0E0' }} />
            <span style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{t.map_no_data}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: spacing.md, marginTop: 2 }}>
            <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.map_source}</span>
            {selectedProduct && <span style={{ fontSize: fontSize.xs, color: colors.primary, fontWeight: 600 }}>{visibleMarkets.length} mercados</span>}
          </div>
          {selectedProduct && (
            <div style={{ textAlign: 'center', marginTop: spacing.xs }}>
              <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary, fontStyle: 'italic' }}>{t.map_no_highlight_note}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
