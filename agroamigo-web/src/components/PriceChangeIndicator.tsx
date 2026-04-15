'use client';

import React from 'react';
import { IoArrowUp, IoArrowDown, IoRemove } from 'react-icons/io5';
import { colors, fontSize as fontSizes, formatPctChange } from '@agroamigo/shared';

interface Props {
  value: number | null | undefined;
  size?: 'sm' | 'md' | 'lg';
}

export function PriceChangeIndicator({ value, size = 'md' }: Props) {
  if (value == null) return null;

  const isUp = value > 0;
  const isNeutral = Math.abs(value) < 0.1;
  const color = isNeutral ? colors.price.neutral : isUp ? colors.price.up : colors.price.down;
  const Icon = isNeutral ? IoRemove : isUp ? IoArrowUp : IoArrowDown;
  const textSize = size === 'sm' ? fontSizes.xs : size === 'lg' ? fontSizes.lg : fontSizes.sm;
  const iconSize = size === 'sm' ? 10 : size === 'lg' ? 18 : 14;

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      backgroundColor: color + '18',
      padding: '2px 6px',
      borderRadius: 6,
      gap: 2,
    }}>
      <Icon size={iconSize} color={color} />
      <span style={{ color, fontSize: textSize, fontWeight: 600 }}>
        {formatPctChange(value)}
      </span>
    </span>
  );
}
