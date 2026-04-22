'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { useLanguage } from '@/context/LanguageContext';

function titleFor(pathname: string, t: Record<string, string>): string {
  if (pathname === '/') return t.nav_home_tab || 'Inicio';
  if (pathname.startsWith('/products')) return t.nav_products || 'Productos';
  if (pathname.startsWith('/product/')) return t.nav_products || 'Producto';
  if (pathname.startsWith('/markets')) return t.nav_markets || 'Mercados';
  if (pathname.startsWith('/market/')) return t.nav_markets || 'Mercado';
  if (pathname.startsWith('/insumos')) return 'Insumos';
  if (pathname.startsWith('/insumo/')) return 'Insumo';
  if (pathname.startsWith('/map')) return t.nav_map || 'Mapa';
  if (pathname.startsWith('/settings')) return t.nav_settings || 'Ajustes';
  return 'AgroAmigo';
}

export function TopBar() {
  const pathname = usePathname();
  const { t } = useLanguage();
  return (
    <header className="topbar">
      <h1>{titleFor(pathname, t as unknown as Record<string, string>)}</h1>
    </header>
  );
}
