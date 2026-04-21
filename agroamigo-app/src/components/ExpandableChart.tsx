import React, { useCallback, useState } from 'react';
import { View, Text, Pressable, StyleSheet, LayoutAnimation, Platform, UIManager, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../theme';
import { useCachedQuery } from '../lib/useCachedQuery';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

interface ExpandableChartProps<T> {
  title: string;
  subtitle?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  badge?: string | number;
  cacheKey: string;
  fetcher: () => Promise<T>;
  ttlMs?: number;
  initiallyExpanded?: boolean;
  /** Rendered once data arrives. Receives the fetched value. */
  render: (data: T) => React.ReactNode;
  /** Rendered while the fetch is in flight. */
  loadingView?: React.ReactNode;
  /** Rendered when the fetch throws. */
  errorView?: (err: unknown) => React.ReactNode;
  /**
   * Optional hook to let the parent read the fetched data (for cross-section
   * derived state). Called whenever data changes.
   */
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

  React.useEffect(() => {
    if (data !== undefined && onData) onData(data);
  }, [data, onData]);

  const toggle = useCallback(() => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpanded((v) => !v);
  }, []);

  return (
    <View style={styles.container}>
      <Pressable style={styles.header} onPress={toggle}>
        {icon && <Ionicons name={icon} size={16} color={colors.text.secondary} />}
        <View style={styles.titleCol}>
          <Text style={styles.title}>{title}</Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
        </View>
        {badge != null && (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{badge}</Text>
          </View>
        )}
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={18}
          color={colors.text.tertiary}
        />
      </Pressable>
      {expanded && (
        <View style={styles.content}>
          {loading && data === undefined && (
            loadingView ?? <ActivityIndicator color={colors.primary} style={{ paddingVertical: spacing.md }} />
          )}
          {error != null && !loading && (
            errorView ? errorView(error) : (
              <Text style={styles.error}>Error: {String((error as Error)?.message ?? error)}</Text>
            )
          )}
          {data !== undefined && render(data)}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
  },
  titleCol: {
    flex: 1,
    gap: 1,
  },
  title: {
    fontSize: fontSize.md,
    fontWeight: '700',
    color: colors.text.primary,
  },
  subtitle: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  badge: {
    backgroundColor: colors.primary + '20',
    borderRadius: borderRadius.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  badgeText: {
    fontSize: fontSize.xs,
    fontWeight: '600',
    color: colors.primary,
  },
  content: {
    marginTop: spacing.xs,
  },
  error: {
    fontSize: fontSize.sm,
    color: '#c0392b',
    paddingVertical: spacing.sm,
  },
});
