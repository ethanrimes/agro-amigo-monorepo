import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { colors } from '../src/theme';
import { SettingsProvider } from '../src/context/SettingsContext';
import { WatchlistProvider } from '../src/context/WatchlistContext';
import { AuthProvider } from '../src/context/AuthContext';

export default function RootLayout() {
  return (
    <SettingsProvider>
    <AuthProvider>
    <WatchlistProvider>
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
        <Stack.Screen name="product/[id]" options={{ headerBackTitle: '' }} />
        <Stack.Screen name="market/[id]" options={{ headerBackTitle: '' }} />
        <Stack.Screen name="insumo/[id]" options={{ headerBackTitle: '' }} />
        <Stack.Screen name="settings" options={{ headerBackTitle: '' }} />
        <Stack.Screen name="auth" options={{ headerBackTitle: '' }} />
      </Stack>
    </WatchlistProvider>
    </AuthProvider>
    </SettingsProvider>
  );
}
