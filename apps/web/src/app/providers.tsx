"use client";
import { PreferencesProvider } from "@/components/marketplace/Preferences";
import { FarmProvider } from "@/components/planning/FarmContext";
export function Providers({ children }: { children: React.ReactNode }) {
  return <PreferencesProvider><FarmProvider>{children}</FarmProvider></PreferencesProvider>;
}
