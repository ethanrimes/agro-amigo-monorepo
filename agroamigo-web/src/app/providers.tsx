'use client';

import React from 'react';
import '@/lib/supabase-init'; // side-effect: initializes shared supabase client
import { SettingsProvider } from '@/context/SettingsContext';
import { WatchlistProvider } from '@/context/WatchlistContext';
import { LanguageProvider } from '@/context/LanguageContext';
import { AuthProvider } from '@/context/AuthContext';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <LanguageProvider>
      <SettingsProvider>
        <AuthProvider>
          <WatchlistProvider>
            {children}
          </WatchlistProvider>
        </AuthProvider>
      </SettingsProvider>
    </LanguageProvider>
  );
}
