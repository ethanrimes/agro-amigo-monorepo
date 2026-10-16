const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');
types.setTypeParser(1700, Number);
types.setTypeParser(1082, value => value);
const dsn = process.env.AGRO_INPUT_QUERY_TEST_DATABASE;
function compiled(relative, mocks = {}) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,relative),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
    {exports,Intl,Date,JSON,require:name=>mocks[name] || {}});
  return exports;
}
test('same-department input detail keeps oldest native aliases and selects the newest quote',
  {skip:!dsn}, async()=>{
    const client = new Client({connectionString:dsn,statement_timeout:12000});
    await client.connect();
    try {
      await client.query('BEGIN');
      await client.query('SET LOCAL search_path=pg_temp');
      await client.query(`CREATE TEMP TABLE published_input_price(id text,department text,
        observed_on date,price numeric,document_id text,source_locator text);
        CREATE TEMP TABLE published_input_municipal_price(LIKE published_input_price);
        ALTER TABLE published_input_municipal_price ADD COLUMN municipality text;`);
      const rows=[
        ['retained-input','Quindio','2014-09-30',100,'old-pdf','PDF page 34,col 1,y 91; inputs-pdf-v14'],
        ['retained-input','Quindío','2018-09-30',120,'new-excel','2.2!row 42'],
        ['retained-input','Córdoba','2018-09-30',900,'other-department','1.2!row 72'],
        ['retained-input','Quindío','2099-09-30',999,'future-quote','1.2!row 79'],
      ];
      for(const row of rows){
        await client.query('INSERT INTO published_input_price VALUES($1,$2,$3,$4,$5,$6)',row);
        await client.query('INSERT INTO published_input_municipal_price VALUES($1,$2,$3,$4,$5,$6,$7)',[...row,'Armenia']);
      }
      await client.query("INSERT INTO published_input_municipal_price VALUES('retained-input','Quindío','2018-09-30',800,'other-town','1.2!row 75','Calarcá')");
      for(const scope of ['department','municipality']) {
        const regions=rows.slice(0,2).map(([id,department,observed_on,price,document_id,source_locator])=>
          ({id,department,observed_on,price,document_id,source_locator,
            municipality:scope==='municipality'?'Armenia':'',presentation:'1 litro',scope}));
        const api=compiled('../src/lib/server/explore.ts',{
          './db':{database:()=>client},'./planning':{inputs:async()=>regions},
          '../filter-labels':compiled('../src/lib/filter-labels.ts'),
          '../input-locations':compiled('../src/lib/input-locations.ts',{
            './filter-labels':compiled('../src/lib/filter-labels.ts')}),
          '../pdf-locator':compiled('../src/lib/pdf-locator.ts'),
        });
        const result=await api.inputDetail('retained-input','QUINDÍO',scope,
          scope==='municipality'?'Armenia':'',true);
        assert.equal(result.input.price,120,'Old alias sorted first must not become the current card');
        assert.equal(result.regions.length,1,'Verified native aliases offer one current location');
        assert.equal(result.history[0].sources[0].source_page,34);
        assert.deepEqual(Array.from(result.history,h=>[h.date,h.price]),
          [['2014-09-30',100],['2018-09-30',120]]);
        assert.equal(result.history[0].sources[0].document_id,'old-pdf');
        assert.equal(result.history[0].sources[0].source_locator,rows[0][5]);
        assert.equal(result.history[0].sources[0].market_name,
          scope==='municipality'?'Armenia, Quindio':'Quindio');
        assert.equal(result.history[1].sources[0].market_name,
          scope==='municipality'?'Armenia, Quindío':'Quindío');
        assert.equal(regions[0].department,'Quindio','Source geography remains literal');
      }
      assert.equal((await client.query('SELECT count(*)::int AS n FROM published_input_municipal_price')).rows[0].n,5);
    } finally { await client.query('ROLLBACK'); await client.end(); }
  });
