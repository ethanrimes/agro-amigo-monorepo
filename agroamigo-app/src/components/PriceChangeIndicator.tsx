import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, fontSize } from '../theme';
import { formatPctChange } from '../lib/format';

interface Props {
  value: number | null | undefined;
  size?: 'sm' | 'md' | 'lg';
}

export function PriceChangeIndicator({ value, size = 'md' }: Props) {
  if (value == null) return null;

  const isUp = value > 0;
  const isNeutral = Math.abs(value) < 0.1;
  const color = isNeutral ? colors.price.neutral : isUp ? colors.price.up : colors.price.down;
  const icon = isNeutral ? 'remove' : isUp ? 'arrow-up' : 'arrow-down';
  const textSize = size === 'sm' ? fontSize.xs : size === 'lg' ? fontSize.lg : fontSize.sm;
  const iconSize = size === 'sm' ? 10 : size === 'lg' ? 18 : 14;

  return (
    <View style={[styles.container, { backgroundColor: color + '18' }]}>
      <Ionicons name={icon} size={iconSize} color={color} />
      <Text style={[styles.text, { color, fontSize: textSize }]}>
        {formatPctChange(value)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
    gap: 2,
  },
  text: {
    fontWeight: '600',
  },
});
