import "server-only";

type SnapshotEntry<T> = Readonly<{ value: T; expires: number }>;

type SnapshotState = {
  ttlMs: number;
  capacity: number;
  values: Map<string, SnapshotEntry<unknown>>;
  pending: Map<string, Promise<SnapshotEntry<unknown>>>;
};
const shared = globalThis as unknown as { agroSnapshots?: Map<string, SnapshotState> };

/** Share named snapshots across independently bundled routes in one server.
 * Use withExpiry when an outer cache must inherit this exact read's deadline. */
export function snapshotCache<T>(ttlMs = 5 * 60 * 1000, capacity = 64, name?: string) {
  let state = name ? shared.agroSnapshots?.get(name) : undefined;
  if (state && (state.ttlMs !== ttlMs || state.capacity !== capacity)) {
    throw new Error("SNAPSHOT_CONFIGURATION_MISMATCH");
  }
  if (!state) {
    state = { ttlMs, capacity, values: new Map(), pending: new Map() };
    if (name) {
      shared.agroSnapshots ??= new Map();
      shared.agroSnapshots.set(name, state);
    }
  }
  const { values, pending } = state;
  const readWithExpiry = async (
    key: string,
    read: () => Promise<T>,
    upstreamExpiresAt?: () => number,
  ): Promise<SnapshotEntry<T>> => {
    const cached = values.get(key);
    if (cached && cached.expires > Date.now()) return cached as SnapshotEntry<T>;
    const active = pending.get(key);
    if (active) return active as Promise<SnapshotEntry<T>>;
    if (pending.size >= capacity) throw new Error("SNAPSHOT_BUSY");
    const work = read().then((value) => {
      values.delete(key);
      const expires = Math.min(Date.now() + ttlMs, upstreamExpiresAt?.() ?? Infinity);
      const entry: SnapshotEntry<T> = Object.freeze({ value, expires });
      values.set(key, entry);
      while (values.size > capacity) values.delete(values.keys().next().value!);
      return entry;
    }).finally(() => pending.delete(key));
    pending.set(key, work);
    return work;
  };
  const readSnapshot = async (
    key: string,
    read: () => Promise<T>,
    upstreamExpiresAt?: () => number,
  ): Promise<T> => (await readWithExpiry(key, read, upstreamExpiresAt)).value;
  return Object.assign(readSnapshot, {
    withExpiry: readWithExpiry,
    expiresAt: (key: string) => values.get(key)?.expires ?? 0,
  });
}
