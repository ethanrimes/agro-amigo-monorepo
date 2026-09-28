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
    // A shared product link must keep its explicit geographic scope even when
    // this browser previously saved another department. Hydration runs after
    // child effects, so restoring localStorage unconditionally loses that URL.
    const query = new URLSearchParams(window.location.search);
    const explicitRegion = query.has("region");
    try {
      const value = JSON.parse(
        localStorage.getItem("agroamigo-preferences-v2") || "{}",
      );
      if (!explicitRegion && typeof value.region === "string")
        setRegion(value.region);
      if (Array.isArray(value.saved))
        setSaved(value.saved.filter((x: unknown) => typeof x === "string"));
    } catch {}
    if (explicitRegion) setRegion((query.get("region") || "").slice(0, 100));
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
