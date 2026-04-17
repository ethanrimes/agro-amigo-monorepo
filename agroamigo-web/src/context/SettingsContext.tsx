'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';

export type MarketLevel = 'nacional' | 'departamento' | 'ciudad' | 'mercado';

export interface DefaultMarket {
  level: MarketLevel;
  id?: string;
  name: string;
}

export interface ChartSettings {
  showAvgLine: boolean;
  showTrendLine: boolean;
  showMinMaxCallouts: boolean;
  showInteractiveCallout: boolean;
}

export interface AppSettings {
  defaultMarket: DefaultMarket;
  fontSizeScale: number;
  chart: ChartSettings;
  commentsEnabled: boolean;
}

const DEFAULT_SETTINGS: AppSettings = {
  defaultMarket: { level: 'nacional', name: 'Promedio nacional' },
  fontSizeScale: 1,
  chart: {
    showAvgLine: true,
    showTrendLine: false,
    showMinMaxCallouts: true,
    showInteractiveCallout: true,
  },
  commentsEnabled: true,
};

const STORAGE_KEY = 'agroamigo_settings';

interface SettingsContextValue {
  settings: AppSettings;
  updateDefaultMarket: (market: DefaultMarket) => void;
  updateFontSizeScale: (scale: number) => void;
  updateChartSettings: (chart: Partial<ChartSettings>) => void;
  updateCommentsEnabled: (enabled: boolean) => void;
  ready: boolean;
}

const SettingsContext = createContext<SettingsContextValue>({
  settings: DEFAULT_SETTINGS,
  updateDefaultMarket: () => {},
  updateFontSizeScale: () => {},
  updateChartSettings: () => {},
  updateCommentsEnabled: () => {},
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
        setSettings({
          ...DEFAULT_SETTINGS,
          ...parsed,
          chart: { ...DEFAULT_SETTINGS.chart, ...parsed.chart },
        });
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

  const updateChartSettings = useCallback((partial: Partial<ChartSettings>) => {
    persist({ ...settings, chart: { ...settings.chart, ...partial } });
  }, [settings, persist]);

  const updateCommentsEnabled = useCallback((enabled: boolean) => {
    persist({ ...settings, commentsEnabled: enabled });
  }, [settings, persist]);

  return (
    <SettingsContext.Provider value={{ settings, updateDefaultMarket, updateFontSizeScale, updateChartSettings, updateCommentsEnabled, ready }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  return useContext(SettingsContext);
}
