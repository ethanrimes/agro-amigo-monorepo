'use client';

import React from 'react';
import { colors } from '@agroamigo/shared';

interface Props {
  data: number[];
  width?: number;
  height?: number;
}

export function Sparkline({ data, width = 60, height = 24 }: Props) {
  if (data.length < 2) {
    return <div style={{ width, height }} />;
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const padding = 2;

  const points = data
    .map((val, i) => {
      const x = padding + (i / (data.length - 1)) * (width - padding * 2);
      const y = padding + (1 - (val - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(' ');

  const trendColor = data[data.length - 1] >= data[0] ? colors.price.up : colors.price.down;

  return (
    <svg width={width} height={height}>
      <polyline
        points={points}
        fill="none"
        stroke={trendColor}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
