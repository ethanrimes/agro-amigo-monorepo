"use client";
import { useEffect, useState } from "react";
export function useData<T>(url: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (!url) { setData(null); setError(""); setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setData(null);
    fetch(url, { signal: controller.signal })
      .then(async (response) => {
        const value = await response.json();
        if (!response.ok)
          throw new Error(value.error || "No pudimos cargar la información.");
        return value;
      })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [url, version]);
  return { data, loading, error, retry: () => setVersion((x) => x + 1) };
}
