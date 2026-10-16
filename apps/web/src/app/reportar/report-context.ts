const allowedFilters = new Set([
  "q", "series", "market", "presentation", "units", "region", "history",
  "date", "period", "scope", "department", "municipality", "product",
  "source", "page", "locator", "sheet", "tab", "group", "year", "month",
  "filter", "currency", "sort",
]);

const preciseCoordinate = /(?:^|[^\d])[+-]?\d{1,3}\.\d{4,}(?:$|[^\d])/;

export function safeReportPath(input: string | null | undefined): string | undefined {
  if (!input || !input.startsWith("/") || input.startsWith("//")) return undefined;
  try {
    const url = new URL(input, "https://agroamigo.local");
    if (url.origin !== "https://agroamigo.local" || url.pathname === "/reportar") return undefined;
    const params = new URLSearchParams();
    for (const [key, value] of url.searchParams) {
      if (!allowedFilters.has(key.toLowerCase()) || value.length > 200 || preciseCoordinate.test(value)) continue;
      const candidate = new URLSearchParams(params);
      candidate.append(key, value);
      if (url.pathname.length + candidate.toString().length + 1 <= 1000) params.append(key, value);
    }
    return url.pathname + (params.size ? `?${params}` : "");
  } catch {
    return undefined;
  }
}

export function sourceDocumentId(path: string | undefined): string | undefined {
  return /^\/evidence\/([a-f0-9]{64})(?:\?|$)/i.exec(path || "")?.[1].toLowerCase();
}

export function relatedScreenLabel(path: string): string {
  const url = new URL(path, "https://agroamigo.local");
  const segments = url.pathname.split("/").filter(Boolean);
  const section = segments[0] || "inicio";
  if (section === "evidence") {
    const page = url.searchParams.get("page");
    return page && /^\d{1,5}$/.test(page) ? `Fuente consultada · página ${page}` : "Fuente consultada";
  }
  const names: Record<string, string> = {
    inicio: "Inicio", products: "Productos", product: "Producto", references: "Referencia oficial",
    markets: "Mercados", market: "Mercado", insumos: "Insumos", insumo: "Insumo",
    farm: "Mi finca", plan: "Calendario y fuentes", sources: "Fuentes y ayuda",
    credits: "Créditos de imágenes", daily: "Precios diarios", regional: "Informe por ciudad",
    saved: "Mis guardados", offers: "Comparar ofertas", compare: "Comparación",
  };
  const name = names[section] || "Pantalla de AgroAmigo";
  if (!segments[1] || !["product", "market", "insumo"].includes(section)) return name;
  let subject = segments[1];
  try { subject = decodeURIComponent(subject); } catch { return name; }
  subject = subject.replace(/[-_]+/g, " ").trim();
  return subject ? `${name} · ${subject}` : name;
}
