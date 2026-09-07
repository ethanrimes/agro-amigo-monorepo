"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
type Preferences = {
  region: string;
  setRegion: (region: string) => void;
  saved: string[];
  toggleSaved: (id: string) => void;
  ready: boolean;
};
const Context = createContext<Preferences | null>(null);
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [region, setRegion] = useState("");
  const [saved, setSaved] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    try {
      const value = JSON.parse(
        localStorage.getItem("agroamigo-preferences-v2") || "{}",
      );
      if (typeof value.region === "string") setRegion(value.region);
      if (Array.isArray(value.saved))
        setSaved(value.saved.filter((x: unknown) => typeof x === "string"));
    } catch {}
    setReady(true);
  }, []);
  useEffect(() => {
    if (ready)
      try {
        localStorage.setItem(
          "agroamigo-preferences-v2",
          JSON.stringify({ region, saved }),
        );
      } catch {}
  }, [region, saved, ready]);
  return (
    <Context.Provider
      value={{
        region,
        setRegion,
        saved,
        toggleSaved: (id) =>
          setSaved((old) =>
            old.includes(id) ? old.filter((x) => x !== id) : [...old, id],
          ),
        ready,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function usePreferences() {
  const value = useContext(Context);
  if (!value) throw new Error("Preferences provider missing");
  return value;
}
