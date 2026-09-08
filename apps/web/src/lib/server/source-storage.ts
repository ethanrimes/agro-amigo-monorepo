import "server-only";
let cachedToken: { value: string; expires: number } | null = null;
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
  const response=await fetch(`https://${account}.blob.core.windows.net/source-archive/${id}.${extension}`,{headers,signal:AbortSignal.timeout(20000)});
  return response.ok ? response : null;
 } catch {return null;}
}
