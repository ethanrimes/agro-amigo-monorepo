/**
 * In-memory session cache for query results. Keyed by string, TTL-bounded,
 * invalidate-by-prefix.
 *
 * Why in-memory (not AsyncStorage/localStorage): we want cache hits within a
 * navigation session (tap a row, navigate in, collapse a chart, re-expand)
 * without staleness risk across reloads.
 */

type Entry = { value: unknown; expiresAt: number };

const store = new Map<string, Entry>();
const inflight = new Map<string, Promise<unknown>>();

const DEFAULT_TTL_MS = 5 * 60 * 1000;

export function cacheGet<T>(key: string): T | undefined {
  const entry = store.get(key);
  if (!entry) return undefined;
  if (entry.expiresAt <= Date.now()) {
    store.delete(key);
    return undefined;
  }
  return entry.value as T;
}

export function cacheSet<T>(key: string, value: T, ttlMs: number = DEFAULT_TTL_MS): void {
  store.set(key, { value, expiresAt: Date.now() + ttlMs });
}

export function cacheDelete(key: string): void {
  store.delete(key);
}

/** Delete every entry whose key starts with the given prefix. */
export function cacheInvalidatePrefix(prefix: string): void {
  for (const key of Array.from(store.keys())) {
    if (key.startsWith(prefix)) store.delete(key);
  }
}

export function cacheClear(): void {
  store.clear();
  inflight.clear();
}

/**
 * Run `fetcher` through the cache. If a matching entry exists and is fresh,
 * returns it without calling fetcher. If the same key is already in flight,
 * awaits that promise (request coalescing).
 */
export async function cachedCall<T>(
  key: string,
  fetcher: () => Promise<T>,
  ttlMs: number = DEFAULT_TTL_MS,
): Promise<T> {
  const hit = cacheGet<T>(key);
  if (hit !== undefined) return hit;

  const pending = inflight.get(key) as Promise<T> | undefined;
  if (pending) return pending;

  const promise = (async () => {
    try {
      const value = await fetcher();
      cacheSet(key, value, ttlMs);
      return value;
    } finally {
      inflight.delete(key);
    }
  })();
  inflight.set(key, promise);
  return promise;
}

/** Build a stable cache key from parts. Objects are JSON-stringified. */
export function cacheKey(...parts: Array<string | number | null | undefined | Record<string, unknown>>): string {
  return parts
    .map((p) => {
      if (p == null) return '';
      if (typeof p === 'object') return JSON.stringify(p);
      return String(p);
    })
    .join(':');
}
