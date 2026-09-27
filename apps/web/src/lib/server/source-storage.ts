import "server-only";
let cachedToken: { value: string; expires: number } | null = null;

// Header acquisition and an individual stalled body read have separate limits.
// A total fetch timeout also aborts an already-started large browser download.
async function blobResponse(url: string, headers: Record<string, string>) {
 const controller = new AbortController();
 const headerTimer = setTimeout(() => controller.abort(new Error("Source headers timed out")), 20000);
 let response: Response;
 try {
  response = await fetch(url, { headers, signal: controller.signal });
 } finally {
  clearTimeout(headerTimer);
 }
 if (!response.ok || !response.body) {
  await response.body?.cancel();
  return null;
 }
 const reader = response.body.getReader();
 const body = new ReadableStream<Uint8Array>({
  async pull(target) {
   const idleTimer = setTimeout(() => controller.abort(new Error("Source body read stalled")), 60000);
   try {
    const part = await reader.read();
    if (part.done) target.close();
    else target.enqueue(part.value);
   } catch (error) {
    target.error(error);
   } finally {
    clearTimeout(idleTimer);
   }
  },
  async cancel(reason) {
   // Disconnected/cancelled clients must not leave an upstream download running.
   controller.abort(reason);
   await reader.cancel(reason).catch(() => undefined);
  },
 });
 return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
}

export async function sourceBlob(id: string, extension: string, range: string | null) {
 const account=process.env.SOURCE_STORAGE_ACCOUNT;
 if (!account || !process.env.IDENTITY_ENDPOINT || !process.env.IDENTITY_HEADER) return null;
 if (!/^[a-f0-9]{64}$/.test(id) || !/^[a-z0-9]+$/.test(account)) return null;
 try {
  if (!cachedToken || cachedToken.expires < Date.now()+60000) {
   const url=new URL(process.env.IDENTITY_ENDPOINT);url.searchParams.set("resource","https://storage.azure.com/");url.searchParams.set("api-version","2019-08-01");
   const response=await fetch(url,{headers:{"X-IDENTITY-HEADER":process.env.IDENTITY_HEADER},signal:AbortSignal.timeout(8000)});
   if(!response.ok)return null;
   const token=await response.json();cachedToken={value:token.access_token,expires:Number(token.expires_on)*1000};
  }
  const headers:Record<string,string>={Authorization:"Bearer "+cachedToken.value,"x-ms-version":"2023-11-03"};
  if(range && /^bytes=\d*-\d*$/.test(range))headers.Range=range;
  return await blobResponse(`https://${account}.blob.core.windows.net/source-archive/${id}.${extension}`, headers);
 } catch {return null;}
}
