'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  IoHomeOutline, IoLeafOutline, IoStorefrontOutline, IoFlaskOutline,
  IoMapOutline, IoSettingsOutline, IoMenuOutline, IoCloseOutline,
} from 'react-icons/io5';
import { useLanguage } from '@/context/LanguageContext';

const navItems = [
  { href: '/', label: 'home', Icon: IoHomeOutline },
  { href: '/products', label: 'products', Icon: IoLeafOutline },
  { href: '/markets', label: 'markets', Icon: IoStorefrontOutline },
  { href: '/insumos', label: 'insumos', Icon: IoFlaskOutline },
  { href: '/map', label: 'map', Icon: IoMapOutline },
  { href: '/settings', label: 'settings', Icon: IoSettingsOutline },
] as const;

function labelFor(key: (typeof navItems)[number]['label'], t: Record<string, string>): string {
  switch (key) {
    case 'home': return t.nav_home_tab || 'Inicio';
    case 'products': return t.nav_products || 'Productos';
    case 'markets': return t.nav_markets || 'Mercados';
    case 'insumos': return 'Insumos';
    case 'map': return t.nav_map || 'Mapa';
    case 'settings': return t.nav_settings || 'Ajustes';
  }
}

export function Sidebar() {
  const pathname = usePathname();
  const { t } = useLanguage();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href);

  return (
    <>
      <button
        aria-label="Menu"
        onClick={() => setMobileOpen(true)}
        style={{
          display: 'none', position: 'fixed', top: 10, left: 10, zIndex: 30,
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 8, padding: 8, cursor: 'pointer',
        }}
        className="mobile-menu-btn"
      >
        <IoMenuOutline size={20} />
      </button>

      {mobileOpen && (
        <div className="sidebar-backdrop" onClick={() => setMobileOpen(false)} />
      )}

      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <span style={{ fontSize: 22 }}>🌱</span>
          AgroAmigo
          <span className="spacer" />
          <button
            onClick={() => setMobileOpen(false)}
            aria-label="Close"
            style={{ display: 'none', background: 'none', border: 'none', cursor: 'pointer' }}
            className="sidebar-close"
          >
            <IoCloseOutline size={20} />
          </button>
        </div>

        <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {navItems.map(({ href, label, Icon }) => (
            <Link
              key={href}
              href={href}
              className={`nav-item ${isActive(href) ? 'active' : ''}`}
              onClick={() => setMobileOpen(false)}
            >
              <Icon size={18} />
              {labelFor(label, t as unknown as Record<string, string>)}
            </Link>
          ))}
        </nav>

        <div className="spacer" />

        <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)', padding: '12px', borderTop: '1px solid var(--color-border-light)' }}>
          Precios DANE · SIPSA
        </div>
      </aside>
    </>
  );
}
