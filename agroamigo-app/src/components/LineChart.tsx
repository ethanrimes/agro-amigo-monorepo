import React, { useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import Svg, { Line, Polyline, Circle, Rect, Text as SvgText } from 'react-native-svg';
import { GestureResponderEvent } from 'react-native';
import { useSettings } from '../context/SettingsContext';
import { useTranslation } from '../lib/useTranslation';
import { formatCOPCompact, formatDateShort } from '../lib/format';
import { colors, spacing, fontSize as fs } from '../theme';

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
  // When set, the chart renders with at least `minPointSpacing` pixels per
  // data point. If that exceeds `width`, the chart grows beyond `width` and
  // is wrapped in a horizontal ScrollView so the user can pan it.
  minPointSpacing?: number;
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

export function LineChart({ data, width, height, color = colors.primary, showBands = false, formatValue = formatCOPCompact, minPointSpacing }: LineChartProps) {
  const { settings } = useSettings();
  const t = useTranslation();
  const { showAvgLine, showTrendLine, showMinMaxCallouts, showInteractiveCallout } = settings.chart;
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  // Clear stale hover index when the data set shrinks (e.g. user applied a
  // filter while hovering). Otherwise `data[hoverIdx]` is undefined below.
  React.useEffect(() => {
    if (hoverIdx !== null && hoverIdx >= data.length) setHoverIdx(null);
  }, [data.length, hoverIdx]);

  // Expand internal render width when there are many points so the user can
  // scroll horizontally instead of having points collapse on top of each
  // other.
  const renderW = minPointSpacing && data.length > 1
    ? Math.max(width, Math.ceil(data.length * minPointSpacing))
    : width;
  const scrolls = renderW > width;

  const padding = { top: 10, right: 10, bottom: 30, left: 50 };
  const chartW = renderW - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const allValues = data.flatMap(d => [d.min ?? d.value, d.max ?? d.value, d.value].filter(v => v != null));
  const minY = Math.min(...allValues) * 0.95;
  const maxY = Math.max(...allValues) * 1.05;
  const rangeY = maxY - minY || 1;

  // Time-proportional x-axis. Right edge extends to TODAY (not the last
  // observation) so any gap between the most recent data point and the
  // current date is visible — the line itself just ends at the last point,
  // which visually communicates "no data since then".
  const timestamps = data.map(d => new Date(d.date + 'T00:00:00').getTime());
  const todayT = new Date(new Date().toISOString().split('T')[0] + 'T00:00:00').getTime();
  const minT = timestamps.length > 0 ? timestamps[0] : 0;
  const lastT = timestamps.length > 0 ? timestamps[timestamps.length - 1] : 1;
  const maxT = Math.max(lastT, todayT);
  const rangeT = maxT - minT || 1;

  const scaleT = (t: number) => padding.left + ((t - minT) / rangeT) * chartW;
  const scaleX = (i: number) => scaleT(timestamps[i]);
  const scaleY = (v: number) => padding.top + (1 - (v - minY) / rangeY) * chartH;

  const mainPoints = data.map((d, i) => `${scaleX(i)},${scaleY(d.value)}`).join(' ');

  const yLabels = [minY, (minY + maxY) / 2, maxY].map(v => ({ y: scaleY(v), label: formatValue(v) }));

  // X-axis labels — evenly spaced in calendar time across [minT, maxT].
  // No longer snapped to data indices so when the last observation lags
  // today the rightmost label still reads "today" (not the stale max).
  const currentYear = new Date().getFullYear();
  const NUM_X_LABELS = 5;
  const xLabels: { t: number; date: string }[] = [];
  if (data.length > 0) {
    for (let n = 0; n < NUM_X_LABELS; n++) {
      const t = minT + (n / (NUM_X_LABELS - 1)) * rangeT;
      const iso = new Date(t).toISOString().split('T')[0];
      xLabels.push({ t, date: iso });
    }
  }
  // If the chart spans more than one year, annotate every label with its
  // year so the axis isn't ambiguous — e.g. Apr '24 vs Apr '25. Uses the
  // full rendered x-axis (which extends to today), not just the data span.
  const minYear = new Date(minT).getFullYear();
  const maxYear = new Date(maxT).getFullYear();
  const spansYears = minYear !== maxYear;
  function formatXDate(dateStr: string): string {
    const label = formatDateShort(dateStr);
    const year = new Date(dateStr + 'T00:00:00').getFullYear();
    if (spansYears) return `${label} '${String(year).slice(2)}`;
    return year < currentYear ? `${label} '${String(year).slice(2)}` : label;
  }

  const avgValue = data.length > 0 ? data.reduce((s, d) => s + d.value, 0) / data.length : 0;
  const trendLine = showTrendLine ? linearRegression(data.map((d, i) => ({ x: i, y: d.value }))) : null;

  let minIdx = 0, maxIdx = 0;
  if (showMinMaxCallouts && data.length > 0) {
    for (let i = 1; i < data.length; i++) {
      if (data[i].value < data[minIdx].value) minIdx = i;
      if (data[i].value > data[maxIdx].value) maxIdx = i;
    }
  }

  const minBandPoints = showBands ? data.map((d, i) => `${scaleX(i)},${scaleY(d.min ?? d.value)}`).join(' ') : '';
  const maxBandPoints = showBands ? data.map((d, i) => `${scaleX(i)},${scaleY(d.max ?? d.value)}`).join(' ') : '';

  const handleTouch = useCallback((e: GestureResponderEvent) => {
    if (!showInteractiveCallout) return;
    const x = e.nativeEvent.locationX;
    const targetT = minT + ((x - padding.left) / chartW) * rangeT;
    let bestIdx = 0, bestDist = Infinity;
    for (let i = 0; i < timestamps.length; i++) {
      const dist = Math.abs(timestamps[i] - targetT);
      if (dist < bestDist) { bestDist = dist; bestIdx = i; }
    }
    setHoverIdx(bestIdx);
  }, [showInteractiveCallout, chartW, padding.left, minT, rangeT, timestamps]);

  const legendItems: { color: string; label: string; dashed?: boolean }[] = [];
  if (showAvgLine && data.length > 1) legendItems.push({ color, label: t.settings_chart_avg_line, dashed: true });
  if (showTrendLine && trendLine) legendItems.push({ color: colors.accent.orange, label: t.settings_chart_trend_line, dashed: true });
  if (showMinMaxCallouts && data.length > 2 && minIdx !== maxIdx) {
    legendItems.push({ color: colors.accent.orange, label: t.product_max });
    legendItems.push({ color: colors.accent.blue, label: t.product_min });
  }

  const chartBody = (
    <>
      <Svg width={renderW} height={height}
        onStartShouldSetResponder={() => showInteractiveCallout}
        onMoveShouldSetResponder={() => showInteractiveCallout}
        onResponderMove={handleTouch}
        onResponderRelease={() => setHoverIdx(null)}>

        {yLabels.map((yl, i) => <Line key={i} x1={padding.left} y1={yl.y} x2={renderW - padding.right} y2={yl.y} stroke={colors.borderLight} strokeWidth={1} />)}
        {yLabels.map((yl, i) => <SvgText key={`yl-${i}`} x={padding.left - 4} y={yl.y + 4} textAnchor="end" fontSize={10} fill={colors.text.tertiary}>{yl.label}</SvgText>)}
        {xLabels.map((xl, i) => <SvgText key={`xl-${i}`} x={scaleT(xl.t)} y={height - 4} textAnchor="middle" fontSize={9} fill={colors.text.tertiary}>{formatXDate(xl.date)}</SvgText>)}

        {showBands && (
          <>
            <Polyline points={maxBandPoints} fill="none" stroke={colors.text.tertiary} strokeWidth={0.5} strokeDasharray="3,3" opacity={0.4} />
            <Polyline points={minBandPoints} fill="none" stroke={colors.text.tertiary} strokeWidth={0.5} strokeDasharray="3,3" opacity={0.4} />
          </>
        )}

        {showAvgLine && data.length > 1 && (
          <>
            <Line x1={padding.left} y1={scaleY(avgValue)} x2={renderW - padding.right} y2={scaleY(avgValue)} stroke={color} strokeWidth={1} strokeDasharray="6,4" opacity={0.4} />
            <SvgText x={renderW - padding.right} y={scaleY(avgValue) - 4} textAnchor="end" fontSize={9} fill={color} opacity={0.6}>{formatValue(avgValue)}</SvgText>
          </>
        )}

        {trendLine && data.length > 1 && (
          <Line x1={scaleX(0)} y1={scaleY(trendLine.intercept)} x2={scaleX(data.length - 1)} y2={scaleY(trendLine.slope * (data.length - 1) + trendLine.intercept)} stroke={colors.accent.orange} strokeWidth={1.5} strokeDasharray="8,4" opacity={0.6} />
        )}

        <Polyline points={mainPoints} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />

        {showMinMaxCallouts && data.length > 2 && minIdx !== maxIdx && (
          <>
            <Circle cx={scaleX(maxIdx)} cy={scaleY(data[maxIdx].value)} r={3} fill={colors.accent.orange} />
            <SvgText x={scaleX(maxIdx)} y={scaleY(data[maxIdx].value) - 8} textAnchor="middle" fontSize={9} fontWeight="600" fill={colors.accent.orange}>{formatValue(data[maxIdx].value)}</SvgText>
            <Circle cx={scaleX(minIdx)} cy={scaleY(data[minIdx].value)} r={3} fill={colors.accent.blue} />
            <SvgText x={scaleX(minIdx)} y={scaleY(data[minIdx].value) + 14} textAnchor="middle" fontSize={9} fontWeight="600" fill={colors.accent.blue}>{formatValue(data[minIdx].value)}</SvgText>
          </>
        )}

        {showInteractiveCallout && hoverIdx !== null && data[hoverIdx] && (
          <>
            <Line x1={scaleX(hoverIdx)} y1={padding.top} x2={scaleX(hoverIdx)} y2={padding.top + chartH} stroke={color} strokeWidth={1} strokeDasharray="4,2" opacity={0.6} />
            <Circle cx={scaleX(hoverIdx)} cy={scaleY(data[hoverIdx].value)} r={4} fill={color} stroke="#fff" strokeWidth={2} />
            <Rect x={Math.min(Math.max(scaleX(hoverIdx) - 48, 2), renderW - 98)} y={Math.max(scaleY(data[hoverIdx].value) - 38, 2)} width={96} height={28} rx={4} fill={colors.dark} opacity={0.9} />
            <SvgText x={Math.min(Math.max(scaleX(hoverIdx), 50), renderW - 50)} y={Math.max(scaleY(data[hoverIdx].value) - 20, 16)} textAnchor="middle" fontSize={10} fontWeight="600" fill="#fff">{formatValue(data[hoverIdx].value)}</SvgText>
            <SvgText x={Math.min(Math.max(scaleX(hoverIdx), 50), renderW - 50)} y={Math.max(scaleY(data[hoverIdx].value) - 8, 28)} textAnchor="middle" fontSize={8} fill="#ccc">{formatDateShort(data[hoverIdx].date)}</SvgText>
          </>
        )}
      </Svg>
    </>
  );

  const legend = legendItems.length > 0 && (
    <View style={{ flexDirection: 'row', gap: spacing.md, flexWrap: 'wrap', justifyContent: 'center', marginTop: 4 }}>
      {legendItems.map(item => (
        <View key={item.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          {item.dashed ? (
            <Svg width={16} height={8}><Line x1={0} y1={4} x2={16} y2={4} stroke={item.color} strokeWidth={1.5} strokeDasharray="4,2" /></Svg>
          ) : (
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: item.color }} />
          )}
          <Text style={{ fontSize: fs.xs - 1, color: colors.text.tertiary }}>{item.label}</Text>
        </View>
      ))}
    </View>
  );

  if (scrolls) {
    return (
      <View style={{ width, alignSelf: 'center' }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={true} contentContainerStyle={{ alignItems: 'center' }}>
          {chartBody}
        </ScrollView>
        {legend}
      </View>
    );
  }
  return (
    <View style={{ alignItems: 'center' }}>
      {chartBody}
      {legend}
    </View>
  );
}
