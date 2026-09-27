import "server-only";

/** Coalesce concurrent reads and bound retained snapshots; never cache failures. */
export function snapshotCache<T>(ttlMs = 5 * 60 * 1000, capacity = 64) {
  const values = new Map<string, { expires: number; value: T }>();
  const pending = new Map<string, Promise<T>>();
  return async (key: string, read: () => Promise<T>): Promise<T> => {
    const cached = values.get(key);
    if (cached && cached.expires > Date.now()) return cached.value;
    const active = pending.get(key);
    if (active) return active;
    if (pending.size >= capacity) throw new Error("SNAPSHOT_BUSY");
    const work = read().then((value) => {
      values.delete(key);
      values.set(key, { expires: Date.now() + ttlMs, value });
      while (values.size > capacity) values.delete(values.keys().next().value!);
      return value;
    }).finally(() => pending.delete(key));
    pending.set(key, work);
    return work;
  };
}
