'use client';

import React from 'react';
import { IoSearch, IoCloseCircle } from 'react-icons/io5';
import { colors, borderRadius, spacing, fontSize } from '@agroamigo/shared';

interface Props {
  value: string;
  onChangeText: (text: string) => void;
  placeholder?: string;
}

export function SearchBar({ value, onChangeText, placeholder = 'Buscar...' }: Props) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      backgroundColor: colors.surface,
      borderRadius: borderRadius.lg,
      padding: `${spacing.sm}px ${spacing.md}px`,
      margin: `0 ${spacing.lg}px ${spacing.md}px`,
      gap: spacing.sm,
      border: `1px solid ${colors.borderLight}`,
    }}>
      <IoSearch size={18} color={colors.text.tertiary} />
      <input
        type="text"
        value={value}
        onChange={(e) => onChangeText(e.target.value)}
        placeholder={placeholder}
        autoCorrect="off"
        style={{
          flex: 1,
          fontSize: fontSize.md,
          color: colors.text.primary,
          border: 'none',
          outline: 'none',
          background: 'transparent',
          padding: '2px 0',
          fontFamily: 'inherit',
        }}
      />
      {value.length > 0 && (
        <button
          onClick={() => onChangeText('')}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex' }}
        >
          <IoCloseCircle size={18} color={colors.text.tertiary} />
        </button>
      )}
    </div>
  );
}
