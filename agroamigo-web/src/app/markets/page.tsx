'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { IoStorefront, IoLocation, IoChevronForward } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize } from '@agroamigo/shared';
import { getMarkets } from '@agroamigo/shared/api/markets';
import { Card } from '@/components/Card';
import { SearchBar } from '@/components/SearchBar';

interface MarketItem { id: string; canonical_name: string; city_name: string; department_name: string; }
interface Section { title: string; data: MarketItem[]; }

export default function MarketsPage() {
  const router = useRouter();
  const [sections, setSections] = useState<Section[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadMarkets(); }, []);

  async function loadMarkets() {
    try {
      const data = await getMarkets();
      if (!data) return;
      const grouped = new Map<string, MarketItem[]>();
      for (const m of data) {
        const dept = (m as any).dim_city?.dim_department?.canonical_name || 'Otro';
        const city = (m as any).dim_city?.canonical_name || '';
        const item: MarketItem = { id: m.id, canonical_name: m.canonical_name, city_name: city, department_name: dept };
        if (!grouped.has(dept)) grouped.set(dept, []);
        grouped.get(dept)!.push(item);
      }
      setSections(Array.from(grouped.entries()).map(([title, data]) => ({ title, data })).sort((a, b) => a.title.localeCompare(b.title)));
    } catch (err) { console.error('Error loading markets:', err); }
    finally { setLoading(false); }
  }

  const filteredSections = useMemo(() => {
    if (search.length < 2) return sections;
    return sections
      .map(s => ({ ...s, data: s.data.filter(m => m.canonical_name.toLowerCase().includes(search.toLowerCase()) || m.city_name.toLowerCase().includes(search.toLowerCase())) }))
      .filter(s => s.data.length > 0);
  }, [sections, search]);

  if (loading) return <div className="loading-container"><div className="spinner" /></div>;

  return (
    <div style={{ paddingTop: spacing.md, paddingBottom: 20 }}>
      <SearchBar value={search} onChangeText={setSearch} placeholder="Buscar mercado o ciudad..." />
      {filteredSections.length === 0 ? (
        <p style={{ textAlign: 'center', marginTop: 40, fontSize: fontSize.md, color: colors.text.tertiary }}>No se encontraron mercados</p>
      ) : filteredSections.map(section => (
        <div key={section.title}>
          <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.lg}px ${spacing.lg}px ${spacing.sm}px` }}>
            <IoLocation size={14} color={colors.primary} />
            <span style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.text.primary }}>{section.title}</span>
          </div>
          {section.data.map(item => (
            <Card key={item.id} style={{ margin: `0 ${spacing.lg}px ${spacing.sm}px` }} onPress={() => router.push(`/market/${item.id}`)}>
              <div style={{ display: 'flex', alignItems: 'center', gap: spacing.md }}>
                <div style={{ width: 44, height: 44, borderRadius: borderRadius.md, backgroundColor: colors.primary + '15', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <IoStorefront size={24} color={colors.primary} />
                </div>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.canonical_name}</span>
                  <span style={{ fontSize: fontSize.sm, color: colors.text.secondary }}>{item.city_name}</span>
                </div>
                <IoChevronForward size={18} color={colors.text.tertiary} />
              </div>
            </Card>
          ))}
        </div>
      ))}
    </div>
  );
}
