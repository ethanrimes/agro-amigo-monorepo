'use client';

import React, { useState, useCallback, useRef } from 'react';
import { colors, spacing, fontSize as fs, formatCOPCompact, formatDateShort } from '@agroamigo/shared';
import { useSettings } from '@/context/SettingsContext';
import { useLanguage } from '@/context/LanguageContext';

export interface LineChartPoint {
  date: string;
  value: number;
  min?: number;
  max?: number;
}

interface LineChartProps {
  data: LineChartPoint[];
  width: number;
  height: number;
  color?: string;
  showBands?: boolean;
  formatValue?: (v: number) => string;
}

function linearRegression(points: { x: number; y: number }[]) {
  const n = points.length;
  if (n < 2) return null;
  let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
  for (const p of points) { sumX += p.x; sumY += p.y; sumXY += p.x * p.y; sumX2 += p.x * p.x; }
  const denom = n * sumX2 - sumX * sumX;
  if (denom === 0) return null;
  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

export function LineChart({ data, width, height, color = colors.primary, showBands = false, formatValue = formatCOPCompact }: LineChartProps) {
  const { settings } = useSettings();
  const { t } = useLanguage();
  const { showAvgLine, showTrendLine, showMinMaxCallouts, showInteractiveCallout } = settings.chart;
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const padding = { top: 10, right: 10, bottom: 30, left: 50 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const allValues = data.flatMap(d => [d.min ?? d.value, d.max ?? d.value, d.value].filter(v => v != null));
  const minY = Math.min(...allValues) * 0.95;
  const maxY = Math.max(...allValues) * 1.05;
  const rangeY = maxY - minY || 1;

  // Time-proportional x-axis: scale by actual date, not index
  const timestamps = data.map(d => new Date(d.date + 'T00:00:00').getTime());
  const minT = timestamps.length > 0 ? timestamps[0] : 0;
  const maxT = timestamps.length > 0 ? timestamps[timestamps.length - 1] : 1;
  const rangeT = maxT - minT || 1;

  const scaleX = (i: number) => padding.left + ((timestamps[i] - minT) / rangeT) * chartW;
  const scaleY = (v: number) => padding.top + (1 - (v - minY) / rangeY) * chartH;

  const mainPoints = data.map((d, i) => `${scaleX(i)},${scaleY(d.value)}`).join(' ');

  // Y-axis labels
  const yLabels = [minY, (minY + maxY) / 2, maxY].map(v => ({ y: scaleY(v), label: formatValue(v) }));

  // X-axis labels — evenly spaced in time, show year for prior years
  const currentYear = new Date().getFullYear();
  const NUM_X_LABELS = 5;
  const xLabels: { idx: number; date: string }[] = [];
  if (data.length > 0) {
    for (let n = 0; n < NUM_X_LABELS; n++) {
      const targetT = minT + (n / (NUM_X_LABELS - 1)) * rangeT;
      // Find closest data point to this target time
      let bestIdx = 0, bestDist = Infinity;
      for (let i = 0; i < timestamps.length; i++) {
        const dist = Math.abs(timestamps[i] - targetT);
        if (dist < bestDist) { bestDist = dist; bestIdx = i; }
      }
      // Avoid duplicates
      if (xLabels.length === 0 || xLabels[xLabels.length - 1].idx !== bestIdx) {
        xLabels.push({ idx: bestIdx, date: data[bestIdx].date });
      }
    }
  }
  function formatXDate(dateStr: string): string {
    const label = formatDateShort(dateStr);
    const year = new Date(dateStr + 'T00:00:00').getFullYear();
    return year < currentYear ? `${label} '${String(year).slice(2)}` : label;
  }

  // Average
  const avgValue = data.length > 0 ? data.reduce((s, d) => s + d.value, 0) / data.length : 0;

  // Trend line
  const trendLine = showTrendLine ? linearRegression(data.map((d, i) => ({ x: i, y: d.value }))) : null;

  // Min/max callouts
  let minIdx = 0, maxIdx = 0;
  if (showMinMaxCallouts && data.length > 0) {
    for (let i = 1; i < data.length; i++) {
      if (data[i].value < data[minIdx].value) minIdx = i;
      if (data[i].value > data[maxIdx].value) maxIdx = i;
    }
  }

  // Bands (min/max area for price charts)
  const minBandPoints = showBands ? data.map((d, i) => `${scaleX(i)},${scaleY(d.min ?? d.value)}`).join(' ') : '';
  const maxBandPoints = showBands ? data.map((d, i) => `${scaleX(i)},${scaleY(d.max ?? d.value)}`).join(' ') : '';

  const handlePointerMove = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (!showInteractiveCallout || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    // Convert pixel to timestamp, find nearest data point
    const targetT = minT + ((x - padding.left) / chartW) * rangeT;
    let bestIdx = 0, bestDist = Infinity;
    for (let i = 0; i < timestamps.length; i++) {
      const dist = Math.abs(timestamps[i] - targetT);
      if (dist < bestDist) { bestDist = dist; bestIdx = i; }
    }
    setHoverIdx(bestIdx);
  }, [showInteractiveCallout, chartW, padding.left, minT, rangeT, timestamps]);

  const handlePointerLeave = useCallback(() => setHoverIdx(null), []);

  // Build legend items
  const legendItems: { color: string; label: string; dashed?: boolean }[] = [];
  if (showAvgLine && data.length > 1) legendItems.push({ color, label: t.settings_chart_avg_line, dashed: true });
  if (showTrendLine && trendLine) legendItems.push({ color: colors.accent.orange, label: t.settings_chart_trend_line, dashed: true });
  if (showMinMaxCallouts && data.length > 2 && minIdx !== maxIdx) {
    legendItems.push({ color: colors.accent.orange, label: t.product_max });
    legendItems.push({ color: colors.accent.blue, label: t.product_min });
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <svg ref={svgRef} width={width} height={height} style={{ touchAction: 'none' }}
        onPointerMove={handlePointerMove} onPointerLeave={handlePointerLeave}>

        {/* Grid lines */}
        {yLabels.map((yl, i) => <line key={i} x1={padding.left} y1={yl.y} x2={width - padding.right} y2={yl.y} stroke={colors.borderLight} strokeWidth={1} />)}
        {yLabels.map((yl, i) => <text key={`yl-${i}`} x={padding.left - 4} y={yl.y + 4} textAnchor="end" fontSize={10} fill={colors.text.tertiary}>{yl.label}</text>)}
        {xLabels.map((xl, i) => <text key={`xl-${i}`} x={scaleX(xl.idx)} y={height - 4} textAnchor="middle" fontSize={9} fill={colors.text.tertiary}>{formatXDate(xl.date)}</text>)}

        {/* Min/max bands */}
        {showBands && (
          <>
            <polyline points={maxBandPoints} fill="none" stroke={colors.text.tertiary} strokeWidth={0.5} strokeDasharray="3,3" opacity={0.4} />
            <polyline points={minBandPoints} fill="none" stroke={colors.text.tertiary} strokeWidth={0.5} strokeDasharray="3,3" opacity={0.4} />
          </>
        )}

        {/* Average line */}
        {showAvgLine && data.length > 1 && (
          <>
            <line x1={padding.left} y1={scaleY(avgValue)} x2={width - padding.right} y2={scaleY(avgValue)}
              stroke={color} strokeWidth={1} strokeDasharray="6,4" opacity={0.4} />
            <text x={width - padding.right} y={scaleY(avgValue) - 4} textAnchor="end" fontSize={9} fill={color} opacity={0.6}>
              {formatValue(avgValue)}
            </text>
          </>
        )}

        {/* Trend line */}
        {trendLine && data.length > 1 && (
          <line
            x1={scaleX(0)} y1={scaleY(trendLine.intercept)}
            x2={scaleX(data.length - 1)} y2={scaleY(trendLine.slope * (data.length - 1) + trendLine.intercept)}
            stroke={colors.accent.orange} strokeWidth={1.5} strokeDasharray="8,4" opacity={0.6}
          />
        )}

        {/* Main line */}
        <polyline points={mainPoints} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />

        {/* Min/max callouts */}
        {showMinMaxCallouts && data.length > 2 && minIdx !== maxIdx && (
          <>
            <circle cx={scaleX(maxIdx)} cy={scaleY(data[maxIdx].value)} r={3} fill={colors.accent.orange} />
            <text x={scaleX(maxIdx)} y={scaleY(data[maxIdx].value) - 8} textAnchor="middle" fontSize={9} fontWeight={600} fill={colors.accent.orange}>
              {formatValue(data[maxIdx].value)}
            </text>
            <circle cx={scaleX(minIdx)} cy={scaleY(data[minIdx].value)} r={3} fill={colors.accent.blue} />
            <text x={scaleX(minIdx)} y={scaleY(data[minIdx].value) + 14} textAnchor="middle" fontSize={9} fontWeight={600} fill={colors.accent.blue}>
              {formatValue(data[minIdx].value)}
            </text>
          </>
        )}

        {/* Interactive callout */}
        {showInteractiveCallout && hoverIdx !== null && (
          <>
            <line x1={scaleX(hoverIdx)} y1={padding.top} x2={scaleX(hoverIdx)} y2={padding.top + chartH}
              stroke={color} strokeWidth={1} strokeDasharray="4,2" opacity={0.6} />
            <circle cx={scaleX(hoverIdx)} cy={scaleY(data[hoverIdx].value)} r={4}
              fill={color} stroke="#fff" strokeWidth={2} />
            <rect
              x={Math.min(Math.max(scaleX(hoverIdx) - 48, 2), width - 98)}
              y={Math.max(scaleY(data[hoverIdx].value) - 38, 2)}
              width={96} height={28} rx={4}
              fill={colors.dark} opacity={0.9}
            />
            <text
              x={Math.min(Math.max(scaleX(hoverIdx), 50), width - 50)}
              y={Math.max(scaleY(data[hoverIdx].value) - 20, 16)}
              textAnchor="middle" fontSize={10} fontWeight={600} fill="#fff">
              {formatValue(data[hoverIdx].value)}
            </text>
            <text
              x={Math.min(Math.max(scaleX(hoverIdx), 50), width - 50)}
              y={Math.max(scaleY(data[hoverIdx].value) - 8, 28)}
              textAnchor="middle" fontSize={8} fill="#ccc">
              {formatDateShort(data[hoverIdx].date)}
            </text>
          </>
        )}
      </svg>

      {/* Legend */}
      {legendItems.length > 0 && (
        <div style={{ display: 'flex', gap: spacing.md, flexWrap: 'wrap', justifyContent: 'center', marginTop: 4 }}>
          {legendItems.map(item => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {item.dashed ? (
                <svg width={16} height={8}><line x1={0} y1={4} x2={16} y2={4} stroke={item.color} strokeWidth={1.5} strokeDasharray="4,2" /></svg>
              ) : (
                <div style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: item.color }} />
              )}
              <span style={{ fontSize: fs.xs - 1, color: colors.text.tertiary }}>{item.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
