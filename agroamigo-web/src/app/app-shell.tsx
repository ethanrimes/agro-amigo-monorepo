'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { IoSettingsOutline, IoArrowBack } from 'react-icons/io5';
import { colors, spacing } from '@agroamigo/shared';
import { BottomTabs } from '@/components/BottomTabs';
import { useLanguage } from '@/context/LanguageContext';

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { t } = useLanguage();

  const isDetail = pathname.startsWith('/product/') || pathname.startsWith('/market/') || pathname.startsWith('/insumo/');
  const isSettings = pathname === '/settings';
  const showBack = isDetail || isSettings;

  const PAGE_TITLES: Record<string, string> = {
    '/': t.nav_home,
    '/products': t.nav_products,
    '/markets': t.nav_markets,
    '/insumos': t.nav_inputs,
    '/map': t.nav_map,
    '/settings': t.nav_settings,
  };

  let title = PAGE_TITLES[pathname] || 'AgroAmigo';
  if (pathname.startsWith('/product/')) title = t.nav_product;
  if (pathname.startsWith('/market/')) title = t.nav_market;
  if (pathname.startsWith('/insumo/')) title = t.nav_input;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm }}>
          {showBack && (
            <button onClick={() => window.history.back()} style={{ color: colors.text.inverse, display: 'flex', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>
              <IoArrowBack size={22} />
            </button>
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
