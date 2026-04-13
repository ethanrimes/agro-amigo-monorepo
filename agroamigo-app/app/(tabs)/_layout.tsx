import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, fontSize } from '../../src/theme';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.dark },
        headerTintColor: colors.text.inverse,
        headerTitleStyle: { fontWeight: '700', fontSize: fontSize.lg },
        tabBarStyle: {
          backgroundColor: colors.dark,
          borderTopColor: colors.darkSurface,
          height: 60,
          paddingBottom: 6,
          paddingTop: 4,
        },
        tabBarActiveTintColor: colors.primaryLight,
        tabBarInactiveTintColor: colors.text.tertiary,
        tabBarLabelStyle: {
          fontSize: fontSize.xs,
          fontWeight: '600',
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Inicio',
          headerTitle: 'AgroAmigo',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="home" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="products"
        options={{
          title: 'Productos',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="leaf" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="markets"
        options={{
          title: 'Mercados',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="storefront" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="insumos"
        options={{
          title: 'Insumos',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="flask" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="map"
        options={{
          title: 'Mapa',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="map" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}
