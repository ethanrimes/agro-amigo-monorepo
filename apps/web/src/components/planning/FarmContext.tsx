"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { FarmProfile } from "@/lib/planning-types";
export const EMPTY_FARM: FarmProfile = {
  municipalityId: "",
  name: "Mi finca",
  cropCode: "",
  variety: "",
  area: "1",
  stage: "planning",
  plantingDate: "",
  floweringDate: "",
  irrigation: false,
  latitude: "",
  longitude: "",
  elevation: "",
};
const Context = createContext<{
  farm: FarmProfile;
  save: (f: FarmProfile) => void;
  ready: boolean;
} | null>(null);
export function FarmProvider({ children }: { children: ReactNode }) {
  const [farm, setFarm] = useState<FarmProfile>(EMPTY_FARM),
    [ready, setReady] = useState(false);
  useEffect(() => {
    try {
      const r = JSON.parse(localStorage.getItem("agroamigo-farm-v1") || "null");
      if (r && typeof r.municipalityId === "string") {
        const safe = { ...EMPTY_FARM };
        for (const k of Object.keys(safe) as (keyof FarmProfile)[]) {
          if (k === "irrigation") safe.irrigation = r.irrigation === true;
          else if (typeof r[k] === "string") safe[k] = r[k].slice(0, 150);
        }
        setFarm(safe);
      }
    } catch {}
    setReady(true);
  }, []);
  const save = (f: FarmProfile) => {
    setFarm(f);
    try {
      localStorage.setItem("agroamigo-farm-v1", JSON.stringify(f));
    } catch {}
  };
  return (
    <Context.Provider value={{ farm, save, ready }}>
      {children}
    </Context.Provider>
  );
}
export function useFarm() {
  const v = useContext(Context);
  if (!v) throw new Error("Farm provider missing");
  return v;
}
