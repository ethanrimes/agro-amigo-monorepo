'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';

export type WatchlistItemType = 'product' | 'insumo';

export interface WatchlistItem {
  id: string;
  type: WatchlistItemType;
  name: string;
  addedAt: string;
}

interface WatchlistContextValue {
  items: WatchlistItem[];
  isWatched: (id: string) => boolean;
  toggle: (id: string, type: WatchlistItemType, name: string) => void;
  remove: (id: string) => void;
  ready: boolean;
}

const STORAGE_KEY = 'agroamigo_watchlist';

const WatchlistContext = createContext<WatchlistContextValue>({
  items: [],
  isWatched: () => false,
  toggle: () => {},
  remove: () => {},
  ready: false,
});

export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setItems(JSON.parse(raw));
    } catch {}
    setReady(true);
  }, []);

  const persist = useCallback((next: WatchlistItem[]) => {
    setItems(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {}
  }, []);

  const isWatched = useCallback((id: string) => {
    return items.some(i => i.id === id);
  }, [items]);

  const toggle = useCallback((id: string, type: WatchlistItemType, name: string) => {
    if (items.some(i => i.id === id)) {
      persist(items.filter(i => i.id !== id));
    } else {
      persist([...items, { id, type, name, addedAt: new Date().toISOString() }]);
    }
  }, [items, persist]);

  const remove = useCallback((id: string) => {
    persist(items.filter(i => i.id !== id));
  }, [items, persist]);

  return (
    <WatchlistContext.Provider value={{ items, isWatched, toggle, remove, ready }}>
      {children}
    </WatchlistContext.Provider>
  );
}

export function useWatchlist() {
  return useContext(WatchlistContext);
}
