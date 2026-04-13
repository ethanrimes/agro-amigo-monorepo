import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, fontSize, spacing } from '../theme';

interface Props {
  title: string;
  onSeeAll?: () => void;
}

export function SectionHeader({ title, onSeeAll }: Props) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>{title}</Text>
      {onSeeAll && (
        <Pressable onPress={onSeeAll} style={styles.seeAll}>
          <Text style={styles.seeAllText}>Ver todo</Text>
          <Ionicons name="chevron-forward" size={14} color={colors.primary} />
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  title: {
    fontSize: fontSize.lg,
    fontWeight: '700',
    color: colors.text.primary,
  },
  seeAll: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  seeAllText: {
    fontSize: fontSize.sm,
    color: colors.primary,
    fontWeight: '600',
  },
});
