"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { FarmProfile } from "@/lib/planning-types";
import {
  FARM_STORAGE,
  EMPTY_PROFILE,
  safeProfile,
  newFarm,
  profileFor,
  allocatedArea,
  type FarmStore,
  type FarmRecord,
  type ManagedCrop,
} from "@/lib/farm-types";
export const EMPTY_FARM = EMPTY_PROFILE;
type ContextValue = {
  farm: FarmProfile;
  farms: FarmRecord[];
  activeFarm: FarmRecord | null;
  ready: boolean;
  storageError: string;
  save: (p: FarmProfile) => void;
  addFarm: (p: FarmProfile) => string;
  updateFarm: (id: string, p: FarmProfile) => void;
  selectFarm: (id: string) => void;
  selectCrop: (id: string) => void;
  saveCrop: (farmId: string, crop: ManagedCrop) => boolean;
  removeCrop: (farmId: string, id: string) => void;
  removeFarm: (id: string) => void;
};
const Context = createContext<ContextValue | null>(null);
export function FarmProvider({ children }: { children: ReactNode }) {
  const [store, setStore] = useState<FarmStore>({
      version: 2,
      farms: [],
      activeId: "",
    }),
    [ready, setReady] = useState(false),
    [storageError, setError] = useState("");
  useEffect(() => {
    try {
      const data = JSON.parse(localStorage.getItem(FARM_STORAGE) || "null");
      if (data?.version === 2 && Array.isArray(data.farms)) {
        const farms: FarmRecord[] = data.farms
          .filter(
            (f: FarmRecord) =>
              typeof f?.id === "string" && f.profile && Array.isArray(f.crops),
          )
          .map((f: FarmRecord) => ({
            ...f,
            profile: safeProfile(f.profile),
            crops: f.crops.filter(
              (c) => typeof c?.id === "string" && typeof c.area === "string",
            ),
          }));
        setStore({
          version: 2,
          farms,
          activeId: farms.some((f) => f.id === data.activeId)
            ? data.activeId
            : farms[0]?.id || "",
        });
      } else {
        const old = JSON.parse(
          localStorage.getItem("agroamigo-farm-v1") || "null",
        );
        if (old?.municipalityId) {
          const f = newFarm(safeProfile(old), "legacy-farm");
          const migrated: FarmStore = {
            version: 2,
            farms: [f],
            activeId: f.id,
          };
          setStore(migrated);
          localStorage.setItem(FARM_STORAGE, JSON.stringify(migrated));
        }
      }
    } catch {
      setError(
        "No pudimos leer los datos guardados. No se reemplazó la copia del dispositivo.",
      );
    }
    setReady(true);
  }, []);
  const persist = (next: FarmStore) => {
    setStore(next);
    try {
      localStorage.setItem(FARM_STORAGE, JSON.stringify(next));
      setError("");
    } catch {
      setError(
        "Los cambios están en esta sesión, pero no se pudieron guardar. Descarga una copia antes de cerrar.",
      );
    }
  };
  const activeFarm =
    store.farms.find((f) => f.id === store.activeId) || store.farms[0] || null;
  const updateFarm = (id: string, profile: FarmProfile) =>
    persist({
      ...store,
      farms: store.farms.map((f) =>
        f.id === id
          ? {
              ...f,
              profile,
              crops:
                f.profile.municipalityId === profile.municipalityId
                  ? f.crops
                  : f.crops.map((c) => ({ ...c, budget: undefined })),
            }
          : f,
      ),
    });
  const addFarm = (p: FarmProfile) => {
    const f = newFarm(p);
    persist({ ...store, farms: [...store.farms, f], activeId: f.id });
    return f.id;
  };
  const selectFarm = (id: string) => {
    if (store.farms.some((f) => f.id === id) && store.activeId !== id)
      persist({ ...store, activeId: id });
  };
  const save = (p: FarmProfile) => {
    if (activeFarm) updateFarm(activeFarm.id, p);
    else addFarm(p);
  };
  const saveCrop = (farmId: string, crop: ManagedCrop) => {
    const f = store.farms.find((f) => f.id === farmId);
    if (!f) return false;
    const crops = f.crops.some((c) => c.id === crop.id)
      ? f.crops.map((c) => (c.id === crop.id ? crop : c))
      : [...f.crops, crop];
    if (allocatedArea({ ...f, crops }) > +f.profile.area + 1e-8) return false;
    persist({
      ...store,
      farms: store.farms.map((r) =>
        r.id === farmId ? { ...r, crops, selectedCropId: crop.id } : r,
      ),
    });
    return true;
  };
  return (
    <Context.Provider
      value={{
        farm: activeFarm ? profileFor(activeFarm) : EMPTY_FARM,
        farms: store.farms,
        activeFarm,
        ready,
        storageError,
        save,
        addFarm,
        updateFarm,
        selectFarm,
        saveCrop,
        selectCrop: (id) => {
          if (activeFarm?.crops.some((c) => c.id === id))
            persist({
              ...store,
              farms: store.farms.map((f) =>
                f.id === activeFarm.id ? { ...f, selectedCropId: id } : f,
              ),
            });
        },
        removeFarm: (id) =>
          persist({
            ...store,
            farms: store.farms.filter((f) => f.id !== id),
            activeId:
              store.activeId === id
                ? store.farms.find((f) => f.id !== id)?.id || ""
                : store.activeId,
          }),
        removeCrop: (farmId, id) =>
          persist({
            ...store,
            farms: store.farms.map((f) =>
              f.id === farmId
                ? {
                    ...f,
                    crops: f.crops.filter((c) => c.id !== id),
                    selectedCropId:
                      f.selectedCropId === id
                        ? f.crops.find((c) => c.id !== id)?.id || ""
                        : f.selectedCropId,
                  }
                : f,
            ),
          }),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useFarm() {
  const c = useContext(Context);
  if (!c) throw new Error("Farm provider missing");
  return c;
}
