import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { colors } from '../src/theme';

export default function RootLayout() {
  return (
    <>
      <StatusBar style="light" backgroundColor={colors.dark} />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.dark },
          headerTintColor: colors.text.inverse,
          headerTitleStyle: { fontWeight: '700' },
          contentStyle: { backgroundColor: colors.background },
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="product/[id]"
          options={{ title: 'Producto', headerBackTitle: 'Atrás' }}
        />
        <Stack.Screen
          name="market/[id]"
          options={{ title: 'Mercado', headerBackTitle: 'Atrás' }}
        />
        <Stack.Screen
          name="insumo/[id]"
          options={{ title: 'Insumo', headerBackTitle: 'Atrás' }}
        />
      </Stack>
    </>
  );
}
