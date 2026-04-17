'use client';

import React, { useEffect, useState, useMemo, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { IoFlask, IoChevronForward, IoChevronDown, IoChevronUp } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize } from '@agroamigo/shared';
import { getInsumoGrupos, getInsumoSubgrupos, getInsumos, getInsumoCpcTree } from '@agroamigo/shared/api/insumos';
import { Card } from '@/components/Card';
import { SearchBar } from '@/components/SearchBar';
import { useLanguage } from '@/context/LanguageContext';

interface CpcGroup {
  code: string;
  title: string;
  insumos: any[];
}

interface SubgrupoNode {
  id: string;
  name: string;
  cpcGroups: CpcGroup[];
  totalCount: number;
}

interface GrupoNode {
  id: string;
  name: string;
  subgrupos: SubgrupoNode[];
  totalCount: number;
}

function buildUnifiedTree(insumos: any[], cpcEntries: any[]): GrupoNode[] {
  const cpcMap = new Map<string, { title: string }>();
  for (const c of cpcEntries) cpcMap.set(c.code, { title: c.title });

  // Group: grupo -> subgrupo -> cpc_code -> insumos
  const grupoMap = new Map<string, { id: string; subMap: Map<string, { id: string; cpcMap: Map<string, any[]> }> }>();

  for (const ins of insumos) {
    const grupoName = ins.grupo || 'Otro';
    const grupoId = ins.grupo_id || 'other';
    const subgrupoName = ins.subgrupo || 'General';
    const subgrupoId = ins.subgrupo_id || 'general';
    const cpcCode = ins.cpc_id || '_none';

    if (!grupoMap.has(grupoName)) grupoMap.set(grupoName, { id: grupoId, subMap: new Map() });
    const grupo = grupoMap.get(grupoName)!;
    if (!grupo.subMap.has(subgrupoName)) grupo.subMap.set(subgrupoName, { id: subgrupoId, cpcMap: new Map() });
    const sub = grupo.subMap.get(subgrupoName)!;
    if (!sub.cpcMap.has(cpcCode)) sub.cpcMap.set(cpcCode, []);
    sub.cpcMap.get(cpcCode)!.push(ins);
  }

  const tree: GrupoNode[] = [];
  for (const [grupoName, grupo] of [...grupoMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    const subgrupos: SubgrupoNode[] = [];
    for (const [subName, sub] of [...grupo.subMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
      const cpcGroups: CpcGroup[] = [];
      for (const [code, items] of [...sub.cpcMap.entries()].sort(([a], [b]) => {
        if (a === '_none') return 1; if (b === '_none') return -1; return a.localeCompare(b);
      })) {
        const cpcInfo = cpcMap.get(code);
        cpcGroups.push({
          code,
          title: cpcInfo?.title || '',
          insumos: items.sort((a: any, b: any) => a.canonical_name.localeCompare(b.canonical_name)),
        });
      }
      const totalCount = cpcGroups.reduce((s, g) => s + g.insumos.length, 0);
      subgrupos.push({ id: sub.id, name: subName, cpcGroups, totalCount });
    }
    const totalCount = subgrupos.reduce((s, sg) => s + sg.totalCount, 0);
    tree.push({ id: grupo.id, name: grupoName, subgrupos, totalCount });
  }
  return tree;
}

function SubgrupoSection({ sub, router }: { sub: SubgrupoNode; router: any }) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div id={`sub-${sub.id}`}>
      <div
        onClick={() => setCollapsed(!collapsed)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: `${spacing.sm}px ${spacing.lg}px`,
          cursor: 'pointer',
          borderBottom: `1px solid ${colors.borderLight}`,
        }}
      >
        <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary }}>
          {sub.name}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm }}>
          <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{sub.totalCount}</span>
          {collapsed ? <IoChevronDown size={14} color={colors.text.tertiary} /> : <IoChevronUp size={14} color={colors.text.tertiary} />}
        </div>
      </div>

      {!collapsed && (
        <>
          {sub.cpcGroups.map(cg => (
            <div key={cg.code}>
              {/* CPC sub-header */}
              {cg.code !== '_none' && (
                <div style={{
                  display: 'flex', alignItems: 'baseline', gap: spacing.sm,
                  padding: `${spacing.sm}px ${spacing.lg}px ${spacing.xs}px ${spacing.xl}px`,
                  backgroundColor: colors.primary + '08',
                  borderTop: `1px solid ${colors.borderLight}`,
                }}>
                  <span style={{ fontSize: fontSize.xs, fontFamily: 'monospace', fontWeight: 600, color: colors.primary, flexShrink: 0 }}>
                    {cg.code}
                  </span>
                  <span style={{ fontSize: fontSize.sm, color: colors.text.secondary }}>
                    {cg.title}
                  </span>
                  <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary, marginLeft: 'auto', flexShrink: 0 }}>
                    {cg.insumos.length}
                  </span>
                </div>
              )}
              {cg.insumos.map((item: any) => (
                <Card key={item.id} style={{ margin: `0 ${spacing.lg}px ${spacing.xs}px`, marginLeft: `${spacing.xl}px` }}
                  onPress={() => router.push(`/insumo/${item.id}`)}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: spacing.md }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: borderRadius.md,
                      backgroundColor: colors.secondary + '15',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    }}>
                      <IoFlask size={18} color={colors.secondary} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{
                        fontSize: fontSize.md, fontWeight: 600, color: colors.text.primary,
                        display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {item.canonical_name}
                      </span>
                    </div>
                    <IoChevronForward size={16} color={colors.text.tertiary} />
                  </div>
                </Card>
              ))}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

export default function InsumosPage() {
  const router = useRouter();
  const { t } = useLanguage();
  const [grupos, setGrupos] = useState<any[]>([]);
  const [subgrupos, setSubgrupos] = useState<any[]>([]);
  const [insumos, setInsumos] = useState<any[]>([]);
  const [cpcEntries, setCpcEntries] = useState<any[]>([]);
  const [selectedGrupo, setSelectedGrupo] = useState<string | undefined>();
  const [selectedSubgrupo, setSelectedSubgrupo] = useState<string | undefined>();
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getInsumoGrupos().then(g => setGrupos(g || []));
    getInsumoCpcTree().then(c => setCpcEntries(c || [])).catch(() => {});
    loadInsumos();
  }, []);

  useEffect(() => {
    if (selectedGrupo) { getInsumoSubgrupos(selectedGrupo).then(s => setSubgrupos(s || [])); setSelectedSubgrupo(undefined); }
    else { setSubgrupos([]); setSelectedSubgrupo(undefined); }
  }, [selectedGrupo]);

  useEffect(() => { loadInsumos(); }, [selectedGrupo, selectedSubgrupo, search]);

  async function loadInsumos() {
    setLoading(true);
    try {
      const data = await getInsumos({ grupoId: selectedGrupo, subgrupoId: selectedSubgrupo, search: search.length >= 2 ? search : undefined, limit: 2000 });
      setInsumos(data || []);
    } catch (err) { console.error('Error loading insumos:', err); }
    finally { setLoading(false); }
  }

  const tree = useMemo(() => buildUnifiedTree(insumos, cpcEntries), [insumos, cpcEntries]);
  const isSearching = search.length >= 2;


  return (
    <div style={{ paddingTop: spacing.md, paddingBottom: 20, position: 'relative' }}>
      <SearchBar value={search} onChangeText={setSearch} placeholder={t.inputs_search} />

      <div className="chip-scroll">
        {[{ id: undefined, canonical_name: t.inputs_all }, ...grupos].map(item => (
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

      {loading ? (
        <div className="loading-container"><div className="spinner" /></div>
      ) : tree.length === 0 ? (
        <p style={{ textAlign: 'center', marginTop: 40, fontSize: fontSize.md, color: colors.text.tertiary }}>{t.inputs_not_found}</p>
      ) : (
        <>
          {tree.map(grupo => (
            <div key={grupo.id} id={`grupo-${grupo.id}`}>
              {/* Grupo header */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: spacing.sm,
                padding: `${spacing.lg}px ${spacing.lg}px ${spacing.sm}px`,
                backgroundColor: colors.secondary + '12',
                borderBottom: `2px solid ${colors.secondary}33`,
                marginTop: spacing.sm,
              }}>
                <IoFlask size={16} color={colors.secondary} />
                <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.secondary, flex: 1 }}>
                  {grupo.name}
                </span>
                <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{grupo.totalCount}</span>
              </div>

              {/* Subgrupo sections */}
              {grupo.subgrupos.map(sub => (
                <SubgrupoSection key={sub.id} sub={sub} router={router} />
              ))}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
