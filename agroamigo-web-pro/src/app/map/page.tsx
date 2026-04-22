'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import { IoSearchOutline, IoCloseCircle, IoCash, IoTrendingUp } from 'react-icons/io5';
import { colors, formatCOPCompact, formatKg, cachedCall } from '@agroamigo/shared';
import { getDepartments, getMarketLocations, getMarketsWithProductData, getPricesByDepartment, getProductPresentationsForMap, getSupplyByDepartment } from '@agroamigo/shared/api/map';
import { getProducts } from '@agroamigo/shared/api/products';

const MapComponent = dynamic(() => import('./map-component'), {
  ssr: false,
  loading: () => <div className="loading-container"><div className="spinner" /><span>Cargando mapa…</span></div>,
});

const PRICE_COLORS = ['#2D7D46', '#4CAF50', '#8BC34A', '#CDDC39', '#FFC107', '#FF9800', '#F44336'];
const SUPPLY_COLORS = ['#E3F2FD', '#90CAF9', '#42A5F5', '#1E88E5', '#1565C0', '#0D47A1', '#1A237E'];

type Mode = 'price' | 'supply';

export default function MapPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('price');
  const [loading, setLoading] = useState(false);
  const [departments, setDepartments] = useState<any[]>([]);
  const [priceData, setPriceData] = useState<any[]>([]);
  const [supplyData, setSupplyData] = useState<any[]>([]);
  const [allMarkets, setAllMarkets] = useState<any[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<{ id: string; name: string } | null>(null);
  const [productSearch, setProductSearch] = useState('');
  const [productResults, setProductResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [activeMarketIds, setActiveMarketIds] = useState<Set<string> | null>(null);
  const [presentations, setPresentations] = useState<any[]>([]);
  const [selectedPresentation, setSelectedPresentation] = useState<any>(null);

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

  useEffect(() => {
    if (selectedProduct && mode === 'price') {
      cachedCall(`map:presentations:${selectedProduct.id}:30`, () => getProductPresentationsForMap(selectedProduct.id, 30))
        .then(p => { const list = (p as any[]) || []; setPresentations(list); setSelectedPresentation(list[0] || null); })
        .catch(() => { setPresentations([]); setSelectedPresentation(null); });
    } else { setPresentations([]); setSelectedPresentation(null); }
  }, [selectedProduct, mode]);

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
      const suffix = `${pid}:${mode}:30:${presId ?? ''}:${uId ?? ''}`;
      const [prices, supply] = await Promise.all([
        mode === 'price' ? cachedCall(`map:prices:${suffix}`, () => getPricesByDepartment(pid, 30, presId, uId)) : Promise.resolve([]),
        mode === 'supply' ? cachedCall(`map:supply:${suffix}`, () => getSupplyByDepartment(pid, 30)) : Promise.resolve([]),
      ]);
      setPriceData((prices as any[]) || []);
      setSupplyData((supply as any[]) || []);
      const ids = await cachedCall(`map:activeMarkets:${suffix}`, () => getMarketsWithProductData(pid, mode, 30, presId, uId));
      setActiveMarketIds(new Set(ids as string[]));
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }

  const searchProducts = useCallback(async (q: string) => {
    if (q.length < 2) { setProductResults([]); return; }
    setSearchLoading(true);
    try {
      const d = await getProducts({ search: q, limit: 20 });
      setProductResults(((d as any[]) || []));
    } catch (err) { console.error(err); }
    finally { setSearchLoading(false); }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => searchProducts(productSearch), 300);
    return () => clearTimeout(timer);
  }, [productSearch, searchProducts]);

  const deptIdToDivipola = useMemo(() => {
    const m = new Map<string, string>();
    for (const d of departments) if (d.divipola_code) m.set(d.id, d.divipola_code);
    return m;
  }, [departments]);

  const divipolaToValue = useMemo(() => {
    const m = new Map<string, number>();
    const dataset = mode === 'price' ? priceData : supplyData;
    const key = mode === 'price' ? 'avg_price' : 'total_kg';
    for (const row of dataset) {
      const code = deptIdToDivipola.get(row.department_id);
      if (code) m.set(code, (row as any)[key] || 0);
    }
    return m;
  }, [mode, priceData, supplyData, deptIdToDivipola]);

  const { minVal, maxVal } = useMemo(() => {
    const vals = Array.from(divipolaToValue.values()).filter(v => v > 0);
    return { minVal: vals.length ? Math.min(...vals) : 0, maxVal: vals.length ? Math.max(...vals) : 1 };
  }, [divipolaToValue]);

  const visibleMarkets = useMemo(() => {
    if (!activeMarketIds) return allMarkets;
    return allMarkets.filter(m => activeMarketIds.has(m.id));
  }, [allMarkets, activeMarketIds]);

  const colorScale = mode === 'price' ? PRICE_COLORS : SUPPLY_COLORS;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 16, height: 'calc(100vh - var(--topbar-h) - 48px)' }}>
      <aside className="card" style={{ padding: 16, overflowY: 'auto' }}>
        <h2 style={{ margin: '0 0 12px 0' }}>Mapa de Colombia</h2>

        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <IoSearchOutline size={16} color="var(--color-text-tertiary)" />
            <input
              className="search-input"
              placeholder="Buscar producto…"
              value={productSearch}
              onChange={e => setProductSearch(e.target.value)}
              style={{ flex: 1, padding: '8px 12px' }}
            />
            {productSearch && (
              <button onClick={() => setProductSearch('')} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                <IoCloseCircle size={16} color="var(--color-text-tertiary)" />
              </button>
            )}
          </div>
          {selectedProduct && (
            <div className="chip active" style={{ marginBottom: 8, cursor: 'default' }}>
              {selectedProduct.name}
              <button onClick={() => { setSelectedProduct(null); setProductSearch(''); setProductResults([]); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#fff', padding: 0, marginLeft: 4 }}>
                <IoCloseCircle size={14} />
              </button>
            </div>
          )}
          {searchLoading && <div className="muted" style={{ fontSize: 12, padding: 4 }}>Buscando…</div>}
          {productResults.length > 0 && (
            <div className="vstack" style={{ gap: 0, maxHeight: 260, overflowY: 'auto', border: '1px solid var(--color-border-light)', borderRadius: 8 }}>
              {productResults.map((p: any) => (
                <button
                  key={p.id}
                  onClick={() => { setSelectedProduct({ id: p.id, name: p.canonical_name }); setProductSearch(''); setProductResults([]); }}
                  className="nav-item"
                  style={{ justifyContent: 'flex-start', borderRadius: 0, padding: '8px 12px' }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{p.canonical_name}</div>
                    <div className="muted" style={{ fontSize: 11 }}>{p.dim_subcategory?.dim_category?.canonical_name}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {selectedProduct && mode === 'price' && presentations.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div className="muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 6 }}>Presentación</div>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {presentations.map(p => (
                <button
                  key={`${p.presentation_id}|${p.units_id}`}
                  onClick={() => setSelectedPresentation(p)}
                  className={`chip ${selectedPresentation?.presentation_id === p.presentation_id && selectedPresentation?.units_id === p.units_id ? 'active' : ''}`}
                  style={{ fontSize: 11 }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        )}

        <div style={{ marginBottom: 12 }}>
          <div className="muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 6 }}>Métrica</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setMode('price')} className={`chip ${mode === 'price' ? 'active' : ''}`} style={{ flex: 1, justifyContent: 'center' }}><IoCash size={14} /> Precios</button>
            <button onClick={() => setMode('supply')} className={`chip ${mode === 'supply' ? 'active' : ''}`} style={{ flex: 1, justifyContent: 'center' }}><IoTrendingUp size={14} /> Abasto</button>
          </div>
        </div>

        {selectedProduct && (
          <div style={{ padding: 12, background: 'var(--color-surface-2)', borderRadius: 8, marginBottom: 12 }}>
            <div className="muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 4 }}>Leyenda</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 11 }}>
              <div style={{ width: 20, height: 10, background: colorScale[0], borderRadius: 2 }} />
              <span>{mode === 'price' ? formatCOPCompact(minVal) : formatKg(minVal)}</span>
              <div style={{ width: 20, height: 10, background: colorScale[3], borderRadius: 2 }} />
              <div style={{ width: 20, height: 10, background: colorScale[6], borderRadius: 2 }} />
              <span>{mode === 'price' ? formatCOPCompact(maxVal) : formatKg(maxVal)}</span>
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{visibleMarkets.length} mercados con datos</div>
          </div>
        )}

        {!selectedProduct && (
          <div className="muted" style={{ fontSize: 12, fontStyle: 'italic', padding: 8 }}>
            Seleccione un producto para visualizar precios o abasto por departamento.
          </div>
        )}
      </aside>

      <div className="card" style={{ padding: 0, overflow: 'hidden', position: 'relative' }}>
        {loading && <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 1100, background: 'var(--color-surface)', padding: 8, borderRadius: 8, boxShadow: 'var(--shadow-md)' }}><div className="spinner" /></div>}
        <MapComponent
          mode={mode}
          divipolaToValue={divipolaToValue}
          minVal={minVal}
          maxVal={maxVal}
          colorScale={colorScale}
          markets={visibleMarkets}
          onMarketClick={(id: string) => router.push(`/market/${id}`)}
        />
      </div>
    </div>
  );
}
