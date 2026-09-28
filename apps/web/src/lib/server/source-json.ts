/** Retry a transient public-source failure once; never turn failure into no data. */
export async function sourceJson(url: string) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const response = await fetch(url, {
        signal: AbortSignal.timeout(25000),
        cache: "no-store",
      });
      if (!response.ok) {
        const retryAfter = Number(response.headers.get("retry-after") || "0");
        if (
          attempt === 0 &&
          [408, 429, 500, 502, 503, 504].includes(response.status) &&
          Number.isFinite(retryAfter) &&
          retryAfter <= 1
        ) {
          await response.body?.cancel();
          await new Promise((resolve) =>
            setTimeout(resolve, Math.max(250, retryAfter * 1000)),
          );
          continue;
        }
        throw Error("La entidad no respondió a la consulta.");
      }
      const body = await response.json();
      if (!body || typeof body !== "object" || body.error)
        throw Error("El geoservicio no pudo resolver esta consulta.");
      return body;
    } catch (error) {
      if (
        attempt === 0 &&
        error instanceof Error &&
        ["TimeoutError", "TypeError"].includes(error.name)
      ) {
        await new Promise((resolve) => setTimeout(resolve, 250));
        continue;
      }
      throw error;
    }
  }
  throw Error("La entidad no respondió a la consulta.");
}
