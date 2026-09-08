import { NextRequest,NextResponse } from 'next/server';
import { database } from '@/lib/server/db';
import { spatialContent } from '@/lib/server/location';
import { sourceBlob } from '@/lib/server/source-storage';
export const dynamic='force-dynamic';
export async function GET(req:NextRequest,{params}:{params:Promise<{id:string}>}){
 try{
  const id=(await params).id.slice(0,220),db=database();
  if(id.startsWith('spatial-')){const content=await spatialContent(id);return content?new Response(new Uint8Array(content),{headers:{'Content-Type':'application/json','Content-Disposition':'attachment; filename="agroamigo-capa.json"','Cache-Control':'public, max-age=31536000, immutable'}}):NextResponse.json({error:'No encontrado'},{status:404});}
  if(id.startsWith('weather-')){const r=(await db.query('SELECT payload FROM weather_snapshot WHERE id=$1',[id.slice(8)])).rows[0];return NextResponse.json(r?.payload||{error:'No encontrado'},{status:r?200:404,headers:{'Content-Disposition':'attachment; filename="pronostico.json"'}});}
  const r=(await db.query('SELECT id,media_type,octet_length(content) AS bytes FROM source_document WHERE id=$1 OR id=(SELECT document_id FROM document_alias WHERE alias=$1) LIMIT 1',[id])).rows[0];
  if(!r)return NextResponse.json({error:'No encontramos este documento.'},{status:404});
  const ext=r.media_type==='application/pdf'?'pdf':r.media_type==='application/vnd.ms-excel'?'xls':r.media_type.includes('spreadsheet')?'xlsx':r.media_type==='image/png'?'png':r.media_type==='application/zip'?'zip':r.media_type==='application/json'?'json':r.media_type==='text/html'?'html':r.media_type==='text/csv'?'csv':'txt';
  const headers:Record<string,string>={'Content-Type':r.media_type==='text/html'?'text/plain; charset=utf-8':r.media_type,'Content-Disposition':`${r.media_type==='application/pdf'?'inline':'attachment'}; filename="agroamigo-${r.id.slice(0,12)}.${ext}"`,'X-Content-Type-Options':'nosniff','Cache-Control':id===r.id?'public, max-age=31536000, immutable':'public, max-age=300','ETag':`"${r.id}"`};
  const blob=await sourceBlob(r.id,ext,req.headers.get('range'));
  if(blob){headers['X-Source-Storage']='azure-blob';headers['Accept-Ranges']='bytes';for(const name of ['content-length','content-range']){const value=blob.headers.get(name);if(value)headers[name]=value;}return new Response(blob.body,{status:blob.status,headers});}
  const content=(await db.query('SELECT content FROM source_document WHERE id=$1',[r.id])).rows[0].content;
  headers['Content-Length']=String(content.length);headers['X-Source-Storage']='database-archive';
  return new Response(new Uint8Array(content),{headers});
 }catch{return NextResponse.json({error:'No pudimos descargar el documento.'},{status:503});}
}
