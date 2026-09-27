"use client";
import { useEffect, useState } from "react";
import type { CatalogPage } from "@/lib/catalog-types";

/** An aborted or older response cannot repaint a newer filter selection. */
export function useCatalogPage(body: string | null) {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<{ key: string | null; data: CatalogPage | null; loading: boolean; error: string }>({ key: null, data: null, loading: false, error: "" });
  useEffect(() => {
    if (!body) return;
    const controller = new AbortController();
    setResult({ key: body, data: null, loading: true, error: "" });
    fetch("/api/catalog", {
      method: "POST", headers: { "Content-Type": "application/json" }, body,
      signal: controller.signal,
    }).then(async (response) => {
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "No pudimos cargar los productos.");
      if (!controller.signal.aborted) setResult({ key: body, data, loading: false, error: "" });
    }).catch((error) => {
      if (!controller.signal.aborted) setResult({ key: body, data: null, loading: false, error: error.message });
    });
    return () => controller.abort();
  }, [body, version]);
  return {
    ...(result.key === body ? result : { data: null, loading: Boolean(body), error: "" }),
    retry: () => setVersion((value) => value + 1),
  };
}
