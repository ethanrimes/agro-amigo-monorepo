'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { IoChevronUp, IoChevronDown } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, useCachedQuery } from '@agroamigo/shared';

interface ExpandableChartProps<T> {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  badge?: string | number;
  cacheKey: string;
  fetcher: () => Promise<T>;
  ttlMs?: number;
  initiallyExpanded?: boolean;
  render: (data: T) => React.ReactNode;
  loadingView?: React.ReactNode;
  errorView?: (err: unknown) => React.ReactNode;
  onData?: (data: T) => void;
}

export function ExpandableChart<T>({
  title,
  subtitle,
  icon,
  badge,
  cacheKey,
  fetcher,
  ttlMs,
  initiallyExpanded = false,
  render,
  loadingView,
  errorView,
  onData,
}: ExpandableChartProps<T>) {
  const [expanded, setExpanded] = useState(initiallyExpanded);
  const { data, loading, error } = useCachedQuery<T>(cacheKey, fetcher, { enabled: expanded, ttlMs });

  useEffect(() => {
    if (data !== undefined && onData) onData(data);
  }, [data, onData]);

  const toggle = useCallback(() => setExpanded((v) => !v), []);

  return (
    <div style={{ overflow: 'hidden' }}>
      <button
        onClick={toggle}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: spacing.sm,
          padding: `${spacing.sm}px 0`,
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          width: '100%',
          textAlign: 'left',
        }}
      >
        {icon}
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.text.primary }}>{title}</div>
          {subtitle && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{subtitle}</div>}
        </div>
        {badge != null && (
          <span style={{
            backgroundColor: colors.primary + '20',
            borderRadius: borderRadius.full,
            padding: `2px ${spacing.sm}px`,
            fontSize: fontSize.xs,
            fontWeight: 600,
            color: colors.primary,
          }}>
            {badge}
          </span>
        )}
        {expanded ? (
          <IoChevronUp size={18} color={colors.text.tertiary} />
        ) : (
          <IoChevronDown size={18} color={colors.text.tertiary} />
        )}
      </button>
      {expanded && (
        <div style={{ marginTop: spacing.xs }}>
          {loading && data === undefined && (
            loadingView ?? (
              <div style={{ padding: `${spacing.md}px 0`, fontSize: fontSize.sm, color: colors.text.tertiary }}>
                Cargando…
              </div>
            )
          )}
          {error != null && !loading && (
            errorView ? errorView(error) : (
              <div style={{ padding: `${spacing.sm}px 0`, fontSize: fontSize.sm, color: '#c0392b' }}>
                Error: {String((error as Error)?.message ?? error)}
              </div>
            )
          )}
          {data !== undefined && render(data)}
        </div>
      )}
    </div>
  );
}
