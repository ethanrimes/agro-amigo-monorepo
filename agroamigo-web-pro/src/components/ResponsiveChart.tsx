'use client';

import React, { useEffect, useRef, useState } from 'react';
import { LineChart, LineChartPoint } from './LineChart';

interface Props {
  data: LineChartPoint[];
  height?: number;
  color?: string;
  showBands?: boolean;
  formatValue?: (v: number) => string;
  minWidth?: number;
}

/**
 * Wraps LineChart with a ResizeObserver so it fills its parent. The base
 * LineChart is fixed-width; on desktop we want charts to grow with the card.
 */
export function ResponsiveChart({ height = 280, minWidth = 320, ...chartProps }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) setWidth(Math.max(minWidth, entry.contentRect.width));
    });
    ro.observe(el);
    setWidth(Math.max(minWidth, el.clientWidth));
    return () => ro.disconnect();
  }, [minWidth]);

  return (
    <div ref={ref} style={{ width: '100%' }}>
      {width > 0 && <LineChart {...chartProps} width={width} height={height} />}
    </div>
  );
}
