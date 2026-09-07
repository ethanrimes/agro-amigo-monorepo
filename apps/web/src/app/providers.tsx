"use client";
import { PreferencesProvider } from "@/components/marketplace/Preferences";
import { FarmProvider } from "@/components/planning/FarmContext";
import { EvidenceProvider } from "@/components/planning/EvidenceProvider";
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <PreferencesProvider>
      <FarmProvider>
        <EvidenceProvider>{children}</EvidenceProvider>
      </FarmProvider>
    </PreferencesProvider>
  );
}
