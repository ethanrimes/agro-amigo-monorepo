'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { IoTrendingUp, IoTrendingDown, IoArrowForward, IoLeafOutline, IoStorefrontOutline, IoCubeOutline } from 'react-icons/io5';
import { colors, formatCOP, formatCOPCompact, formatKg, formatDateShort, pctChange, cachedCall } from '@agroamigo/shared';
import { getCategories, getTrendingProducts } from '@agroamigo/shared/api/products';
import { getTopSuppliedProducts } from '@agroamigo/shared/api/supply';
import { useLanguage } from '@/context/LanguageContext';

export default function HomePage() {
  const router = useRouter();
  const { t } = useLanguage();
  const [categories, setCategories] = useState<any[]>([]);
  const [trending, setTrending] = useState<any[]>([]);
  const [topSupplied, setTopSupplied] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [cats, trend, sup] = await Promise.all([
          cachedCall('home:categories', () => getCategories()),
          cachedCall('home:trending:12', () => getTrendingProducts(12)),
          cachedCall('home:topSupplied:10', () => getTopSuppliedProducts(10)),
        ]);
        setCategories(((cats as any[]) || []));
        setTrending(((trend as any[]) || []));
        setTopSupplied(((sup as any[]) || []));
      } catch (err) { console.error(err); }
      finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <div className="loading-container"><div className="spinner" /> <span>Cargando…</span></div>;

  return (
    <div className="vstack" style={{ gap: 24 }}>
      {/* KPI row */}
      <div className="grid-cards">
        <Kpi
          icon={<IoLeafOutline size={24} color={colors.primary} />}
          value={trending.length}
          label="Productos con tendencia"
        />
        <Kpi
          icon={<IoStorefrontOutline size={24} color={colors.primary} />}
          value={categories.length}
          label="Categorías cubiertas"
        />
        <Kpi
          icon={<IoCubeOutline size={24} color={colors.accent.blue} />}
          value={formatKg(topSupplied.reduce((s, p) => s + (p.total_kg || 0), 0))}
          label="Abasto reciente (top 10)"
        />
      </div>

      {/* Trending products */}
      <section className="card">
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Productos en tendencia</h2>
          <span className="spacer" />
          <button
            onClick={() => router.push('/products')}
            className="chip"
          >
            Ver todos <IoArrowForward size={12} />
          </button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Producto</th>
                <th>Categoría</th>
                <th className="num">Precio actual</th>
                <th className="num">Var. semanal</th>
                <th>Fecha</th>
              </tr>
            </thead>
            <tbody>
              {trending.map((p: any) => {
                const curr = p.latest_avg_price ?? p.avg_price ?? p.min_price ?? 0;
                const prev = p.prev_avg_price ?? p.prev_price ?? null;
                const change = prev ? pctChange(prev, curr) : null;
                return (
                  <tr
                    key={p.id || p.product_id}
                    onClick={() => router.push(`/product/${p.id || p.product_id}`)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>{p.canonical_name || p.product_name}</td>
                    <td className="muted">{p.dim_subcategory?.dim_category?.canonical_name || p.category_name || '—'}</td>
                    <td className="num" style={{ color: colors.primary, fontWeight: 600 }}>{formatCOP(curr)}</td>
                    <td className="num">
                      {change != null ? (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          color: change > 0 ? colors.accent.orange : change < 0 ? colors.accent.blue : colors.text.tertiary,
                          fontWeight: 600,
                        }}>
                          {change > 0 ? <IoTrendingUp size={12} /> : change < 0 ? <IoTrendingDown size={12} /> : null}
                          {change > 0 ? '+' : ''}{change.toFixed(1)}%
                        </span>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td className="muted">{p.latest_date ? formatDateShort(p.latest_date) : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid-2">
        <section className="card">
          <h2>Más abastecidos</h2>
          <div className="vstack" style={{ gap: 10 }}>
            {topSupplied.slice(0, 8).map((p: any, i: number) => {
              const max = topSupplied[0]?.total_kg || 1;
              const pct = ((p.total_kg || 0) / max) * 100;
              return (
                <div
                  key={p.product_id || i}
                  onClick={() => p.product_id && router.push(`/product/${p.product_id}`)}
                  style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: p.product_id ? 'pointer' : 'default' }}
                >
                  <span style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {p.product_name || p.canonical_name || 'Producto'}
                  </span>
                  <div style={{ flex: 1, height: 10, background: 'var(--color-border-light)', borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: colors.accent.blue, borderRadius: 4 }} />
                  </div>
                  <span className="num" style={{ width: 80, fontSize: 12, fontWeight: 600 }}>{formatCOPCompact(p.total_kg || 0).replace('$', '')} kg</span>
                </div>
              );
            })}
          </div>
        </section>

        <section className="card">
          <h2>Categorías</h2>
          <div className="vstack" style={{ gap: 4 }}>
            {categories.slice(0, 12).map((c: any) => (
              <button
                key={c.id}
                className="nav-item"
                onClick={() => router.push(`/products?category=${encodeURIComponent(c.canonical_name)}`)}
                style={{ justifyContent: 'space-between' }}
              >
                <span>{c.canonical_name}</span>
                <IoArrowForward size={12} color="var(--color-text-tertiary)" />
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function Kpi({ icon, value, label }: { icon: React.ReactNode; value: React.ReactNode; label: string }) {
  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{
          width: 44, height: 44, borderRadius: 12,
          background: 'color-mix(in srgb, var(--color-primary) 10%, transparent)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>{icon}</div>
        <div className="stat">
          <span className="value" style={{ fontSize: 22 }}>{value}</span>
          <span className="label">{label}</span>
        </div>
      </div>
    </div>
  );
}
