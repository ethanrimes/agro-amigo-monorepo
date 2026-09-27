import { test, expect } from '@playwright/test';
import { currentInputIdentities, inputSourceCell, type InputRevision } from '../src/lib/input-revisions';
const old:InputRevision = {id:'13-26-6-50-kilogramos-fertisa-colombia-s-a-6235-0',name:'13-26-6',presentation:'50 kilogramos',observed_on:'2025-09-30',department:'Antioquia',document_id:'old',source_locator:'Hoja 1.3, fila 75346; precio por presentación',brand:'',registration:''};
const corrected:InputRevision = {...old,id:'13-26-6-50-kilogramos-fertisa-colombia-s-a-6235',document_id:'new',source_locator:'1.3!row 75346',brand:'FERTISA COLOMBIA S.A.',registration:'6235'};
const docs = [{id:'old',source_url:'https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSAInsumos-SeriesHistoricasDep-2018-2026.xlsx',retrieved_at:'2026-09-07T12:00:00Z'},{id:'new',source_url:'https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSAInsumos-SeriesHistoricasDep-2018-2026.xlsx',retrieved_at:'2026-09-15T12:00:00Z'}];
test('only a proven newer source-cell commercial identity suppresses a legacy catalog alias',()=>{
 expect(inputSourceCell(old.source_locator)).toBe(inputSourceCell(corrected.source_locator));
 expect(currentInputIdentities([old,corrected],docs)).toEqual([corrected]);
 // Retained old detail identity stays readable by itself.
 expect(currentInputIdentities([old],docs)).toEqual([old]);
 for(const alteration of [{department:'Boyacá'},{presentation:'1 litro'},{observed_on:'2025-08-31'},{source_locator:'1.3!row 75347'},{name:'Otro 13-26-6'}])
  expect(currentInputIdentities([old,{...corrected,...alteration}],docs)).toHaveLength(2);
 expect(currentInputIdentities([old,corrected],docs.map(d=>({...d,source_url:d.id})))).toHaveLength(2);
 expect(currentInputIdentities([old,corrected],docs.map(d=>({...d,retrieved_at:'2026-09-07T12:00:00Z'})))).toHaveLength(2);
 expect(currentInputIdentities([old,corrected,{...corrected,id:'another',brand:'Otra marca'}],docs)).toHaveLength(3);
});

test('live grouped input catalog keeps corrected variants and retained legacy details',async({request})=>{
 test.skip(process.env.RUN_PRICE_AUDIT !== "1", "Opt-in Sep27 retained source-revision audit");
 test.setTimeout(60000);
 const response=await request.get('/api/planning/inputs?grouped=true&department=Antioquia&scope=department');
 expect(response.ok()).toBe(true);
 const rows=await response.json();
 expect(rows.some((r:{id:string})=>r.id===corrected.id)).toBe(true);
 expect(rows.some((r:{id:string})=>r.id===old.id)).toBe(false);
 for(const name of ['100 centímetros cúbicos','250 centímetros cúbicos','1 litro'])
  expect(rows.some((r:{name:string;presentation:string})=>r.name==='Acarotal 1,8 Ec'&&r.presentation===name)).toBe(true);
});
