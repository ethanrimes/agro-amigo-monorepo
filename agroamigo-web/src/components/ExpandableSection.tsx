'use client';

import React, { useState } from 'react';
import { IoChevronUp, IoChevronDown } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize } from '@agroamigo/shared';

interface ExpandableSectionProps {
  title: string;
  subtitle?: string;
  initiallyExpanded?: boolean;
  children: React.ReactNode;
  icon?: React.ReactNode;
  badge?: string | number;
}

export function ExpandableSection({
  title,
  subtitle,
  initiallyExpanded = false,
  children,
  icon,
  badge,
}: ExpandableSectionProps) {
  const [expanded, setExpanded] = useState(initiallyExpanded);

  return (
    <div style={{ overflow: 'hidden' }}>
      <button
        onClick={() => setExpanded(!expanded)}
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
      {expanded && <div style={{ marginTop: spacing.xs }}>{children}</div>}
    </div>
  );
}
