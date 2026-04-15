'use client';

import React from 'react';
import '@/lib/supabase-init'; // side-effect: initializes shared supabase client
import { SettingsProvider } from '@/context/SettingsContext';
import { WatchlistProvider } from '@/context/WatchlistContext';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SettingsProvider>
      <WatchlistProvider>
        {children}
      </WatchlistProvider>
    </SettingsProvider>
  );
}
