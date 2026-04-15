'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { IoSettingsOutline, IoArrowBack } from 'react-icons/io5';
import { colors, spacing } from '@agroamigo/shared';
import { BottomTabs } from '@/components/BottomTabs';

const PAGE_TITLES: Record<string, string> = {
  '/': 'AgroAmigo',
  '/products': 'Productos',
  '/markets': 'Mercados',
  '/insumos': 'Insumos',
  '/map': 'Mapa',
  '/settings': 'Configuraci\u00f3n',
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const isDetail = pathname.startsWith('/product/') || pathname.startsWith('/market/') || pathname.startsWith('/insumo/');
  const isSettings = pathname === '/settings';
  const showBack = isDetail || isSettings;

  let title = PAGE_TITLES[pathname] || 'AgroAmigo';
  if (pathname.startsWith('/product/')) title = 'Producto';
  if (pathname.startsWith('/market/')) title = 'Mercado';
  if (pathname.startsWith('/insumo/')) title = 'Insumo';

  return (
    <div className="app-shell">
      <header className="app-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm }}>
          {showBack && (
            <Link href="javascript:void(0)" onClick={() => window.history.back()} style={{ color: colors.text.inverse, display: 'flex' }}>
              <IoArrowBack size={22} />
            </Link>
          )}
          <span>{title}</span>
        </div>
        {!showBack && (
          <Link href="/settings" style={{ color: colors.text.inverse }}>
            <IoSettingsOutline size={22} />
          </Link>
        )}
      </header>
      <main className="app-content">
        {children}
      </main>
      <BottomTabs />
    </div>
  );
}
