const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const ts = require('typescript');
const {Client,types}=require('pg');
const out={};new Function('exports',ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib/server/official-evidence-sql.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(out);
const SQL=out.OFFICIAL_EVIDENCE_ROWS_SQL;
const OLD=`SELECT product_name,market,observed_on,period_start,price,min_price,max_price,currency,unit,basis,source_locator
 FROM(SELECT DISTINCT ON(q.source_locator) q.* FROM official_price_quote q
 WHERE q.document_id=$1 AND($2='' OR q.source_locator=$2)
 AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id AND a.status='review' AND(a.observed_on IS NULL OR a.observed_on=q.observed_on))
 AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
 ORDER BY q.source_locator,q.parsed_at DESC) verified ORDER BY observed_on DESC,source_locator LIMIT100`.replace('LIMIT100','LIMIT 100');
const socket=process.env.AGRO_EVIDENCE_SQL_TEST_SOCKET, enabled=socket?.startsWith('/tmp/agro-evidence-pg-');
let db;types.setTypeParser(1082,v=>v);const pgtest=(name,fn)=>test(name,{skip:!enabled&&'Requires isolated local PostgreSQL'},fn);
test('source preview limits narrow revisions before payload join',()=>{assert.ok(SQL.includes('AS MATERIALIZED'));assert.ok(SQL.indexOf('LIMIT 100')<SQL.indexOf('JOIN official_price_quote q'));assert.ok(!SQL.includes('q.*'));assert.ok(SQL.includes('r.created_at>=q.parsed_at'));});
before(async()=>{if(!enabled)return;db=new Client({host:socket,port:65449,database:'postgres'});await db.connect();await db.query(`SET search_path=pg_temp;SET statement_timeout='10s';
 CREATE TEMP TABLE official_price_quote(document_id text,source_locator text,parser_version text,parsed_at timestamptz,observed_on date,product_name text,market text,period_start date,price numeric,min_price numeric,max_price numeric,currency text,unit text,basis text,PRIMARY KEY(document_id,source_locator,parser_version));
 CREATE TEMP TABLE official_source_review(document_id text,source_locator text,created_at timestamptz);
 CREATE TEMP TABLE ingestion_asset(document_id text,status text,observed_on date);
 INSERT INTO official_price_quote SELECT 'large', 'cell-'||lpad(n::text,3,'0'),'v1','2026-09-01',DATE '2020-01-01'+n,'Product','Market',NULL,n,NULL,NULL,'USD','tonne','Benchmark' FROM generate_series(1,130)n;
 INSERT INTO official_price_quote SELECT document_id,source_locator,'v2','2026-09-02',observed_on,product_name,market,period_start,price+10,min_price,max_price,currency,unit,basis FROM official_price_quote;
 INSERT INTO official_source_review VALUES('large','cell-130','2026-09-03'),('large','cell-129','2026-09-03');
 INSERT INTO official_price_quote SELECT document_id,source_locator,'v3','2026-09-04',observed_on,product_name,market,period_start,999,min_price,max_price,currency,unit,basis FROM official_price_quote WHERE source_locator='cell-129' AND parser_version='v1';
 INSERT INTO official_price_quote SELECT document_id,source_locator,'v3','2026-09-04',DATE '2019-01-01',product_name,market,period_start,777,min_price,max_price,currency,unit,basis FROM official_price_quote WHERE source_locator='cell-128' AND parser_version='v1';
 INSERT INTO ingestion_asset VALUES('large','review','2020-05-07'),('all-review','review',NULL),('unrelated','review',NULL);
 INSERT INTO official_price_quote SELECT 'all-review',source_locator,parser_version,parsed_at,observed_on,product_name,market,period_start,price,min_price,max_price,currency,unit,basis FROM official_price_quote WHERE document_id='large' AND parser_version='v1';
 CREATE INDEX official_quote_document_revisions ON official_price_quote(document_id,source_locator,parsed_at DESC) INCLUDE(observed_on,parser_version);`);assert.equal((await db.query("SELECT relpersistence FROM pg_class WHERE oid='official_price_quote'::regclass")).rows[0].relpersistence,'t');});
after(async()=>{if(db)await db.end();});
async function same(doc,loc=''){const expected=(await db.query(OLD,[doc,loc])).rows,actual=(await db.query(SQL,[doc,loc])).rows;assert.deepEqual(actual,expected);return actual;}
pgtest('100-row preview preserves corrected revisions, review suppression, ordering and date changes',async()=>{const r=await same('large');assert.equal(r.length,100);assert.equal(r[0].source_locator,'cell-129');assert.equal(r[0].price,'999');assert.ok(!r.some(x=>['cell-130','cell-128','cell-127'].includes(x.source_locator)));});
pgtest('exact old-locator lookup preserves corrected date and original units',async()=>{const r=await same('large','cell-128');assert.equal(r.length,1);assert.equal(r[0].observed_on,'2019-01-01');assert.equal(r[0].price,'777');assert.equal(r[0].unit,'tonne');});
pgtest('whole-original review and absent sources remain empty',async()=>{assert.deepEqual(await same('all-review'),[]);assert.deepEqual(await same('missing'),[]);});
pgtest('row review remains excluded until a subsequent successful parse',async()=>{assert.deepEqual(await same('large','cell-130'),[]);assert.equal((await same('large','cell-129'))[0].price,'999');});
