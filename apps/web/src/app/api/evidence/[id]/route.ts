import { NextRequest,NextResponse } from 'next/server';
import { evidence } from '@/lib/server/planning';
export const dynamic='force-dynamic';
export async function GET(req:NextRequest,{params}:{params:Promise<{id:string}>}){
 try{const data=await evidence((await params).id.slice(0,220),req.nextUrl.searchParams);return NextResponse.json(data||{error:'No encontramos este documento.'},{status:data?200:404});}
 catch{return NextResponse.json({error:'No pudimos cargar el documento. Intenta nuevamente.'},{status:503});}
}
