"use client";
import { useEffect, useState } from "react";
import type { CatalogPage } from "@/lib/catalog-types";
import {
  fetchJson,
  JsonFetchTimeoutError,
  JsonResponseParseError,
} from "@/lib/client/fetch-json";

class CatalogDisplayError extends Error {}

/** An aborted or older response cannot repaint a newer filter selection. */
export function useCatalogPage(body: string | null) {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<{ key: string | null; data: CatalogPage | null; loading: boolean; error: string }>({ key: null, data: null, loading: false, error: "" });
  useEffect(() => {
    if (!body) return;
    const controller = new AbortController();
    setResult({ key: body, data: null, loading: true, error: "" });
    fetchJson<unknown>("/api/catalog", {
      method: "POST", headers: { "Content-Type": "application/json" }, body,
      signal: controller.signal,
    }).then(({ response, data }) => {
      if (!response.ok) throw new CatalogDisplayError(
        typeof (data as { error?: unknown } | null)?.error === "string"
          ? (data as { error: string }).error
          : "No pudimos cargar los productos. Intenta de nuevo.",
      );
      if (!controller.signal.aborted) setResult({ key: body, data: data as CatalogPage, loading: false, error: "" });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setResult({ key: body, data: null, loading: false,
        error: error instanceof CatalogDisplayError ? error.message
          : error instanceof JsonFetchTimeoutError
            ? "El catálogo tardó demasiado en responder. Revisa tu conexión e intenta de nuevo."
            : error instanceof JsonResponseParseError
              ? "No pudimos leer la respuesta del catálogo. Intenta de nuevo."
              : "No pudimos conectar con el catálogo. Revisa tu conexión e intenta de nuevo." });
    });
    return () => controller.abort();
  }, [body, version]);
  return {
    ...(result.key === body ? result : { data: null, loading: Boolean(body), error: "" }),
    retry: () => setVersion((value) => value + 1),
  };
}
