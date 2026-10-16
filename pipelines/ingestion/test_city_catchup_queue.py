"""Bounded city ZIP catch-up selection and actual worker.run scheduling."""
import getpass
import io
import os
import random
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg

from . import queue_plan, worker
from .resumable_inputs import WorkDeferred


class CityCatchupPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-city-catchup-pg-", dir="/tmp"))
        cls.cluster = cls.directory / "data"
        cls.port = random.randrange(41000, 49000)
        try:
            subprocess.run(
                ["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale",
                 "--encoding=UTF8"],
                check=True, stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                ["pg_ctl", "-D", str(cls.cluster), "-l", str(cls.directory / "postgres.log"),
                 "-o", f'-k {cls.directory} -p {cls.port} -h ""', "-w", "start"],
                check=True, stdout=subprocess.DEVNULL,
            )
            cls.db = psycopg.connect(
                f"host={cls.directory} port={cls.port} dbname=postgres user={getpass.getuser()}",
                autocommit=True,
            )
            assert str(cls.db.info.host).startswith("/tmp/agro-city-catchup-pg-")
            cls.db.execute("SET search_path=pg_temp")
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        db = getattr(cls, "db", None)
        if db is not None:
            db.close()
        cluster = getattr(cls, "cluster", None)
        if cluster is not None and cluster.exists():
            subprocess.run(["pg_ctl", "-D", str(cluster), "-m", "fast", "-w", "stop"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        directory = getattr(cls, "directory", None)
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)

    def setUp(self):
        self.db.execute('DROP TABLE IF EXISTS pg_temp.ingestion_asset')
        self.db.execute('CREATE TEMP TABLE ingestion_asset('
                        'url text PRIMARY KEY, kind text NOT NULL, observed_on date,'
                        'status text NOT NULL, checked_at timestamptz)')

    def add(self, url, year, *, status='pending', checked=None, month=1, day=1, kind='city-zip'):
        self.db.execute('INSERT INTO ingestion_asset VALUES(%s,%s,%s,%s,%s)',
                        (url, kind, date(year, month, day), status, checked))

    def test_rotates_years_and_never_lets_2021_monopolize_2022(self):
        for year in (2021, 2022, 2023, 2025):
            self.add(f'{year}-old', year)
            self.add(f'{year}-next', year, day=2)
        for turn, year in enumerate((2021, 2022, 2023, 2025)):
            got = queue_plan.city_catchup_candidates(self.db, rotation=turn)
            self.assertEqual(got[0][0], f'{year}-old')
            self.assertEqual(got[1][0], f'{(2021, 2022, 2023, 2025)[(turn+1)%4]}-old')

    def test_due_retry_gets_second_slot_and_early_exclusion_frees_it(self):
        self.add('2021-old', 2021)
        self.add('2022-old', 2022)
        self.add('2020-due', 2020, checked='2026-01-01T00:00:00Z')
        got = queue_plan.city_catchup_candidates(self.db, rotation=1)
        self.assertEqual([r[0] for r in got], ['2022-old', '2020-due'])
        got = queue_plan.city_catchup_candidates(self.db, rotation=1, exclude_urls=['2022-old','2020-due'])
        self.assertEqual([r[0] for r in got], ['2021-old'])

    def test_future_review_complete_failed_and_recent_retry_are_excluded(self):
        self.add('valid', 2022)
        self.add('review', 2021, status='review')
        self.add('failed', 2021, status='failed')
        self.add('complete-old-parser', 2021, status='complete')
        self.add('future', date.today().year+2)
        self.add('wrong-kind', 2021, kind='daily-zip')
        self.add('recent-retry', 2021, checked='2099-01-01T00:00:00Z')
        self.assertEqual([r[0] for r in queue_plan.city_catchup_candidates(self.db, rotation=0)], ['valid'])

    def test_one_year_can_use_two_distinct_never_checked_rows(self):
        self.add('first', 2022)
        self.add('second', 2022, day=2)
        self.assertEqual([r[0] for r in queue_plan.city_catchup_candidates(self.db, rotation=124)], ['first','second'])

    def test_limit_zero_or_one_is_real(self):
        self.add('first', 2022)
        self.add('due', 2021, checked='2026-01-01T00:00:00Z')
        self.assertEqual(queue_plan.city_catchup_candidates(self.db, rotation=0, limit=0), [])
        self.assertEqual([r[0] for r in queue_plan.city_catchup_candidates(self.db, rotation=0, limit=1)], ['first'])

    def test_four_and_six_slots_rotate_distinct_years_with_one_due_retry(self):
        years=(2021,2022,2023,2024,2025,2026)
        for year in years:
            for day in range(1,7):self.add(f'{year}-{day}',year,day=day)
        self.add('old-due',2020,checked='2026-01-01T00:00:00Z')
        for turn in range(len(years)):
            got=queue_plan.city_catchup_candidates(self.db,rotation=turn,limit=6)
            self.assertEqual(len(got),6)
            self.assertEqual(got[0][0],f'{years[turn]}-1')
            self.assertEqual(got[1][0],'old-due')
            self.assertEqual(len({row[2].year for row in got if row[0]!='old-due'}),5)
            self.assertEqual(len({row[0] for row in got}),6)
        self.assertEqual(len(queue_plan.city_catchup_candidates(self.db,rotation=0,limit=4)),4)
        self.assertEqual(len(queue_plan.city_catchup_candidates(self.db,rotation=0,limit=100)),6)

    def test_one_year_six_slots_reach_successive_never_checked_sources(self):
        for day in range(1,8):self.add(f'2022-{day}',2022,day=day)
        self.add('old-due',2021,checked='2026-01-01T00:00:00Z')
        got=queue_plan.city_catchup_candidates(self.db,rotation=0,limit=6)
        self.assertEqual([row[0] for row in got],
            ['2022-1','old-due','2022-2','2022-3','2022-4','2022-5'])

    def test_earlier_repair_and_historical_exclusions_do_not_spend_city_slots(self):
        self.add('repair-first', 2021)
        self.add('historical-first', 2022)
        self.add('city-next', 2023)
        selected = queue_plan.city_catchup_candidates(
            self.db, rotation=0, exclude_urls={'repair-first', 'historical-first'}
        )
        self.assertEqual([row[0] for row in selected], ['city-next'])

    def test_recent_gap_is_reserved_while_old_never_checked_and_retry_rotate(self):
        today = self.db.execute("SELECT (clock_timestamp() AT TIME ZONE 'America/Bogota')::date").fetchone()[0]
        missing = today - timedelta(days=100)
        self.add('https://www.dane.gov.co/files/recent.zip', missing.year,
                 month=missing.month, day=missing.day)
        self.add('old-never', 2021)
        self.add('old-retry', 2020, checked=datetime.now(timezone.utc)-timedelta(hours=7))
        before = self.db.execute('SELECT * FROM ingestion_asset ORDER BY url').fetchall()
        even = queue_plan.city_catchup_candidates(self.db, rotation=0,
                    recent_since=today-timedelta(days=365))
        odd = queue_plan.city_catchup_candidates(self.db, rotation=1,
                    recent_since=today-timedelta(days=365))
        self.assertEqual([r[0] for r in even],
                         ['https://www.dane.gov.co/files/recent.zip', 'old-never'])
        self.assertEqual([r[0] for r in odd],
                         ['https://www.dane.gov.co/files/recent.zip', 'old-retry'])
        self.assertEqual(before, self.db.execute('SELECT * FROM ingestion_asset ORDER BY url').fetchall())

    def test_recent_gap_uses_oldest_due_source_and_keeps_existing_total_cap(self):
        today = self.db.execute("SELECT (clock_timestamp() AT TIME ZONE 'America/Bogota')::date").fetchone()[0]
        for age in (100, 90, 80):
            day = today - timedelta(days=age)
            self.add(f'https://www.dane.gov.co/files/gap-{age}.zip', day.year,
                     month=day.month, day=day.day,
                     checked=datetime.now(timezone.utc)-timedelta(hours=7) if age == 100 else None)
        for year in (2021, 2022, 2023, 2024): self.add(f'old-{year}', year)
        selected = queue_plan.city_catchup_candidates(self.db, rotation=0, limit=6,
                    recent_since=today-timedelta(days=365))
        self.assertEqual(selected[0][0], 'https://www.dane.gov.co/files/gap-100.zip')
        self.assertEqual(len(selected), 6)
        self.assertEqual(len({row[0] for row in selected}), 6)
        self.assertIn('old-2021', [row[0] for row in selected])

    def test_recent_priority_excludes_current_mutable_lane_and_ineligible_assets(self):
        today = self.db.execute("SELECT (clock_timestamp() AT TIME ZONE 'America/Bogota')::date").fetchone()[0]
        specs = [('latest', 1, 'pending', None, 'city-zip'),
                 ('boundary', 3, 'pending', None, 'city-zip'),
                 ('future', -1, 'pending', None, 'city-zip'),
                 ('too-old', 366, 'pending', None, 'city-zip'),
                 ('review', 100, 'review', None, 'city-zip'),
                 ('complete', 100, 'complete', None, 'city-zip'),
                 ('failed', 100, 'failed', None, 'city-zip'),
                 ('cooldown', 100, 'pending', datetime.now(timezone.utc), 'city-zip'),
                 ('other-kind', 100, 'pending', None, 'daily-pdf'),
                 ('excluded', 120, 'pending', None, 'city-zip'),
                 ('eligible', 110, 'pending', None, 'city-zip')]
        for label, age, status, checked, kind in specs:
            day = today-timedelta(days=age)
            self.add('https://www.dane.gov.co/files/'+label+'.zip', day.year,
                     month=day.month, day=day.day, status=status, checked=checked, kind=kind)
        self.add('https://untrusted.example/older.zip', today.year, month=1)
        selected = queue_plan.city_catchup_candidates(self.db, rotation=0,
                    recent_since=today-timedelta(days=365),
                    exclude_urls=['https://www.dane.gov.co/files/excluded.zip'])
        self.assertEqual(selected[0][0], 'https://www.dane.gov.co/files/eligible.zip')

    def test_no_recent_gap_preserves_existing_year_and_retry_order(self):
        today = self.db.execute("SELECT (clock_timestamp() AT TIME ZONE 'America/Bogota')::date").fetchone()[0]
        self.add('old-never', 2021)
        self.add('old-retry', 2020, checked=datetime.now(timezone.utc)-timedelta(hours=7))
        ordinary = queue_plan.city_catchup_candidates(self.db, rotation=1)
        reserved = queue_plan.city_catchup_candidates(self.db, rotation=1,
                    recent_since=today-timedelta(days=365))
        self.assertEqual(ordinary, reserved)

    def test_single_available_slot_alternates_recent_and_old_without_extra_work(self):
        today = self.db.execute("SELECT (clock_timestamp() AT TIME ZONE 'America/Bogota')::date").fetchone()[0]
        day = today-timedelta(days=100)
        self.add('https://www.dane.gov.co/files/recent.zip', day.year,
                 month=day.month, day=day.day)
        self.add('old-never', 2021)
        recent = queue_plan.city_catchup_candidates(self.db, rotation=0, limit=1,
                    recent_since=today-timedelta(days=365))
        old = queue_plan.city_catchup_candidates(self.db, rotation=1, limit=1,
                    recent_since=today-timedelta(days=365))
        self.assertEqual([r[0] for r in recent], ['https://www.dane.gov.co/files/recent.zip'])
        self.assertEqual([r[0] for r in old], ['old-never'])

    def test_changed_zip_member_bytes_get_distinct_existing_resume_step(self):
        from pipelines.ingestion.city_reports import _member_step

        def member(payload):
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w') as z:
                z.writestr('Barranquilla.pdf',payload)
            with zipfile.ZipFile(io.BytesIO(data.getvalue())) as z:
                return z.infolist()[0]

        self.assertNotEqual(_member_step(member(b'old readable grid'),date(2022,1,3)),
                            _member_step(member(b'new readable grid'),date(2022,1,3)))

    def test_due_retry_keeps_separate_year_rotation_even_after_429(self):
        self.add('2021-old',2021)
        self.add('2022-old',2022)
        self.add('publisher-429',2020,checked='2026-01-01T00:00:00Z')
        selected=queue_plan.city_catchup_candidates(self.db,rotation=1)
        self.assertEqual([x[0] for x in selected],['2022-old','publisher-429'])
        # Selection does not perform source HTTP or alter the failed asset:
        # the worker's existing HOST_COOLDOWNS gate still defers it.
        checked=self.db.execute("SELECT checked_at FROM ingestion_asset WHERE url='publisher-429'").fetchone()[0]
        self.assertEqual(checked.astimezone(timezone.utc).year,2026)

    def test_completed_v6_parent_is_outdated_for_existing_v7_backfill(self):
        self.db.execute(
            "ALTER TABLE ingestion_asset ADD COLUMN error text, "
            "ADD COLUMN processor_version text, ADD COLUMN discovered_at timestamptz, "
            "ADD COLUMN document_id text"
        )
        self.db.execute(
            "CREATE TEMP TABLE official_source_review(document_id text,parser_version text,"
            "source_locator text,record jsonb)"
        )
        self.add('old-complete',2021,status='complete',checked='2026-10-05T03:00:00Z')
        self.add('current-complete',2022,status='complete',checked='2026-10-05T03:00:00Z')
        self.db.execute(
            "UPDATE ingestion_asset SET processor_version=CASE WHEN url='old-complete' "
            "THEN 'city-v7' ELSE 'city-v8' END, discovered_at=now()"
        )
        self.assertEqual(worker.parser_version('city-zip'), 'city-v8')
        selected = queue_plan.backfill_candidates(self.db, 100)
        self.assertIn('old-complete', [row[0] for row in selected])
        self.assertNotIn('current-complete', [row[0] for row in selected])


class WorkerCityLane(unittest.TestCase):
    def run_case(self, *, limit=100, budget=200, repair=(), historical=(), city=(),
                 recent=(), fresh=(), backlog=(), advance=None, defer=None,
                 blocked_host=False, process_callback=None, elapsed_by_url=None,
                 sql_capture=None):
        clock=[0.0]
        observed=[]
        advance_urls={advance} if isinstance(advance,str) else set(advance or ())
        elapsed_by_url=elapsed_by_url or {}
        db=MagicMock()
        def execute(sql,*args):
            if sql_capture is not None:sql_capture.append((sql,args))
            result=MagicMock()
            result.fetchone.return_value=(True,)
            return result
        db.execute.side_effect=execute
        def process(_db,url,kind,day):
            observed.append((url,kind,worker.RUN_DEADLINE.get(),clock[0]))
            if process_callback is not None:
                return process_callback(url, kind, day)
            if url==defer:
                clock[0]=worker.RUN_DEADLINE.get()
                raise WorkDeferred('Committed city member will resume')
            clock[0]+=elapsed_by_url.get(url,0)
            if url in advance_urls:
                clock[0]=worker.RUN_DEADLINE.get()
            return 1
        with (
            patch.object(worker,'connect') as connect,
            patch.object(worker,'refresh_catalog',return_value={}),
            patch.object(worker,'HostCooldowns') as host_type,
            patch.object(worker,'retained_reparse_during_host_cooldown',return_value=False),
            patch.object(worker.time,'monotonic',side_effect=lambda:clock[0]),
            patch.object(worker,'process_asset',side_effect=process),
            patch.object(queue_plan,'supply_validation_retry',return_value=[]),
            patch.object(queue_plan,'repair_candidates',return_value=list(repair)),
            patch.object(queue_plan,'historical_candidates',return_value=list(historical)),
            patch.object(queue_plan,'city_catchup_candidates',side_effect=lambda _db, *, exclude_urls, limit, recent_since:
                         [row for row in city if row[0] not in exclude_urls][:limit]) as city_selector,
            patch.object(queue_plan,'recent_pending_daily_pdf_candidates',return_value=list(recent)),
            patch.object(queue_plan,'daily_candidates',return_value=list(fresh)),
            patch.object(queue_plan,'current_dane_candidates',return_value=[]),
            patch.object(queue_plan,'backfill_candidates',return_value=list(backlog)),
            patch('pipelines.ingestion.label_normalization.drain',
                  return_value={'available':True,'deferred':False}),
            patch('pipelines.ingestion.city_product_backfill.drain',
                  return_value={'selected':0,'completed':0,'errors':[]}),
            patch('pipelines.ingestion.retained_replays.drain',return_value={}),
            patch('pipelines.ingestion.ocr.drain',return_value={}),
        ):
            connect.return_value.__enter__.return_value=db
            host_type.return_value.blocked.side_effect=(
                lambda url:datetime.now(timezone.utc)+timedelta(hours=1)
                if blocked_host and url.startswith('https://www.dane.gov.co/') else None)
            result=worker.run('backfill',limit=limit,time_budget=budget)
        self.assertIsNone(worker.RUN_DEADLINE.get())
        return result,observed,city_selector

    def test_recent_city_gets_bounded_window_before_a_slow_historical_repair(self):
        recent_day = worker.today()-timedelta(days=100)
        city=[('recent-city','city-zip',recent_day),
              ('old-city','city-zip',date(2021,1,3))]
        result,obs,selector=self.run_case(city=city,
            repair=[('slow-repair','dane-weekly-pdf',date(2013,5,24))],
            advance={'recent-city','slow-repair'})
        self.assertEqual([x[0] for x in obs], ['recent-city','slow-repair'])
        self.assertEqual([x[2] for x in obs], [90,200])
        self.assertEqual(result['city_catchup_lane']['recent_priority'], ['recent-city'])
        self.assertEqual(selector.call_args.kwargs['recent_since'],
                         worker.today()-timedelta(days=365))
        self.assertTrue(result['time_budget_reached'])

    def test_recent_and_historical_city_keep_bounded_first_occurrence(self):
        recent=('recent-city','city-zip',worker.today()-timedelta(days=100))
        old=('old-city','city-zip',date(2021,1,3))
        result,obs,_=self.run_case(city=[recent,old],fresh=[recent,old],budget=300)
        self.assertEqual([x[0] for x in obs], ['recent-city','old-city'])
        self.assertEqual([x[2] for x in obs], [90,90])
        self.assertEqual(result['assets'], 2)

    def test_two_city_slots_precede_large_fresh_and_reset_deadline(self):
        city=(('zip-2022','city-zip',date(2022,1,3)),
              ('zip-retry','city-zip',date(2021,8,6)))
        result,obs,sel=self.run_case(city=city,
            fresh=[('huge-fresh','supply',date(2026,10,4))],
            backlog=[('later','daily',date(2020,1,1))],advance='huge-fresh')
        self.assertEqual([x[0] for x in obs],['zip-2022','zip-retry','huge-fresh'])
        self.assertEqual([x[2] for x in obs],[90,90,200])
        self.assertEqual(len(result['city_catchup_lane']['selected']),2)
        sel.assert_called_once()
        self.assertTrue(result['time_budget_reached'])

    def test_opt_in_six_uses_bounded_slots_and_keeps_recent_and_fresh(self):
        city=[(f'city-{i}','city-zip',date(2022,i,1)) for i in range(1,7)]
        with patch.dict(os.environ,{'AGRO_CITY_CATCHUP_SLOTS':'6'}):
            result,obs,selector=self.run_case(budget=2100,city=city,
                recent=[('recent','daily-pdf',date(2026,10,4))],
                fresh=[('fresh','daily',date(2026,10,5))])
        self.assertEqual(selector.call_args.kwargs['limit'],6)
        self.assertEqual([x[0] for x in obs],
                         [f'city-{i}' for i in range(1,7)]+['recent','fresh'])
        self.assertEqual(result['city_catchup_lane']['configured_slots'],6)
        self.assertEqual(result['city_catchup_lane']['time_reserved_skips'],[])

    def test_slow_prior_work_skips_city_without_marking_checked_and_reaches_later(self):
        city=[(f'city-{i}','city-zip',date(2022,i,1)) for i in range(1,5)]
        statements=[]
        with patch.dict(os.environ,{'AGRO_CITY_CATCHUP_SLOTS':'6'}):
            result,obs,selector=self.run_case(budget=900,
                repair=[('repair','daily-pdf',date(2020,1,1))],city=city,
                recent=[('recent','daily-pdf',date(2026,10,4))],
                fresh=[('fresh','daily',date(2026,10,5))],
                elapsed_by_url={'repair':400},advance={'city-1','city-2'},
                sql_capture=statements)
        self.assertEqual(selector.call_args.kwargs['limit'],4)
        self.assertEqual([x[0] for x in obs],['repair','city-1','city-2','recent','fresh'])
        self.assertEqual(result['city_catchup_lane']['time_reserved_skips'],['city-3','city-4'])
        self.assertEqual(result['assets'],5)
        checked_urls=[args[0][0] for sql,args in statements
            if sql.startswith('UPDATE ingestion_asset SET checked_at=now()')]
        self.assertNotIn('city-3',checked_urls)
        self.assertNotIn('city-4',checked_urls)

    def test_opt_in_cooldown_does_not_fetch_and_fresh_proceeds(self):
        blocked='https://www.dane.gov.co/files/sipsa-03-01-2022.zip'
        with patch.dict(os.environ,{'AGRO_CITY_CATCHUP_SLOTS':'4'}):
            result,obs,_=self.run_case(budget=2100,blocked_host=True,
                city=[(blocked,'city-zip',date(2022,1,3))],
                fresh=[('fresh','daily',date(2026,10,5))])
        self.assertEqual([x[0] for x in obs],['fresh'])
        self.assertEqual(result['deferred_hosts']['www.dane.gov.co']['count'],1)

    def test_small_global_cap_preserves_later_slot_when_opted_in(self):
        with patch.dict(os.environ,{'AGRO_CITY_CATCHUP_SLOTS':'6'}):
            result,obs,selector=self.run_case(limit=2,budget=2100,
                city=[('city','city-zip',date(2022,1,3))],
                fresh=[('fresh','daily',date(2026,10,5))])
        self.assertEqual(selector.call_args.kwargs['limit'],1)
        self.assertEqual([x[0] for x in obs],['city','fresh'])
        self.assertEqual(result['assets'],2)

    def test_global_cap_one_two_and_large_remains_unchanged(self):
        city=(('zip-a','city-zip',date(2022,1,3)),('zip-b','city-zip',date(2021,8,6)))
        for cap,expected in ((1,['zip-a']),(2,['zip-a','zip-b']),
                             (150,['zip-a','zip-b','fresh'])):
            with self.subTest(cap=cap):
                result,obs,_=self.run_case(limit=cap,city=city,
                    fresh=[('fresh','daily',date(2026,10,4))])
                self.assertEqual([x[0] for x in obs],expected)
                self.assertEqual(result['assets'],len(expected))

    def test_duplicate_earlier_priority_owns_first_budget(self):
        result,obs,selector=self.run_case(
            repair=[('same','city-zip',date(2021,1,1))],
            historical=[('old','city-zip',date(2020,1,1))],
            city=[('same','city-zip',date(2021,1,1)),
                  ('old','city-zip',date(2020,1,1)),
                  ('gap','city-zip',date(2022,1,3))],
            fresh=[('gap','city-zip',date(2022,1,3))])
        self.assertEqual([x[0] for x in obs],['same','old','gap'])
        self.assertEqual([x[2] for x in obs],[200,90,90])
        self.assertEqual(result['assets'],3)
        self.assertEqual(selector.call_args.kwargs['exclude_urls'],{'same','old'})

    def test_deferred_city_resumes_next_run_and_parent_ceiling(self):
        result,obs,_=self.run_case(city=[('gap','city-zip',date(2022,1,3))],
            fresh=[('fresh','daily',date(2026,10,4))],defer='gap')
        self.assertEqual([x[0] for x in obs],['gap','fresh'])
        self.assertEqual([x[2] for x in obs],[90,200])
        self.assertEqual([x['url'] for x in result['deferred']],['gap'])
        result,obs,_=self.run_case(budget=60,city=[('gap','city-zip',date(2022,1,3))])
        self.assertEqual(obs[0][2],60)

    def test_host_429_cooldown_skips_city_without_process_or_http(self):
        url='https://www.dane.gov.co/files/sipsa-03-01-2022.zip'
        result,obs,_=self.run_case(city=[(url,'city-zip',date(2022,1,3))],
            fresh=[('other-host','daily',date(2026,10,4))],blocked_host=True)
        self.assertEqual([x[0] for x in obs],['other-host'])
        self.assertEqual(result['assets'],1)
        self.assertEqual(result['deferred_hosts']['www.dane.gov.co']['count'],1)



if __name__ == '__main__':
    unittest.main()
