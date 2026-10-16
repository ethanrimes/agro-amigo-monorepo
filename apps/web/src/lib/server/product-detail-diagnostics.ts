/** Server-only, bounded diagnostics for product-detail failures. */
const stages = new Set([
  "market_alias", "product_lookup", "filter_options", "selected_quotes",
  "summary_references", "classification", "dispatch",
]);

function boundedMs(value: number): number {
  return Number.isFinite(value) ? Math.max(0, Math.min(120_000, Math.round(value))) : 0;
}

function errorCode(error: unknown): string {
  if (!error || typeof error !== "object") return "UNKNOWN";
  const coded = (error as { code?: unknown }).code;
  if (typeof coded === "string" && /^[A-Z0-9]{5}$/.test(coded)) return coded;
  const message = (error as { message?: unknown }).message;
  if (message === "PRODUCT_DETAIL_BUSY" || message === "SNAPSHOT_BUSY") return message;
  return "UNKNOWN";
}

export class ProductDetailStageError extends Error {
  readonly stage: string;
  readonly stageDurationMs: number;
  readonly failureCode: string;

  constructor(stage: string, durationMs: number, cause: unknown) {
    super("PRODUCT_DETAIL_STAGE_FAILED");
    this.name = "ProductDetailStageError";
    this.stage = stages.has(stage) ? stage : "dispatch";
    this.stageDurationMs = boundedMs(durationMs);
    this.failureCode = errorCode(cause);
  }
}

export async function withProductDetailStage<T>(stage: string, work: () => Promise<T>): Promise<T> {
  const started = performance.now();
  try {
    return await work();
  } catch (error) {
    throw new ProductDetailStageError(stage, performance.now() - started, error);
  }
}

export function productDetailFailureEvent(
  error: unknown,
  id: string,
  filters: Record<string, string>,
  totalDurationMs: number,
) {
  const stageError = error instanceof ProductDetailStageError ? error : null;
  const series = filters.series === "monthly" || filters.series === "city" ? filters.series : "other";
  const history = filters.history === "all" || filters.history === "recent" ? filters.history : "other";
  return {
    event: "product_detail_failed",
    product_id: /^[a-z0-9-]{1,120}$/.test(id) ? id : "invalid-product-id",
    stage: stageError?.stage ?? "dispatch",
    duration_ms: boundedMs(totalDurationMs),
    stage_duration_ms: stageError?.stageDurationMs ?? 0,
    code: stageError?.failureCode ?? errorCode(error),
    filters: {
      series,
      history,
      region_present: Boolean(filters.region),
      market_present: Boolean(filters.market),
      presentation_present: Boolean(filters.presentation),
      units_present: Boolean(filters.units),
    },
  } as const;
}
