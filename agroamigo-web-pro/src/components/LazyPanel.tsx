'use client';

import React, { useState } from 'react';
import { IoChevronDown, IoChevronUp } from 'react-icons/io5';

interface Props {
  title: string;
  subtitle?: string;
  badge?: string | number;
  right?: React.ReactNode;
  initiallyExpanded?: boolean;
  onExpandChange?: (expanded: boolean) => void;
  children: React.ReactNode;
}

/**
 * Desktop-styled collapsible panel used by detail pages. Wraps content in a
 * card-like block with a chevron header. When collapsed, children do not
 * render at all (so children can safely fire data fetches on mount).
 */
export function LazyPanel({
  title, subtitle, badge, right, initiallyExpanded = false, onExpandChange, children,
}: Props) {
  const [open, setOpen] = useState(initiallyExpanded);

  React.useEffect(() => {
    if (initiallyExpanded) onExpandChange?.(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    onExpandChange?.(next);
  };

  return (
    <div className="card" style={{ padding: 0 }}>
      <button
        onClick={toggle}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 12,
          padding: '16px 20px', background: 'none', border: 'none', cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--color-text)' }}>{title}</div>
          {subtitle && <div style={{ fontSize: 12, color: 'var(--color-text-tertiary)', marginTop: 2 }}>{subtitle}</div>}
        </div>
        {badge != null && (
          <span style={{
            padding: '2px 10px', borderRadius: 999,
            backgroundColor: 'color-mix(in srgb, var(--color-primary) 12%, transparent)',
            color: 'var(--color-primary)', fontSize: 12, fontWeight: 600,
          }}>{badge}</span>
        )}
        {right}
        {open ? <IoChevronUp size={18} color="var(--color-text-tertiary)" /> : <IoChevronDown size={18} color="var(--color-text-tertiary)" />}
      </button>
      {open && <div style={{ padding: '0 20px 20px' }}>{children}</div>}
    </div>
  );
}
