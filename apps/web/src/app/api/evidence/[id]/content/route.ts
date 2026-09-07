import { NextRequest,NextResponse } from 'next/server';
import { database } from '@/lib/server/db';
export const dynamic='force-dynamic';
export async function GET(req:NextRequest,{params}:{params:Promise<{id:string}>}){
 try{
  const id=(await params).id.slice(0,220),db=database();
  if(id.startsWith('weather-')){const r=(await db.query('SELECT payload FROM weather_snapshot WHERE id=$1',[id.slice(8)])).rows[0];return NextResponse.json(r?.payload||{error:'No encontrado'},{status:r?200:404,headers:{'Content-Disposition':'attachment; filename="pronostico.json"'}});}
  const r=(await db.query('SELECT id,content,media_type FROM source_document WHERE id=$1 OR id=(SELECT document_id FROM document_alias WHERE alias=$1) LIMIT 1',[id])).rows[0];
  if(!r)return NextResponse.json({error:'No encontramos este documento.'},{status:404});
  const ext=r.media_type==='application/pdf'?'pdf':r.media_type.includes('spreadsheet')?'xlsx':r.media_type==='application/json'?'json':'txt';
  // HTML is never executed on the app origin. Only PDF is eligible for inline viewing.
  return new Response(new Uint8Array(r.content),{headers:{'Content-Type':r.media_type==='text/html'?'text/plain; charset=utf-8':r.media_type,'Content-Length':String(r.content.length),'Content-Disposition':`${r.media_type==='application/pdf'?'inline':'attachment'}; filename="agroamigo-${r.id.slice(0,12)}.${ext}"`,'X-Content-Type-Options':'nosniff','Cache-Control':id===r.id?'public, max-age=31536000, immutable':'public, max-age=300','ETag':`"${r.id}"`}});
 }catch{return NextResponse.json({error:'No pudimos descargar el documento.'},{status:503});}
}
