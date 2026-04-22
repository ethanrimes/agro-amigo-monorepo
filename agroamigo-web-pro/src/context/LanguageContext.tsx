'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { type Locale, type Translations, getTranslations } from '@/translations';

const STORAGE_KEY = 'agroamigo_language';

interface LanguageContextValue {
  locale: Locale;
  t: Translations;
  setLocale: (locale: Locale) => void;
  ready: boolean;
}

const LanguageContext = createContext<LanguageContextValue>({
  locale: 'es',
  t: getTranslations('es'),
  setLocale: () => {},
  ready: false,
});

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>('es');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY) as Locale | null;
      if (saved === 'en' || saved === 'es') setLocaleState(saved);
    } catch {}
    setReady(true);
  }, []);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    try { localStorage.setItem(STORAGE_KEY, newLocale); } catch {}
    document.documentElement.lang = newLocale;
  }, []);

  const t = getTranslations(locale);

  return (
    <LanguageContext.Provider value={{ locale, t, setLocale, ready }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}
