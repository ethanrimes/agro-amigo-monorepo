'use client';

import React from 'react';
import { colors, borderRadius, spacing } from '@agroamigo/shared';

interface Props {
  children: React.ReactNode;
  style?: React.CSSProperties;
  onPress?: () => void;
  padding?: number;
  className?: string;
}

export function Card({ children, style, onPress, padding = spacing.lg, className }: Props) {
  const baseStyle: React.CSSProperties = {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    boxShadow: `0 2px 8px ${colors.shadow}`,
    padding,
    ...style,
  };

  if (onPress) {
    return (
      <button
        onClick={onPress}
        className={`card-pressable ${className || ''}`}
        style={{ ...baseStyle, border: 'none', width: '100%', textAlign: 'left', cursor: 'pointer' }}
      >
        {children}
      </button>
    );
  }

  return (
    <div className={className} style={baseStyle}>
      {children}
    </div>
  );
}
