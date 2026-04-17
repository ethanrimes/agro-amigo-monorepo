'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { IoHome, IoLeaf, IoStorefront, IoFlask, IoMap } from 'react-icons/io5';
import { colors, fontSize } from '@agroamigo/shared';
import { useLanguage } from '@/context/LanguageContext';

export function BottomTabs() {
  const pathname = usePathname();
  const { t } = useLanguage();

  const TABS = [
    { href: '/', label: t.nav_home_tab, Icon: IoHome },
    { href: '/products', label: t.nav_products, Icon: IoLeaf },
    { href: '/markets', label: t.nav_markets, Icon: IoStorefront },
    { href: '/insumos', label: t.nav_inputs, Icon: IoFlask },
    { href: '/map', label: t.nav_map, Icon: IoMap },
  ];

  function isActive(href: string) {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  }

  return (
    <nav style={{
      display: 'flex',
      backgroundColor: colors.dark,
      borderTop: `1px solid ${colors.darkSurface}`,
      height: 60,
      paddingBottom: 6,
      paddingTop: 4,
    }}>
      {TABS.map(({ href, label, Icon }) => {
        const active = isActive(href);
        return (
          <Link
            key={href}
            href={href}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 2,
              textDecoration: 'none',
              color: active ? colors.primaryLight : colors.text.tertiary,
            }}
          >
            <Icon size={22} />
            <span style={{ fontSize: fontSize.xs, fontWeight: 600 }}>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
