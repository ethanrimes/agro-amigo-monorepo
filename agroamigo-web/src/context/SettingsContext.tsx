'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';

export type MarketLevel = 'nacional' | 'departamento' | 'ciudad' | 'mercado';

export interface DefaultMarket {
  level: MarketLevel;
  id?: string;
  name: string;
}

export interface AppSettings {
  defaultMarket: DefaultMarket;
  fontSizeScale: number;
}

const DEFAULT_SETTINGS: AppSettings = {
  defaultMarket: { level: 'nacional', name: 'Promedio nacional' },
  fontSizeScale: 1,
};

const STORAGE_KEY = 'agroamigo_settings';

interface SettingsContextValue {
  settings: AppSettings;
  updateDefaultMarket: (market: DefaultMarket) => void;
  updateFontSizeScale: (scale: number) => void;
  ready: boolean;
}

const SettingsContext = createContext<SettingsContextValue>({
  settings: DEFAULT_SETTINGS,
  updateDefaultMarket: () => {},
  updateFontSizeScale: () => {},
  ready: false,
});

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        setSettings({ ...DEFAULT_SETTINGS, ...parsed });
      }
    } catch {}
    setReady(true);
  }, []);

  const persist = useCallback((next: AppSettings) => {
    setSettings(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {}
  }, []);

  const updateDefaultMarket = useCallback((market: DefaultMarket) => {
    persist({ ...settings, defaultMarket: market });
  }, [settings, persist]);

  const updateFontSizeScale = useCallback((scale: number) => {
    persist({ ...settings, fontSizeScale: scale });
  }, [settings, persist]);

  return (
    <SettingsContext.Provider value={{ settings, updateDefaultMarket, updateFontSizeScale, ready }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  return useContext(SettingsContext);
}
