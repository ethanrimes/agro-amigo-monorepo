import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';

// Mapbox requires a native build with an access token.
// For the Expo Go dev flow, we show a placeholder with planned functionality.
// In production, this will use @rnmapbox/maps with a Mapbox token.

export default function MapScreen() {
  const [mode, setMode] = useState<'price' | 'supply'>('price');

  return (
    <View style={styles.container}>
      {/* Map placeholder */}
      <View style={styles.mapPlaceholder}>
        <Ionicons name="map" size={64} color={colors.primary + '40'} />
        <Text style={styles.placeholderTitle}>Mapa de Colombia</Text>
        <Text style={styles.placeholderSubtitle}>
          El mapa interactivo con Mapbox estará disponible{'\n'}en la versión nativa (development build)
        </Text>
      </View>

      {/* Control panel overlay */}
      <View style={styles.controlPanel}>
        <View style={styles.modeSelector}>
          <Pressable
            style={[styles.modeButton, mode === 'price' && styles.modeButtonActive]}
            onPress={() => setMode('price')}
          >
            <Ionicons
              name="cash"
              size={16}
              color={mode === 'price' ? colors.text.inverse : colors.text.secondary}
            />
            <Text style={[styles.modeText, mode === 'price' && styles.modeTextActive]}>
              Precios
            </Text>
          </Pressable>
          <Pressable
            style={[styles.modeButton, mode === 'supply' && styles.modeButtonActive]}
            onPress={() => setMode('supply')}
          >
            <Ionicons
              name="trending-up"
              size={16}
              color={mode === 'supply' ? colors.text.inverse : colors.text.secondary}
            />
            <Text style={[styles.modeText, mode === 'supply' && styles.modeTextActive]}>
              Abastecimiento
            </Text>
          </Pressable>
        </View>

        <Text style={styles.controlLabel}>
          {mode === 'price'
            ? 'Precios por departamento/mercado'
            : 'Flujos de abastecimiento'
          }
        </Text>
      </View>

      {/* Legend */}
      <View style={styles.legend}>
        <View style={styles.legendRow}>
          {mode === 'price' ? (
            <>
              <View style={[styles.legendDot, { backgroundColor: '#4CAF50' }]} />
              <Text style={styles.legendText}>Bajo</Text>
              <View style={[styles.legendDot, { backgroundColor: '#FFC107' }]} />
              <Text style={styles.legendText}>Medio</Text>
              <View style={[styles.legendDot, { backgroundColor: '#F44336' }]} />
              <Text style={styles.legendText}>Alto</Text>
            </>
          ) : (
            <>
              <View style={[styles.legendDot, { backgroundColor: colors.accent.blue }]} />
              <Text style={styles.legendText}>Bajo volumen</Text>
              <View style={[styles.legendDot, { backgroundColor: colors.primary }]} />
              <Text style={styles.legendText}>Alto volumen</Text>
            </>
          )}
        </View>
        <Text style={styles.legendSource}>Fuente: SIPSA-DANE</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  mapPlaceholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.md,
  },
  placeholderTitle: {
    fontSize: fontSize.xl,
    fontWeight: '700',
    color: colors.text.primary,
  },
  placeholderSubtitle: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
    textAlign: 'center',
    lineHeight: 20,
  },
  controlPanel: {
    position: 'absolute',
    top: spacing.md,
    left: spacing.md,
    right: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.md,
    shadowColor: colors.dark,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 5,
    gap: spacing.sm,
  },
  modeSelector: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  modeButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    backgroundColor: colors.borderLight,
  },
  modeButtonActive: {
    backgroundColor: colors.primary,
  },
  modeText: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    color: colors.text.secondary,
  },
  modeTextActive: {
    color: colors.text.inverse,
  },
  controlLabel: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
    textAlign: 'center',
  },
  legend: {
    position: 'absolute',
    bottom: spacing.lg,
    left: spacing.md,
    right: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.md,
    shadowColor: colors.dark,
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 5,
    gap: spacing.xs,
  },
  legendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    justifyContent: 'center',
  },
  legendDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  legendText: {
    fontSize: fontSize.xs,
    color: colors.text.secondary,
  },
  legendSource: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
    textAlign: 'center',
  },
});
