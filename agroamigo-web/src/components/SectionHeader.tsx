'use client';

import React from 'react';
import { IoChevronForward } from 'react-icons/io5';
import { colors, fontSize, spacing } from '@agroamigo/shared';

interface Props {
  title: string;
  onSeeAll?: () => void;
}

export function SectionHeader({ title, onSeeAll }: Props) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: `${spacing.md}px ${spacing.lg}px`,
    }}>
      <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary }}>{title}</span>
      {onSeeAll && (
        <button
          onClick={onSeeAll}
          style={{
            display: 'flex', alignItems: 'center', gap: 2,
            background: 'none', border: 'none', cursor: 'pointer', padding: 0,
          }}
        >
          <span style={{ fontSize: fontSize.sm, color: colors.primary, fontWeight: 600 }}>Ver todo</span>
          <IoChevronForward size={14} color={colors.primary} />
        </button>
      )}
    </div>
  );
}
