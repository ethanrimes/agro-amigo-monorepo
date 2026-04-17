import { useMemo } from 'react';
import { useSettings } from '../context/SettingsContext';
import { getTranslations, type Translations } from '../translations';

export function useTranslation(): Translations {
  const { settings } = useSettings();
  return useMemo(() => getTranslations(settings.locale), [settings.locale]);
}
