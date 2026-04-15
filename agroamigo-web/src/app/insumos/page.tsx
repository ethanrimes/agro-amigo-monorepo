'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { IoFlask, IoChevronForward } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize } from '@agroamigo/shared';
import { getInsumoGrupos, getInsumoSubgrupos, getInsumos } from '@agroamigo/shared/api/insumos';
import { Card } from '@/components/Card';
import { SearchBar } from '@/components/SearchBar';

interface Section { title: string; grupo: string; isFirstInGrupo: boolean; data: any[]; }

function buildSections(insumos: any[]): Section[] {
  const grupoMap = new Map<string, Map<string, any[]>>();
  for (const ins of insumos) {
    const grupo = ins.grupo || 'Otro';
    const subgrupo = ins.subgrupo || 'General';
    if (!grupoMap.has(grupo)) grupoMap.set(grupo, new Map());
    const subMap = grupoMap.get(grupo)!;
    if (!subMap.has(subgrupo)) subMap.set(subgrupo, []);
    subMap.get(subgrupo)!.push(ins);
  }
  const sections: Section[] = [];
  for (const [grupo, subMap] of [...grupoMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    let first = true;
    for (const [subgrupo, items] of [...subMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
      sections.push({ title: subgrupo, grupo, isFirstInGrupo: first, data: items });
      first = false;
    }
  }
  return sections;
}

export default function InsumosPage() {
  const router = useRouter();
  const [grupos, setGrupos] = useState<any[]>([]);
  const [subgrupos, setSubgrupos] = useState<any[]>([]);
  const [insumos, setInsumos] = useState<any[]>([]);
  const [selectedGrupo, setSelectedGrupo] = useState<string | undefined>();
  const [selectedSubgrupo, setSelectedSubgrupo] = useState<string | undefined>();
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => { getInsumoGrupos().then(g => setGrupos(g || [])); loadInsumos(); }, []);
  useEffect(() => {
    if (selectedGrupo) { getInsumoSubgrupos(selectedGrupo).then(s => setSubgrupos(s || [])); setSelectedSubgrupo(undefined); }
    else { setSubgrupos([]); setSelectedSubgrupo(undefined); }
  }, [selectedGrupo]);
  useEffect(() => { loadInsumos(); }, [selectedGrupo, selectedSubgrupo, search]);

  async function loadInsumos() {
    setLoading(true);
    try {
      const data = await getInsumos({ grupoId: selectedGrupo, subgrupoId: selectedSubgrupo, search: search.length >= 2 ? search : undefined, limit: 300 });
      setInsumos(data || []);
    } catch (err) { console.error('Error loading insumos:', err); }
    finally { setLoading(false); }
  }

  const sections = useMemo(() => buildSections(insumos), [insumos]);

  return (
    <div style={{ paddingTop: spacing.md, paddingBottom: 20 }}>
      <SearchBar value={search} onChangeText={setSearch} placeholder="Buscar insumo..." />
      <div className="chip-scroll">
        {[{ id: undefined, canonical_name: 'Todos' }, ...grupos].map(item => (
          <button key={item.id || 'all'} onClick={() => setSelectedGrupo(item.id === selectedGrupo ? undefined : item.id)}
            style={{
              padding: `${spacing.sm}px ${spacing.md}px`, borderRadius: borderRadius.full, whiteSpace: 'nowrap',
              backgroundColor: selectedGrupo === item.id ? colors.secondary : colors.surface,
              color: selectedGrupo === item.id ? colors.text.inverse : colors.text.secondary,
              border: `1px solid ${selectedGrupo === item.id ? colors.secondary : colors.borderLight}`,
              cursor: 'pointer', fontSize: fontSize.sm, fontWeight: 500,
            }}>{item.canonical_name}</button>
        ))}
      </div>
      {subgrupos.length > 0 && (
        <div className="chip-scroll" style={{ marginTop: 4 }}>
          {subgrupos.map(item => (
            <button key={item.id} onClick={() => setSelectedSubgrupo(item.id === selectedSubgrupo ? undefined : item.id)}
              style={{
                padding: `4px ${spacing.sm}px`, borderRadius: borderRadius.full, whiteSpace: 'nowrap',
                backgroundColor: selectedSubgrupo === item.id ? colors.secondary : colors.surface,
                color: selectedSubgrupo === item.id ? colors.text.inverse : colors.text.secondary,
                border: `1px solid ${selectedSubgrupo === item.id ? colors.secondary : colors.borderLight}`,
                cursor: 'pointer', fontSize: fontSize.xs, fontWeight: 500,
              }}>{item.canonical_name}</button>
          ))}
        </div>
      )}
      {loading ? <div className="loading-container"><div className="spinner" /></div> :
        sections.length === 0 ? <p style={{ textAlign: 'center', marginTop: 40, fontSize: fontSize.md, color: colors.text.tertiary }}>No se encontraron insumos</p> :
        sections.map(section => (
          <div key={`${section.grupo}-${section.title}`}>
            {section.isFirstInGrupo && (
              <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.lg}px ${spacing.lg}px ${spacing.xs}px` }}>
                <IoFlask size={14} color={colors.secondary} />
                <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.secondary }}>{section.grupo}</span>
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: `${spacing.xs}px ${spacing.lg}px` }}>
              <span style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.text.secondary }}>{section.title}</span>
              <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{section.data.length}</span>
            </div>
            {section.data.map(item => (
              <Card key={item.id} style={{ margin: `0 ${spacing.lg}px ${spacing.xs}px` }} onPress={() => router.push(`/insumo/${item.id}`)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: spacing.md }}>
                  <div style={{ width: 40, height: 40, borderRadius: borderRadius.md, backgroundColor: colors.secondary + '15', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <IoFlask size={22} color={colors.secondary} />
                  </div>
                  <div style={{ flex: 1 }}><span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.canonical_name}</span></div>
                  <IoChevronForward size={18} color={colors.text.tertiary} />
                </div>
              </Card>
            ))}
          </div>
        ))}
    </div>
  );
}
