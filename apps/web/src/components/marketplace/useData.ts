"use client";
import { useEffect, useState } from "react";
import {
  fetchJson,
  JsonFetchTimeoutError,
  JsonResponseParseError,
} from "@/lib/client/fetch-json";
export function useData<T>(url: string | null, timeoutMs?: number) {
  const [version, setVersion] = useState(0);
  const key = url ? JSON.stringify([url, version, timeoutMs]) : null;
  const [result, setResult] = useState<{
    key: string | null;
    data: T | null;
    loading: boolean;
    error: string;
  }>({ key: null, data: null, loading: false, error: "" });
  useEffect(() => {
    if (!url) {
      setResult({ key: null, data: null, loading: false, error: "" });
      return;
    }
    const controller = new AbortController();
    const requestKey = JSON.stringify([url, version, timeoutMs]);
    setResult({ key: requestKey, data: null, loading: true, error: "" });
    fetchJson<unknown>(url, { signal: controller.signal }, timeoutMs)
      .then(({ response, data }) => {
        const value = data as { error?: unknown } | null;
        if (!response.ok)
          throw new Error(value?.error
            ? typeof value.error === "string" ? value.error : String(value.error)
            : "No pudimos cargar la información.");
        return data as T;
      })
      .then((data: T) => {
        if (!controller.signal.aborted)
          setResult({ key: requestKey, data, loading: false, error: "" });
      })
      .catch((e) => {
        const error = e instanceof Error ? e : new Error(String(e));
        if (!controller.signal.aborted && error.name !== "AbortError")
          setResult({ key: requestKey, data: null, loading: false, error:
            e instanceof JsonFetchTimeoutError
              ? "La consulta tardó demasiado. Revisa tu conexión e intenta de nuevo."
              : e instanceof JsonResponseParseError
                ? e.cause instanceof Error ? e.cause.message : "No pudimos leer la respuesta. Intenta de nuevo."
                : error.message || "No pudimos cargar la información. Intenta de nuevo." });
      });
    return () => controller.abort();
  }, [url, version, timeoutMs]);
  return {
    ...(key !== null && result.key === key
      ? result
      : { data: null, loading: key !== null, error: "" }),
    retry: () => setVersion((x) => x + 1),
  };
}
