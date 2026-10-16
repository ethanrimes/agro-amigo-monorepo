// Android's embedded WebView intermittently leaves opaque black bands when a
// PDF page is rasterized into a large canvas. The page's CSS size still follows
// the selected zoom; only its backing bitmap is bounded on the native wrapper.
export const ANDROID_WEBVIEW_PDF_MAX_CANVAS_PIXELS = 800_000;

export function pdfCanvasBackingRatio({
  width,
  height,
  devicePixelRatio,
  userAgent,
}: {
  width: number;
  height: number;
  devicePixelRatio: number;
  userAgent: string;
}): number {
  if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(height) || height <= 0) {
    throw new RangeError("The PDF page viewport must have positive finite dimensions.");
  }
  const area = width * height;
  if (!Number.isFinite(area) || area <= 0) {
    throw new RangeError("The PDF page viewport area must be positive and finite.");
  }
  const requestedRatio = Math.min(Number.isFinite(devicePixelRatio) && devicePixelRatio > 0
    ? devicePixelRatio : 1, 2);
  const ratio = userAgent.includes("AgroAmigoAndroid/")
    ? Math.min(requestedRatio, Math.sqrt(ANDROID_WEBVIEW_PDF_MAX_CANVAS_PIXELS / area))
    : requestedRatio;
  const backingWidth = Math.floor(width * ratio), backingHeight = Math.floor(height * ratio);
  if (!Number.isSafeInteger(backingWidth) || backingWidth < 1 ||
      !Number.isSafeInteger(backingHeight) || backingHeight < 1) {
    throw new RangeError("The PDF page cannot be rendered into a positive canvas.");
  }
  return ratio;
}
