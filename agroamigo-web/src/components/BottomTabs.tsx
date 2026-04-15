'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { IoHome, IoLeaf, IoStorefront, IoFlask, IoMap } from 'react-icons/io5';
import { colors, fontSize } from '@agroamigo/shared';

const TABS = [
  { href: '/', label: 'Inicio', Icon: IoHome },
  { href: '/products', label: 'Productos', Icon: IoLeaf },
  { href: '/markets', label: 'Mercados', Icon: IoStorefront },
  { href: '/insumos', label: 'Insumos', Icon: IoFlask },
  { href: '/map', label: 'Mapa', Icon: IoMap },
];

export function BottomTabs() {
  const pathname = usePathname();

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
