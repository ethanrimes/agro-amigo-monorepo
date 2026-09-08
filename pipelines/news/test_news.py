import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from .cli import assess, apply_reviews, config
from .content import date_value, discover, diverse, expiry, extract, spanish, topics
from .state import State
from .transport import FetchError, Fetcher

SOURCE=dict(id='test',name='Fuente',allowed_hosts=['example.org'],timezone='America/Bogota',
    enabled=True,access_policy='check_access_terms_on_run',group='regional',publisher_id='owner',public_display_rights='unverified')
SPANISH=('Los agricultores colombianos informaron que la cosecha de café mantiene su producción. '
         'Los precios de los fertilizantes y las condiciones del transporte afectan los costos de los cultivos. '
         'La investigación describe cambios en los mercados internacionales y recomienda consultar las fuentes oficiales antes de tomar decisiones.')
ENGLISH=('Farmers reported that the coffee harvest remains stable this year. Fertilizer prices and shipping conditions affect crop production costs. '
         'The research describes changes in international agricultural markets and recommends consulting official sources before making decisions. '
         'Growers should monitor changes in supply and demand across the international market.')

def article(date='2026-09-04',body=SPANISH,lang='es',extra=''):
    return f'<html lang="{lang}"><head><meta property="article:published_time" content="{date}">{extra}</head><body><header>8 septiembre 2026</header><article><h1>Mercados y producción de café</h1><p>{body}</p></article></body></html>'

def record():
    end=datetime(2026,9,8,tzinfo=timezone.utc)
    return assess(extract(article(),'https://example.org/noticia',SOURCE),SOURCE,end-timedelta(days=14),end)

def review(r):
    return dict(id=r['id'],content_sha256=r['content_sha256'],decision='include',
        primary_category='precios_y_mercados',story_kind='market_trend',crops=['café'],inputs=[],
        factual_label_es='La publicación informa sobre la producción de café y los precios de los fertilizantes en los mercados internacionales.',
        colombia_relevance_es='Estos cambios podrían afectar los costos de productores colombianos. Conviene comparar las referencias con las cotizaciones locales antes de decidir una compra.',
        impact_is_inference=True,transmission_channel='comercio')

class ExtractionTests(unittest.TestCase):
    def test_canada_is_not_sugar_cane(self):
        self.assertEqual(topics('Ecuador exporta mango hacia Canadá')['crops'],['mango'])
        self.assertIn('caña de azúcar',topics('Cultivadores de caña y cañaverales')['crops'])

    def test_explicit_agrosavia_date_with_leading_month(self):
        self.assertEqual(date_value('Julio 29, 2026')['value'],'2026-07-29T00:00:00-05:00')

    def test_masthead_does_not_become_publication(self):
        html='<html lang="es"><header>7 septiembre 2026</header><article><h1>Café en Colombia</h1><p>'+SPANISH+'</p></article></html>'
        self.assertIsNone(extract(html,'https://example.org/article',SOURCE)['published_at'])

    def test_language_independent_of_spanish_masthead(self):
        self.assertTrue(spanish(SPANISH,'en')['accepted'])
        self.assertFalse(spanish(ENGLISH,'es')['accepted'])
        self.assertFalse(spanish('Precios del café','es')['accepted'])

    def test_updated_date_is_not_publication(self):
        html=article('2026-07-12',extra='<meta property="article:modified_time" content="2026-09-04T10:00:00-05:00">')
        r=extract(html,'https://example.org/a',SOURCE)
        self.assertTrue(r['published_at'].startswith('2026-07-12'))
        self.assertTrue(r['updated_at'].startswith('2026-09-04'))

    def test_conflicting_original_dates_go_to_review(self):
        ld={'@type':'NewsArticle','headline':'Mercados y producción de café','datePublished':'2026-09-05'}
        r=extract(article(extra='<script type="application/ld+json">'+json.dumps(ld)+'</script>'),'https://example.org/a',SOURCE)
        self.assertTrue(r['date_conflict']);self.assertIsNone(r['published_at'])

    def test_event_date_not_used(self):
        html='<html><article><h1>Capacitación de café</h1><p>'+SPANISH+' El evento será el 15 de septiembre de 2026.</p></article></html>'
        self.assertIsNone(extract(html,'https://example.org/a',SOURCE)['published_at'])

    def test_spanish_date_and_invalid_date(self):
        self.assertEqual(date_value('mar. 1 sept. 2026')['value'],'2026-09-01T00:00:00-05:00')
        self.assertIsNone(date_value('31/02/2026'))
        self.assertIsNone(date_value('durante el año 2026'))

    def test_date_only_and_offsets(self):
        self.assertTrue(date_value('2026-09-04')['timezone_assumed'])
        self.assertFalse(date_value('2026-09-04T10:00:00+02:00')['timezone_assumed'])

    def test_rss_and_atom_are_only_discovery_hints(self):
        for xml in ['<rss><channel><item><title>Producción de café</title><link>https://example.org/a?utm_source=feed</link><pubDate>Fri, 04 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>',
                    '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Producción de café</title><link href="https://example.org/a"/><published>2026-09-04</published></entry></feed>']:
            entries,_,_=discover(xml,'https://example.org/feed',SOURCE)
            self.assertEqual(entries[0]['url'],'https://example.org/a')
            self.assertIn('listing_date_hint',entries[0]);self.assertNotIn('published_at',entries[0])

    def test_xml_entities_rejected(self):
        with self.assertRaises(ValueError):
            discover('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><rss/>','https://example.org/feed',SOURCE)

    def test_html_system_font_does_not_trigger_xml_block(self):
        entries,_,_=discover('<!DOCTYPE html><html><style>body{font:system-ui}</style><a href="/cafe">La producción de café colombiano crece</a></html>','https://example.org',SOURCE)
        self.assertEqual(len(entries),1)

    def test_explicit_publication_time_in_article_footer(self):
        html='<html lang="es"><body><article><h1>Exportaciones de mango</h1><p>'+SPANISH+'</p><footer>Fecha de publicación: <time datetime="2026-09-01T15:19:00.0000000" itemprop="datePublished">mar. 1 sept. 2026</time></footer></article></body></html>'
        self.assertTrue(extract(html,'https://example.org/a',SOURCE)['published_at'].startswith('2026-09-01'))

    def test_visible_date_conflicts_with_earlier_creation_metadata(self):
        source=dict(SOURCE,publication_date_selector='.publication-date')
        html=article('2026-09-01T10:23:54+02:00').replace('</article>','<div class="publication-date">3 de septiembre de 2026</div></article>')
        result=extract(html,'https://example.org/a',source)
        self.assertTrue(result['date_conflict']);self.assertIsNone(result['published_at'])

    def test_global_story_without_colombia_is_candidate(self):
        text=SPANISH.replace('colombianos','ecuatorianos')
        r=extract(article(body=text),'https://example.org/a',SOURCE)
        self.assertEqual(r['relevance_kind'],'indirect')

    def test_cross_host_canonical_is_ignored(self):
        r=extract(article(extra='<link rel="canonical" href="http://127.0.0.1/secret">'),'https://example.org/a',SOURCE)
        self.assertEqual(r['canonical_url'],'https://example.org/a')

class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=State(Path(self.tmp.name)/'state.sqlite3')
    def tearDown(self): self.state.close();self.tmp.cleanup()

    def test_rerun_deduplicates_and_preserves_publication(self):
        first=self.state.upsert('test',record())
        r=record();r['published_at']='2026-09-05T00:00:00-05:00'
        second=self.state.upsert('test',r)
        self.assertEqual(first['published_at'],second['published_at'])
        self.assertEqual(first['first_seen_at'],second['first_seen_at'])
        self.assertEqual(len(self.state.stories()),1)

    def test_changed_content_revokes_previous_acceptance(self):
        r=self.state.upsert('test',record());r.update(decision='include',status='active')
        self.state.save('test',r)
        newer=record();newer['content_sha256']='changed'
        r=self.state.upsert('test',newer)
        self.assertEqual(r['decision'],'review')
        self.assertEqual(self.state.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0],1)

    def test_successful_listing_keeps_article_backlog(self):
        self.state.enqueue('test',[dict(url='https://example.org/a')])
        self.state.finish_source('test',True,{},'2026-09-04T00:00:00+00:00')
        self.assertEqual(self.state.pending('test',5),['https://example.org/a'])
        self.state.candidate_result('https://example.org/a','error',3600)
        self.assertEqual(self.state.pending('test',5),[])
        self.assertEqual(self.state.backlog('test'),1)

    def test_failed_source_never_advances_watermark(self):
        self.state.finish_source('test',True,{},'2026-09-01T00:00:00+00:00')
        self.state.finish_source('test',False,{},'2026-09-05T00:00:00+00:00')
        self.assertEqual(self.state.checkpoint('test'),'2026-09-01T00:00:00+00:00')

    def test_overlapping_runs_are_rejected(self):
        with self.state.lock():
            with self.assertRaises(RuntimeError):
                with self.state.lock(): pass

    def test_stale_classification_cannot_include(self):
        r=self.state.upsert('test',record())
        with self.assertRaises(ValueError):
            apply_reviews(self.state,[dict(id=r['id'],content_sha256='wrong',decision='include')],'test')

    def test_reviewed_tags_and_expiry_survive_unchanged_retrieval(self):
        r=self.state.upsert('test',record())
        apply_reviews(self.state,[review(r)],'human-test-reviewer')
        first=self.state.stories()[0]
        again=self.state.upsert('test',record())
        self.assertEqual(again['crops'],['café'])
        self.assertEqual(again['inputs'],[])
        self.assertEqual(again['primary_category'],'precios_y_mercados')
        self.assertEqual(again['display_expires_at'],first['display_expires_at'])
        self.assertEqual(again['classification_method'],'reviewed_handoff')

    def test_review_bundle_is_atomic(self):
        r=self.state.upsert('test',record())
        with self.assertRaises(ValueError):
            apply_reviews(self.state,[review(r),dict(id='missing')],'test')
        self.assertEqual(self.state.stories()[0]['decision'],'review')

    def test_changed_headline_revokes_acceptance(self):
        r=self.state.upsert('test',record());apply_reviews(self.state,[review(r)],'test')
        changed=record();changed['headline_sha256']='new'
        self.assertEqual(self.state.upsert('test',changed)['decision'],'review')

    def test_expired_stories_do_not_consume_recheck_budget(self):
        r=self.state.upsert('test',record())
        r.update(decision='include',status='active',review_at='2000-01-01T00:00:00+00:00',
                 display_expires_at='2000-01-02T00:00:00+00:00')
        self.state.save('test',r)
        self.assertEqual(self.state.rechecks('test',10),[])

    def test_host_cooldown_survives_process_restart(self):
        self.state.save_backoffs({'example.org':9999999999})
        other=State(Path(self.tmp.name)/'state.sqlite3')
        try: self.assertEqual(other.backoffs()['example.org'],9999999999)
        finally: other.close()

class TransportTests(unittest.TestCase):
    @staticmethod
    def response(status,headers=None,body=b''):
        import requests
        r=requests.Response();r.status_code=status;r.headers.update(headers or {})
        r._content=body;r._content_consumed=True
        return r

    def setUp(self): self.fetcher=Fetcher(retries=0,min_interval=0)
    def tearDown(self): self.fetcher.close()

    def test_robots_disallow_prevents_article_request(self):
        response=self.response(200,{'Content-Type':'text/plain'},b'User-agent: *\nDisallow: /private\n')
        with patch.object(self.fetcher,'check_url'),patch.object(self.fetcher.session,'get',return_value=response) as get:
            with self.assertRaisesRegex(FetchError,'robots_disallowed'):
                self.fetcher.fetch('https://example.org/private/article',SOURCE)
            self.assertEqual(get.call_count,1)

    def test_rate_limit_stops_subsequent_host_requests(self):
        response=self.response(429,{'Retry-After':'7200'})
        with patch.object(self.fetcher,'check_url'),patch.object(self.fetcher.session,'get',return_value=response) as get:
            with self.assertRaisesRegex(FetchError,'rate_limited'):
                self.fetcher._request('https://example.org/a',SOURCE)
            with self.assertRaisesRegex(FetchError,'host_backoff'):
                self.fetcher._request('https://example.org/b',SOURCE)
            self.assertEqual(get.call_count,1)

    def test_redirect_cannot_escape_source_allowlist(self):
        response=self.response(302,{'Location':'http://127.0.0.1/private'})
        public_address=[(2,1,6,'',('93.184.216.34',0))]
        with patch('socket.getaddrinfo',return_value=public_address),patch.object(self.fetcher.session,'get',return_value=response) as get:
            with self.assertRaisesRegex(FetchError,'host_or_language_path_not_allowed'):
                self.fetcher._request('https://example.org/a',SOURCE)
            self.assertEqual(get.call_count,1)

class FeedTests(unittest.TestCase):
    def test_expiry_anchored_to_publication(self):
        e,_=expiry('2026-09-01T00:00:00-05:00','spot_price')
        self.assertEqual(e,'2026-09-03T00:00:00-05:00')

    def test_monthly_reference_is_not_two_day_weather_alert(self):
        e,review=expiry('2026-09-01T00:00:00-05:00','seasonal_outlook')
        self.assertEqual(e,'2026-09-15T00:00:00-05:00')
        self.assertEqual(review,'2026-09-02T00:00:00-05:00')

    def test_explicit_earlier_deadline(self):
        e,_=expiry('2026-09-01T00:00:00-05:00','event','2026-09-06T23:59:59-05:00')
        self.assertEqual(e,'2026-09-06T23:59:59-05:00')

    def test_home_diversity_caps_owner_and_same_event(self):
        records=[dict(id=str(i),source_group=str(i%3),publisher_id='same' if i<4 else str(i),priority=100-i,published_at='2026-09-01',event_id='event' if i in (0,4) else str(i)) for i in range(9)]
        result=diverse(records,5,2)
        self.assertEqual(len(result),5)
        self.assertLessEqual(sum(s['publisher_id']=='same' for s in result),2)
        self.assertEqual(len({s['event_id'] for s in result}),5)

    def test_catalog_spanish_and_restricted_sources_disabled(self):
        data=config(Path(__file__).with_name('sources.json'))
        self.assertGreaterEqual(len(data['sources']),90)
        self.assertTrue(all(s['language']=='es' for s in data['sources']))
        self.assertTrue(all(not s['enabled'] for s in data['sources'] if s['access_policy']=='permission_required'))

    def test_private_network_is_rejected_before_fetch(self):
        fetcher=Fetcher()
        source=dict(SOURCE,allowed_hosts=['127.0.0.1'])
        with self.assertRaises(FetchError): fetcher.check_url('http://127.0.0.1/',source)
        fetcher.close()

if __name__=='__main__': unittest.main()
