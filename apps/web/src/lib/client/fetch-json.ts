export const JSON_FETCH_TIMEOUT_MS = 30_000;

export class JsonFetchTimeoutError extends Error {
  constructor() {
    super("JSON request timed out");
    this.name = "JsonFetchTimeoutError";
  }
}

export class JsonResponseParseError extends Error {
  readonly cause: unknown;

  constructor(cause: unknown) {
    super("Could not parse JSON response");
    this.name = "JsonResponseParseError";
    this.cause = cause;
  }
}

function abortError() {
  const error = new Error("The operation was aborted");
  error.name = "AbortError";
  return error;
}

/** Fetch JSON with one deadline spanning headers and body consumption. */
export async function fetchJson<T>(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = JSON_FETCH_TIMEOUT_MS,
): Promise<{ response: Response; data: T }> {
  const callerSignal = init.signal;
  if (callerSignal?.aborted) throw abortError();

  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  let timeoutReject: ((reason: JsonFetchTimeoutError) => void) | undefined;
  let didTimeout = false;
  const timeoutError = new JsonFetchTimeoutError();
  const timeout = new Promise<never>((_resolve, reject) => {
    timeoutReject = reject;
    timeoutId = setTimeout(() => {
      didTimeout = true;
      controller.abort();
      timeoutReject?.(timeoutError);
    }, timeoutMs);
  });
  let abortListener: (() => void) | undefined;
  const cancelled = new Promise<never>((_resolve, reject) => {
    abortListener = () => {
      controller.abort();
      reject(abortError());
    };
    callerSignal?.addEventListener("abort", abortListener, { once: true });
  });

  const { signal: _callerSignal, ...fetchInit } = init;
  const request = (async () => {
    const response = await fetch(input, { ...fetchInit, signal: controller.signal });
    let data: T;
    try {
      data = (await response.json()) as T;
    } catch (error) {
      if (didTimeout) throw timeoutError;
      if (callerSignal?.aborted) throw abortError();
      throw new JsonResponseParseError(error);
    }
    if (didTimeout) throw timeoutError;
    if (callerSignal?.aborted) throw abortError();
    return { response, data };
  })();

  try {
    return await Promise.race([request, timeout, cancelled]);
  } catch (error) {
    if (didTimeout) throw timeoutError;
    if (callerSignal?.aborted) throw abortError();
    throw error;
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
    if (abortListener) callerSignal?.removeEventListener("abort", abortListener);
  }
}
