"""Bounded public HTTP fetching, robots checks and retry/backoff reporting."""
import ipaddress
import random
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .content import allowed

USER_AGENT = 'AgroAmigoNewsResearch/1.0'

class FetchError(Exception):
    def __init__(self, code, retry_after=0):
        self.code, self.retry_after = code, retry_after
        super().__init__(code)

@dataclass
class Page:
    url: str
    status: int
    text: str
    etag: str | None = None
    last_modified: str | None = None

class Fetcher:
    def __init__(self, timeout=15, max_bytes=2_000_000, retries=2, min_interval=1.0):
        self.timeout, self.max_bytes, self.retries = timeout, max_bytes, retries
        self.min_interval = min_interval
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT, 'Accept-Language': 'es,en;q=0.1'})
        self.robots, self.last_request, self.blocked_until = {}, {}, {}

    def close(self):
        self.session.close()

    def check_url(self, url, source):
        if not allowed(url, source): raise FetchError('host_or_language_path_not_allowed')
        try:
            addresses = socket.getaddrinfo(urlsplit(url).hostname, None)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise FetchError('non_public_destination')
        except socket.gaierror:
            raise FetchError('dns_unavailable') from None

    def _request(self, url, source, headers=None, delay=None, redirects=0, check_robots=False):
        if redirects > 4: raise FetchError('redirect_limit')
        self.check_url(url, source)
        host = urlsplit(url).hostname
        if self.blocked_until.get(host, 0) > time.time():
            raise FetchError('host_backoff', self.blocked_until[host]-time.time())
        delay = max(self.min_interval, delay or 0)
        if delay > 10: raise FetchError('crawl_delay_exceeds_run_budget', delay)
        for attempt in range(self.retries+1):
            pause = delay - (time.monotonic()-self.last_request.get(host, 0))
            if pause > 0: time.sleep(pause)
            self.last_request[host] = time.monotonic()
            try:
                response = self.session.get(url, headers=headers, timeout=(self.timeout, self.timeout), allow_redirects=False, stream=True)
            except requests.RequestException:
                if attempt < self.retries:
                    time.sleep(2**attempt + random.random()); continue
                raise FetchError('network_or_timeout') from None
            with response:
                if response.status_code in (301, 302, 303, 307, 308):
                    target = urljoin(url, response.headers.get('Location', ''))
                    self.check_url(target, source)
                    if check_robots:
                        delay = self._permission(target, source)
                    return self._request(target, source, headers, delay, redirects+1, check_robots)
                if response.status_code == 429:
                    value = response.headers.get('Retry-After', '300')
                    try: retry = float(value)
                    except ValueError:
                        try: retry = (parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds()
                        except (ValueError, TypeError): retry = 300
                    retry = max(60, retry)
                    self.blocked_until[host] = time.time()+retry
                    raise FetchError('rate_limited', retry)
                if response.status_code >= 500:
                    if attempt < self.retries:
                        time.sleep(2**attempt + random.random()); continue
                    raise FetchError('upstream_unavailable')
                if response.status_code in (401, 403): raise FetchError('access_restricted')
                if response.status_code == 304: return Page(url, 304, '')
                if response.status_code != 200: raise FetchError('http_'+str(response.status_code))
                mime = response.headers.get('Content-Type', '').lower()
                if not any(x in mime for x in ('html', 'xml', 'text/plain')):
                    raise FetchError('unsupported_content_type')
                size, chunks = 0, []
                for chunk in response.iter_content(16384):
                    size += len(chunk)
                    if size > self.max_bytes: raise FetchError('response_too_large')
                    chunks.append(chunk)
                raw = b''.join(chunks)
                encoding = response.encoding
                if not encoding or encoding.lower() == 'iso-8859-1': encoding = 'utf-8'
                return Page(url, 200, raw.decode(encoding, errors='replace'), response.headers.get('ETag'), response.headers.get('Last-Modified'))
        raise FetchError('retry_limit')

    def _permission(self, url, source):
        if not source['enabled'] or source['access_policy'] == 'permission_required':
            raise FetchError('source_disabled_or_permission_required')
        u = urlsplit(url)
        origin = f'{u.scheme}://{u.netloc}'
        if origin not in self.robots:
            parser = RobotFileParser()
            try:
                page = self._request(origin+'/robots.txt', source)
                # Login/HTML error pages are not a valid robots policy.
                if '<html' in page.text.lower(): raise FetchError('robots_unverified')
                parser.parse(page.text.splitlines())
            except FetchError as exc:
                if exc.code == 'http_404': parser.parse(['User-agent: *', 'Allow: /'])
                else:
                    self.robots[origin] = None
                    raise FetchError('robots_'+exc.code, exc.retry_after) from None
            self.robots[origin] = parser
        parser = self.robots[origin]
        if parser is None: raise FetchError('robots_unverified')
        if not parser.can_fetch(USER_AGENT, url): raise FetchError('robots_disallowed')
        return parser.crawl_delay(USER_AGENT) or parser.crawl_delay('*') or 0

    def fetch(self, url, source, etag=None, last_modified=None):
        self.check_url(url, source)
        delay = self._permission(url, source)
        headers = {}
        if etag: headers['If-None-Match'] = etag
        if last_modified: headers['If-Modified-Since'] = last_modified
        return self._request(url, source, headers, delay=delay, check_robots=True)
