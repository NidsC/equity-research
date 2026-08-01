"""SEC EDGAR client.

EDGAR is free and unauthenticated. The two hard rules are a descriptive
User-Agent header identifying you (email included) and a ceiling of 10
requests/second per IP.

Rate limiting here is deliberately conservative and has two independent layers:

  1. A token bucket — 4 requests per 2 seconds sustained, burst of 4. This is
     the throttle that actually paces traffic.
  2. A tripwire at 8 observed requests/second that latches permanently. The
     bucket makes 8/s unreachable, so if the tripwire ever fires it means the
     throttle has been bypassed — a second limiter instance, a direct httpx
     call, a bug. At that point the safe move is to stop the application dead
     rather than keep going and earn an IP ban.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import httpx

SEC_HOST = "https://www.sec.gov"
DATA_HOST = "https://data.sec.gov"
TICKER_MAP_URL = f"{SEC_HOST}/files/company_tickers.json"

# Sustained throughput: 4 requests per 2 seconds (2/s average, burst of 4).
SUSTAINED_REQUESTS = 4
SUSTAINED_WINDOW_SECONDS = 2.0

# Tripwire. SEC's hard ceiling is 10/s; we abort at 8/s, which the bucket above
# should make unreachable. Firing this is an invariant violation, not a hint.
TRIPWIRE_REQUESTS_PER_SECOND = 8

CACHE_DIR = Path(os.environ.get("ER_CACHE_DIR", "data/cache"))


class EdgarError(RuntimeError):
    pass


class RateLimitTripwire(BaseException):
    """The observed request rate exceeded the tripwire; the client is dead.

    Deliberately inherits from BaseException, not Exception. This must not be
    swallowed by a broad ``except Exception`` in a retry loop or a worker pool —
    the whole point is that the application stops making requests.
    """


def _user_agent() -> str:
    ua = os.environ.get("EDGAR_USER_AGENT")
    if not ua:
        raise EdgarError(
            "EDGAR_USER_AGENT is not set. The SEC requires a descriptive User-Agent "
            'identifying you, e.g. EDGAR_USER_AGENT="Equity Research yourname@example.com"'
        )
    return ua


class _RateLimiter:
    """Token bucket with a latching tripwire, safe across threads.

    The bucket holds ``capacity`` tokens and refills at ``capacity / window``
    tokens per second. Every grant is timestamped; if the number of grants
    inside any one-second window reaches the tripwire, the limiter latches
    permanently and every subsequent acquire raises.
    """

    def __init__(
        self,
        capacity: int = SUSTAINED_REQUESTS,
        window_seconds: float = SUSTAINED_WINDOW_SECONDS,
        tripwire_per_second: int = TRIPWIRE_REQUESTS_PER_SECOND,
    ) -> None:
        self._capacity = float(capacity)
        self._refill_per_second = capacity / window_seconds
        self._tripwire = tripwire_per_second

        self._lock = threading.Lock()
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._grants: deque[float] = deque()
        self._tripped: str | None = None

    @property
    def tripped(self) -> bool:
        return self._tripped is not None

    def reset(self) -> None:
        """Clear the latch. For tests only — never call this to 'recover'."""
        with self._lock:
            self._tokens = self._capacity
            self._last_refill = time.monotonic()
            self._grants.clear()
            self._tripped = None

    def acquire(self) -> None:
        with self._lock:
            if self._tripped is not None:
                raise RateLimitTripwire(self._tripped)

            # Refill, then wait for a token if the bucket is dry.
            now = time.monotonic()
            self._tokens = min(
                self._capacity,
                self._tokens + (now - self._last_refill) * self._refill_per_second,
            )
            self._last_refill = now

            if self._tokens < 1.0:
                deficit = (1.0 - self._tokens) / self._refill_per_second
                time.sleep(deficit)
                now = time.monotonic()
                self._tokens = min(
                    self._capacity,
                    self._tokens + (now - self._last_refill) * self._refill_per_second,
                )
                self._last_refill = now

            self._tokens -= 1.0

            # Record the grant and check the observed rate over the last second.
            self._grants.append(now)
            while self._grants and now - self._grants[0] >= 1.0:
                self._grants.popleft()

            if len(self._grants) >= self._tripwire:
                self._tripped = (
                    f"EDGAR rate tripwire: {len(self._grants)} requests in the last "
                    f"second (limit {self._tripwire}/s, SEC ceiling 10/s). The token "
                    f"bucket should have made this impossible, so something is issuing "
                    f"requests outside it. Halting to avoid an IP ban."
                )
                raise RateLimitTripwire(self._tripped)


_limiter = _RateLimiter()


@dataclass(frozen=True)
class Filing:
    """One filing from a company's submission history."""

    cik: str
    accession: str
    form: str
    filing_date: str
    report_date: str
    primary_document: str

    @property
    def index_url(self) -> str:
        cik_int = int(self.cik)
        acc = self.accession.replace("-", "")
        return f"{SEC_HOST}/Archives/edgar/data/{cik_int}/{acc}"

    @property
    def document_url(self) -> str:
        return f"{self.index_url}/{self.primary_document}"


class EdgarClient:
    """Cached, rate-limited access to EDGAR.

    Every response is written to disk. Filings are immutable once filed, so the
    cache is safe indefinitely and keeps repeat analysis runs off the network.
    """

    def __init__(self, cache_dir: Path | None = None, timeout: float = 30.0) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            headers={
                "User-Agent": _user_agent(),
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- transport -----------------------------------------------------

    def _cache_path(self, url: str) -> Path:
        safe = url.split("://", 1)[-1].replace("/", "_")
        return self.cache_dir / safe

    def get(self, url: str, *, use_cache: bool = True) -> bytes:
        path = self._cache_path(url)
        if use_cache and path.exists():
            return path.read_bytes()

        last_error: Exception | None = None
        for attempt in range(3):
            _limiter.acquire()
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:  # transient network failure
                last_error = exc
                time.sleep(2**attempt)
                continue

            if response.status_code == 429:
                # Backing off hard here; a repeat 429 risks an IP block.
                time.sleep(5 * (attempt + 1))
                last_error = EdgarError(f"429 rate limited on {url}")
                continue
            if response.status_code == 404:
                raise EdgarError(f"Not found: {url}")
            if response.status_code >= 500:
                last_error = EdgarError(f"{response.status_code} from {url}")
                time.sleep(2**attempt)
                continue

            response.raise_for_status()
            path.write_bytes(response.content)
            return response.content

        raise EdgarError(f"Failed to fetch {url}") from last_error

    def get_json(self, url: str, *, use_cache: bool = True) -> dict:
        return json.loads(self.get(url, use_cache=use_cache))

    # ---- lookups -------------------------------------------------------

    def cik_for_ticker(self, ticker: str) -> str:
        """Resolve a ticker to a zero-padded 10-digit CIK."""
        payload = self.get_json(TICKER_MAP_URL)
        wanted = ticker.strip().upper()
        for entry in payload.values():
            if entry["ticker"].upper() == wanted:
                return str(entry["cik_str"]).zfill(10)
        raise EdgarError(f"No CIK found for ticker {ticker!r}")

    def submissions(self, cik: str) -> dict:
        """Full submission history for a filer."""
        return self.get_json(f"{DATA_HOST}/submissions/CIK{cik}.json", use_cache=False)

    def filings(self, cik: str, forms: tuple[str, ...] = ("10-K",), limit: int = 5) -> list[Filing]:
        """Most recent filings of the given form types, newest first."""
        recent = self.submissions(cik)["filings"]["recent"]
        out: list[Filing] = []
        for i, form in enumerate(recent["form"]):
            if form not in forms:
                continue
            out.append(
                Filing(
                    cik=cik,
                    accession=recent["accessionNumber"][i],
                    form=form,
                    filing_date=recent["filingDate"][i],
                    report_date=recent["reportDate"][i],
                    primary_document=recent["primaryDocument"][i],
                )
            )
            if len(out) >= limit:
                break
        return out

    # ---- XBRL ----------------------------------------------------------

    def company_facts(self, cik: str) -> dict:
        """Every XBRL fact the filer has reported, grouped by taxonomy/concept."""
        return self.get_json(f"{DATA_HOST}/api/xbrl/companyfacts/CIK{cik}.json", use_cache=False)

    def company_concept(self, cik: str, concept: str, taxonomy: str = "us-gaap") -> dict:
        """One concept's full history for one filer."""
        return self.get_json(
            f"{DATA_HOST}/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json"
        )

    def frames(self, concept: str, period: str, unit: str = "USD", taxonomy: str = "us-gaap") -> dict:
        """One concept across all filers for one period — the peer-comp endpoint.

        `period` looks like CY2024 (annual), CY2024Q1 (quarterly) or CY2024Q1I
        (instantaneous, for balance-sheet items).
        """
        return self.get_json(
            f"{DATA_HOST}/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{period}.json"
        )

    def filing_document(self, filing: Filing) -> str:
        """Raw HTML of a filing's primary document."""
        return self.get(filing.document_url).decode("utf-8", errors="replace")
