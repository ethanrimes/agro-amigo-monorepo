import { useCallback, useEffect, useRef, useState } from 'react';
import { cacheGet, cachedCall } from './cache';

export interface UseCachedQueryResult<T> {
  data: T | undefined;
  loading: boolean;
  error: unknown;
  refetch: () => Promise<void>;
}

export interface UseCachedQueryOptions {
  /** When false, the hook does not fetch. Use this for lazy expanders. */
  enabled?: boolean;
  /** TTL override in ms. */
  ttlMs?: number;
}

/**
 * React hook that fetches a value through the shared cache. When `enabled`
 * flips from false to true, fetches (or returns a cached hit instantly).
 * Honors the cache across mounts, so collapsing and re-expanding a chart
 * is free as long as TTL has not elapsed.
 */
export function useCachedQuery<T>(
  key: string,
  fetcher: () => Promise<T>,
  opts: UseCachedQueryOptions = {},
): UseCachedQueryResult<T> {
  const { enabled = true, ttlMs } = opts;
  const [data, setData] = useState<T | undefined>(() => cacheGet<T>(key));
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<unknown>(null);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const value = await cachedCall<T>(key, fetcher, ttlMs);
      if (mountedRef.current) setData(value);
    } catch (err) {
      if (mountedRef.current) setError(err);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [key, fetcher, ttlMs]);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) return;
    const hit = cacheGet<T>(key);
    if (hit !== undefined) {
      setData(hit);
      return;
    }
    load();
    return () => {
      mountedRef.current = false;
    };
  }, [enabled, key, load]);

  return { data, loading, error, refetch: load };
}
