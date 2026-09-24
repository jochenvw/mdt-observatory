"""Allowlisted research searches for the Research specialist, on top of curated evidence.

Queries go only to approved public scholarly endpoints, in a Europe-first source
hierarchy: Dutch guidelines, the EU trial register, international literature, US
registries, then preprints. Every result becomes an ``Evidence`` record labelled
``LIVE`` (fetched during the meeting) or ``RECORDED`` (a captured response replayed
in rehearsal). Nothing here extracts study effects or judges applicability: those
fields are marked "not extracted" / "not assessed" rather than guessed.
"""

import asyncio
import hashlib
import html
import json
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from importlib.resources import files
from typing import Any, Literal, cast
from urllib.parse import urlencode
from weakref import WeakKeyDictionary

import httpx2

from mdt.models import Evidence

type Tier = Literal["NL", "EU", "INTL", "US", "PREPRINT"]
type Retrieval = Literal["LIVE", "RECORDED"]

TIER_ORDER: tuple[Tier, ...] = ("NL", "EU", "INTL", "US", "PREPRINT")
TIER_LABELS: dict[Tier, str] = {
    "NL": "Netherlands", "EU": "European", "INTL": "International literature",
    "US": "US context", "PREPRINT": "Preprint",
}
_REGION: dict[Tier, Literal["NL", "EU", "INTERNATIONAL", "US"]] = {
    "NL": "NL", "EU": "EU", "INTL": "INTERNATIONAL", "US": "US", "PREPRINT": "INTERNATIONAL",
}
# ClinicalTrials.gov's edge filter rejects unfamiliar agents; keep the library prefix.
USER_AGENT = f"python-httpx/{httpx2.__version__} MDT-Observatory/1.0 (fictional MDT demonstration)"
MAX_QUERY_CHARS = 256
MIN_QUERY_CHARS = 3
MAX_RESULTS = 10
MAX_RESPONSE_BYTES = 2_000_000
SEARCH_PASSAGE_CHARS = 700
ABSTRACT_CHARS = 3000
CACHE_SECONDS = 3600
CACHE_ENTRIES = 128
NCBI_INTERVAL_SECONDS = 0.34
REQUEST_TIMEOUT = httpx2.Timeout(12.0, connect=5.0)
PUBLICATION_TYPES = ("any", "review", "guideline", "randomized_trial")
SORT_ORDERS = ("most_cited", "newest")
REGISTRIES = ("ctis_then_clinicaltrials_gov", "ctis", "clinicaltrials_gov")


@dataclass(frozen=True)
class Source:
    key: str
    label: str
    tier: Tier
    host: str
    description: str


SOURCES: dict[str, Source] = {
    source.key: source
    for source in (
        Source(
            "richtlijnendatabase", "Richtlijnendatabase", "NL", "richtlijnendatabase.nl",
            "Dutch national clinical practice guidelines",
        ),
        Source(
            "ctis", "EU Clinical Trials register (CTIS)", "EU", "euclinicaltrials.eu",
            "EU Clinical Trials Information System public register",
        ),
        Source(
            "europepmc", "Europe PMC", "INTL", "www.ebi.ac.uk",
            "EMBL-EBI index of PubMed, PMC and guideline literature",
        ),
        Source(
            "pubmed", "PubMed", "INTL", "eutils.ncbi.nlm.nih.gov",
            "NCBI bibliographic database",
        ),
        Source(
            "clinicaltrials_gov", "ClinicalTrials.gov", "US", "clinicaltrials.gov",
            "US National Library of Medicine trial register",
        ),
        Source(
            "preprints", "Preprints via Europe PMC", "PREPRINT", "www.ebi.ac.uk",
            "medRxiv, bioRxiv, Research Square and other preprint servers",
        ),
    )
}
ALLOWED_HOSTS = frozenset(source.host for source in SOURCES.values())
_EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_PUBMED_SUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
_CTIS_SEARCH = "https://euclinicaltrials.eu/ctis-public-api/search"
_CTGOV_SEARCH = "https://clinicaltrials.gov/api/v2/studies"
_GUIDELINE_SEARCH = "https://richtlijnendatabase.nl/zoek"
_CTGOV_FIELDS = (
    "NCTId,BriefTitle,OverallStatus,Phase,Condition,LeadSponsorName,LocationCountry,"
    "StartDate,BriefSummary,EnrollmentCount,StudyType"
)
_EUROPEPMC_TYPES = {
    "any": "",
    "review": ' AND (PUB_TYPE:"review" OR PUB_TYPE:"systematic review")',
    "guideline": ' AND (PUB_TYPE:"practice guideline" OR PUB_TYPE:"guideline")',
    "randomized_trial": ' AND PUB_TYPE:"randomized controlled trial"',
}
_PUBMED_TYPES = {
    "any": "",
    "review": " AND (review[pt] OR systematic review[pt])",
    "guideline": " AND (guideline[pt] OR practice guideline[pt])",
    "randomized_trial": " AND randomized controlled trial[pt]",
}

_QUERY = {
    "type": "string",
    "description": (
        f"Clinical concepts only, {MIN_QUERY_CHARS}-{MAX_QUERY_CHARS} characters. Never "
        "include case identifiers, names, dates, ages or record numbers."
    ),
}
_MAX = {"type": "integer", "description": f"Number of results to return, 1-{MAX_RESULTS}."}
_PUBTYPE = {"type": "string", "enum": list(PUBLICATION_TYPES)}
_SORT = {
    "type": "string", "enum": list(SORT_ORDERS),
    "description": "most_cited surfaces established studies; newest surfaces recent work.",
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    properties: dict[str, Any]
    sources: tuple[str, ...]
    started: str
    """Clinician-readable description of what this search is doing."""


TOOL_SPECS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            "search_dutch_guidelines",
            "LIVE search of the Dutch Richtlijnendatabase (tier NL, search first). Use Dutch "
            "clinical terms. Returns guideline modules with the search-result snippet only.",
            {"query": _QUERY, "max_results": _MAX}, ("richtlijnendatabase",),
            "Dutch national guidelines",
        ),
        ToolSpec(
            "search_clinical_trials",
            "LIVE search of trial registers: the EU CTIS register first (tier EU), then "
            "ClinicalTrials.gov (tier US context). max_results applies to each register.",
            {
                "query": _QUERY, "max_results": _MAX,
                "registry": {"type": "string", "enum": list(REGISTRIES)},
            },
            ("ctis", "clinicaltrials_gov"),
            "trial registers",
        ),
        ToolSpec(
            "search_europepmc",
            "LIVE search of peer-reviewed literature in Europe PMC (EMBL-EBI; includes "
            "PubMed and ESMO guidelines). Every query word must appear in the title or "
            "abstract, so use 3-6 key terms. Returns identifiers and a shortened abstract.",
            {
                "query": _QUERY, "max_results": _MAX, "publication_type": _PUBTYPE,
                "sort": _SORT,
            },
            ("europepmc",),
            "published literature",
        ),
        ToolSpec(
            "search_pubmed",
            "LIVE search of PubMed (NCBI). Returns bibliographic records without abstracts; "
            "use fetch_abstract to read one.",
            {"query": _QUERY, "max_results": _MAX, "publication_type": _PUBTYPE},
            ("pubmed",),
            "published literature",
        ),
        ToolSpec(
            "search_preprints",
            "LIVE search of preprints (medRxiv, bioRxiv and others) via Europe PMC. "
            "Preprints are not peer reviewed and must be labelled as such.",
            {"query": _QUERY, "max_results": _MAX},
            ("preprints",),
            "preprints",
        ),
        ToolSpec(
            "fetch_abstract",
            "LIVE retrieval of the full abstract for a LIVE evidence ID returned earlier in "
            "this review. Never promotes an abstract to full text.",
            {"evidence_id": {"type": "string", "description": "An evidence ID from this run."}},
            ("europepmc",),
            "abstract",
        ),
    )
}


class LiteratureError(RuntimeError):
    """A source could not be searched. Reported visibly; never silently replaced."""


@dataclass
class SourceCheck:
    source: Source
    status: Literal["completed", "unavailable"]
    total: int = 0
    returned: int = 0
    message: str = ""


@dataclass
class SearchOutcome:
    tool: str
    query: str
    status: Literal["completed", "unavailable", "refused"]
    checks: list[SourceCheck] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    already_curated: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def sources(self) -> list[Source]:
        return [SOURCES[key] for key in TOOL_SPECS[self.tool].sources]


def tool_parameters(name: str) -> dict[str, Any]:
    spec = TOOL_SPECS[name]
    return {
        "type": "object",
        "properties": spec.properties,
        "required": list(spec.properties),
        "additionalProperties": False,
    }


def parse_arguments(name: str, arguments: Any) -> tuple[dict[str, Any] | None, str]:
    """Validate the bounded tool schema; return (arguments, "") or (None, reason)."""
    spec = TOOL_SPECS[name]
    if not isinstance(arguments, dict) or set(arguments) != set(spec.properties):
        return None, "The search request did not match the tool's fields."
    for key, schema in spec.properties.items():
        value = arguments[key]
        if schema["type"] == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return None, f"{key} must be a whole number."
            if not 1 <= value <= MAX_RESULTS:
                return None, f"{key} must be between 1 and {MAX_RESULTS}."
        elif not isinstance(value, str):
            return None, f"{key} must be text."
        elif "enum" in schema and value not in schema["enum"]:
            return None, f"{key} must be one of {', '.join(schema['enum'])}."
    if "query" in arguments:
        query = " ".join(str(arguments["query"]).split())
        if not MIN_QUERY_CHARS <= len(query) <= MAX_QUERY_CHARS:
            return None, f"The search text must be {MIN_QUERY_CHARS}-{MAX_QUERY_CHARS} characters."
        if not query.isprintable():
            return None, "The search text contained unprintable characters."
        arguments = {**arguments, "query": query}
    return arguments, ""


_IDENTIFYING_KEY = re.compile(
    r"(?:^|_)(?:id|name|pseudonym|mrn|bsn|patient_id|record_number|dob|date_of_birth|"
    r"birth_date|nhs|insurance_number)$",
    re.IGNORECASE,
)


def case_identifiers(case: dict[str, Any]) -> set[str]:
    """Strings from the case record that must never leave the application in a query."""
    found: set[str] = set()

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif isinstance(value, str) and _IDENTIFYING_KEY.search(key) and len(value) >= 4:
            found.add(value)

    walk(case)
    metadata = case.get("source_metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("sha256"), str):
        found.add(metadata["sha256"])
    return found


_PRIVACY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"), "a date"),
    (re.compile(r"\d{6,}"), "a record number"),
    (re.compile(r"\b(?:CASE|SYN|MDT)-", re.IGNORECASE), "a case identifier"),
    (re.compile(r"\S@\S"), "an e-mail address"),
    (
        re.compile(r"\b\d{1,3}[- ]?(?:year|yr|jaar)s?[- ]old\b|\b\d{1,3}[- ]?jarige\b", re.I),
        "an age",
    ),
)


def query_violation(query: str, identifiers: set[str]) -> str | None:
    """Why a query may not be sent, in clinician-readable words; None when it may."""
    for pattern, what in _PRIVACY_PATTERNS:
        if pattern.search(query):
            return f"The search text contained {what}; only clinical concepts may be searched."
    folded = query.casefold()
    if any(value.casefold() in folded for value in identifiers):
        return (
            "The search text contained a case identifier; "
            "only clinical concepts may be searched."
        )
    return None


def request_key(
    method: str, url: str, params: dict[str, str] | None = None, body: str | None = None,
) -> str:
    """Stable key for caching and recorded replay; excludes credentials by construction."""
    safe = sorted((key, value) for key, value in (params or {}).items() if key != "api_key")
    return f"{method} {url}" + (f"?{urlencode(safe)}" if safe else "") + (
        f" {body}" if body else ""
    )


_CACHE: OrderedDict[str, tuple[float, str]] = OrderedDict()
_NCBI_NEXT: WeakKeyDictionary[asyncio.AbstractEventLoop, float] = WeakKeyDictionary()
_NCBI_LOCKS: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()


def clear_cache() -> None:
    _CACHE.clear()


async def _pace_ncbi() -> None:
    """NCBI permits three requests per second without an API key."""
    loop = asyncio.get_running_loop()
    lock = _NCBI_LOCKS.setdefault(loop, asyncio.Lock())
    async with lock:
        wait = _NCBI_NEXT.get(loop, 0.0) - loop.time()
        if wait > 0:
            await asyncio.sleep(wait)
        _NCBI_NEXT[loop] = loop.time() + NCBI_INTERVAL_SECONDS


@dataclass(frozen=True)
class RecordedSearches:
    captured_at: str
    responses: dict[str, str]
    plans: dict[str, list[dict[str, Any]]]


@cache
def recorded_searches() -> RecordedSearches:
    """Captured responses that let rehearsal show the search behaviour offline."""
    path = files("mdt").joinpath("dossiers", "recorded_searches.json")
    if not path.is_file():
        return RecordedSearches("", {}, {})
    data = json.loads(path.read_text(encoding="utf-8"))
    return RecordedSearches(
        captured_at=str(data["captured_at"]),
        responses=dict(data["responses"]),
        plans={key: list(value) for key, value in data["plans"].items()},
    )


class LiteratureClient:
    """One review's HTTP access to the allowlisted sources.

    ``LIVE`` sends real requests (cached for an hour per process). ``RECORDED``
    serves captured responses and never touches the network; a request with no
    recording fails visibly, exactly like an unreachable source.
    """

    def __init__(
        self,
        *,
        retrieval: Retrieval = "LIVE",
        transport: httpx2.AsyncBaseTransport | None = None,
        ncbi_api_key: str = "",
        recorded: RecordedSearches | None = None,
        recorder: dict[str, str] | None = None,
    ) -> None:
        self.retrieval: Retrieval = retrieval
        self.recorded = recorded
        self.recorder = recorder
        self.captured_at = recorded.captured_at if recorded else ""
        self._ncbi_api_key = ncbi_api_key
        self._client: httpx2.AsyncClient | None = None
        self._transport = transport
        self.requests: list[str] = []

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx2.AsyncClient:
        if self._client is None:
            self._client = httpx2.AsyncClient(
                transport=self._transport, timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT}, follow_redirects=False,
            )
        return self._client

    async def request(
        self, source: Source, method: str, url: str, *,
        params: dict[str, str] | None = None, body: str | None = None,
    ) -> str:
        target = httpx2.URL(url)
        if target.scheme != "https" or target.host not in ALLOWED_HOSTS or (
            target.host != source.host
        ):
            raise LiteratureError(
                f"That address is not an allowlisted endpoint for {source.label}."
            )
        key = request_key(method, url, params, body)
        self.requests.append(key)
        if self.retrieval == "RECORDED":
            if self.recorded is None or key not in self.recorded.responses:
                raise LiteratureError(
                    f"No recorded response exists for this {source.label} search."
                )
            return self.recorded.responses[key]
        cached = _CACHE.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS and self.recorder is None:
            _CACHE.move_to_end(key)
            return cached[1]
        sent = dict(params or {})
        if source.host == SOURCES["pubmed"].host:
            sent["tool"] = "mdt-observatory"
            if self._ncbi_api_key:
                sent["api_key"] = self._ncbi_api_key
        text = await self._send(source, method, url, sent, body)
        _CACHE[key] = (time.monotonic(), text)
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_ENTRIES:
            _CACHE.popitem(last=False)
        if self.recorder is not None:
            self.recorder[key] = text
        return text

    async def _send(
        self, source: Source, method: str, url: str, params: dict[str, str], body: str | None,
    ) -> str:
        headers = {"Content-Type": "application/json"} if body else {}
        for attempt in range(2):
            if source.host == SOURCES["pubmed"].host:
                await _pace_ncbi()
            retry_after = 0.0
            try:
                async with self._http().stream(
                    method, url, params=params, content=body, headers=headers,
                ) as response:
                    if response.status_code in {429, 500, 502, 503, 504}:
                        if attempt:
                            raise LiteratureError(
                                f"{source.label} is temporarily unavailable "
                                f"(status {response.status_code})."
                            )
                        retry_after = _retry_seconds(response.headers.get("retry-after"))
                    elif response.status_code != 200:
                        raise LiteratureError(
                            f"{source.label} could not be searched (status {response.status_code})."
                        )
                    else:
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > MAX_RESPONSE_BYTES:
                                raise LiteratureError(f"{source.label} returned too much data.")
                            chunks.append(chunk)
                        return b"".join(chunks).decode(response.encoding or "utf-8", "replace")
            except httpx2.TransportError:
                if attempt:
                    raise LiteratureError(f"{source.label} did not respond.") from None
                retry_after = 1.0
            await asyncio.sleep(retry_after)
        raise LiteratureError(f"{source.label} is temporarily unavailable.")


def _retry_seconds(value: str | None) -> float:
    try:
        return min(max(float(value or 1), 0.0), 5.0)
    except ValueError:
        return 1.0


_BLOCK_TAGS = re.compile(r"</?(?:h\d|p|br|li|div|section)[^>]*>", re.IGNORECASE)


def _plain(value: Any) -> str:
    text = _BLOCK_TAGS.sub(" ", str(value or ""))
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return " ".join(text.split())


def _shorten(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rsplit(" ", 1)[0] + " …"


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]", "", value)[:64]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _iso_date(value: str) -> str:
    """CTIS reports dd/mm/yyyy; every other source already uses ISO order."""
    if match := re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", value.strip()):
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    return value


class _Builder:
    """Turns one source's parsed record into a labelled, honest Evidence record."""

    def __init__(self, client: LiteratureClient, source: Source, query: str, endpoint: str):
        self.client = client
        self.source = source
        self.query = query
        self.endpoint = endpoint
        self.retrieved_at = client.captured_at if client.retrieval == "RECORDED" else _now()

    def build(
        self, *, kind: str, identifier: tuple[str, str], title: str, url: str, date: str,
        authority: str, passage: str, access: str, identifiers: dict[str, str],
        tier: Tier | None = None, scrutiny: dict[str, str] | None = None,
        limitations: list[str] | None = None,
    ) -> Evidence:
        tier = tier or self.source.tier
        prefix = "LIVE" if self.client.retrieval == "LIVE" else "REC"
        retrieved = (
            "Retrieved live during this meeting; not curated or independently appraised."
            if self.client.retrieval == "LIVE"
            else f"Recorded search response captured {self.client.captured_at} and replayed "
            "for rehearsal; not a live search."
        )
        notes = [retrieved, "Patient-to-study applicability has not been assessed."]
        if tier == "US":
            notes.append("US context — not European standard of care.")
        if tier == "PREPRINT":
            notes.append("PREPRINT — not peer reviewed.")
        if access == "METADATA_ONLY":
            notes.append("Only the bibliographic record or search snippet was read.")
        return Evidence(
            id=f"{prefix}-{identifier[0]}-{_safe_id(identifier[1])}",
            title=title or "Untitled record",
            url=url,
            date=date or "Not stated",
            authority=authority or self.source.label,
            region=_REGION[tier],
            kind=kind,
            access=cast(Any, access),
            patient_match="NOT_ASSESSED",
            passage=passage,
            limitations=[*notes, *(limitations or [])],
            scrutiny={
                "population": "not extracted", "intervention": "not extracted",
                "comparator": "not extracted", "outcome": "not extracted",
                "study_design": "not extracted", "patient_applicability": "not assessed",
                **(scrutiny or {}),
            },
            retrieval=self.client.retrieval,
            retrieved_at=self.retrieved_at,
            retrieved_via=self.source.label,
            source_tier=tier,
            endpoint=self.endpoint,
            query=self.query,
            identifiers=identifiers,
        )


def _europepmc_record(builder: _Builder, item: dict[str, Any], limit: int) -> Evidence | None:
    source = str(item.get("source") or "")
    record_id = str(item.get("id") or "")
    if not record_id:
        return None
    pmid = str(item.get("pmid") or "")
    title = _plain(item.get("title"))
    journal = item.get("journalInfo", {}).get("journal", {}) if isinstance(
        item.get("journalInfo"), dict
    ) else {}
    publisher = item.get("bookOrReportDetails", {}).get("publisher", "") if isinstance(
        item.get("bookOrReportDetails"), dict
    ) else ""
    types = [str(value) for value in item.get("pubTypeList", {}).get("pubType", [])] if (
        isinstance(item.get("pubTypeList"), dict)
    ) else []
    abstract = _plain(item.get("abstractText"))
    identifiers = {
        key: str(item[name]) for key, name in (("pmid", "pmid"), ("pmcid", "pmcid"), ("doi", "doi"))
        if item.get(name)
    }
    preprint = source == "PPR"
    lowered = " ".join(types).lower()
    guideline = "guideline" in lowered
    tier: Tier = "PREPRINT" if preprint else "EU" if guideline and "ESMO" in title else "INTL"
    if preprint:
        identifiers["preprint"] = record_id
        kind, url = "PREPRINT", f"https://europepmc.org/article/PPR/{record_id}"
    else:
        kind = (
            "GUIDELINE" if guideline else "SYSTEMATIC_REVIEW" if "systematic" in lowered
            else "REVIEW" if "review" in lowered
            else "RANDOMIZED_TRIAL" if "randomized" in lowered else "LITERATURE"
        )
        url = (
            f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid
            else f"https://europepmc.org/article/{_safe_id(source)}/{_safe_id(record_id)}"
        )
    journal_name = str(journal.get("title") or journal.get("isoabbreviation") or publisher or "")
    scrutiny = {"publication_type": ", ".join(types) or "not stated", "journal": journal_name}
    if item.get("isOpenAccess") == "Y":
        scrutiny["open_access"] = "Full text available at the source; not retrieved."
    mesh = item.get("meshHeadingList", {}).get("meshHeading", []) if isinstance(
        item.get("meshHeadingList"), dict
    ) else []
    if mesh and limit > SEARCH_PASSAGE_CHARS:
        scrutiny["mesh_terms"] = ", ".join(
            str(term.get("descriptorName")) for term in mesh[:12] if isinstance(term, dict)
        )
    return builder.build(
        kind=kind, identifier=("PPR" if preprint else "PMID" if pmid else source, record_id if (
            preprint or not pmid
        ) else pmid),
        title=title, url=url,
        date=str(item.get("firstPublicationDate") or item.get("pubYear") or ""),
        authority=journal_name or ("Preprint server" if preprint else "Europe PMC record"),
        passage=_shorten(abstract, limit), identifiers=identifiers, tier=tier, scrutiny=scrutiny,
        access="PUBLIC_ABSTRACT_ONLY" if abstract else "METADATA_ONLY",
        limitations=(
            ["Abstract shortened for search; fetch the abstract to read it in full."]
            if len(abstract) > limit else []
        ),
    )


def _title_abstract_query(query: str) -> str:
    """Require every concept word in the title or abstract; full-text matches add noise."""
    terms: list[str] = []
    for word in re.sub(r"[^\w\s-]", " ", query).split():
        operator = word.upper()
        if operator in {"OR", "NOT"}:
            if terms and terms[-1] not in {"OR", "NOT"}:
                terms.append(operator)
        elif operator != "AND":
            if terms and terms[-1] not in {"OR", "NOT"}:
                terms.append("AND")
            terms.append(word)
    while terms and terms[-1] in {"OR", "NOT", "AND"}:
        terms.pop()
    return f"TITLE_ABS:({' '.join(terms) or query})"


async def _search_europepmc(
    client: LiteratureClient, source: Source, query: str, count: int, publication_type: str,
    sort: str,
) -> tuple[list[Evidence], int]:
    preprints = source.key == "preprints"
    params = {
        "query": _title_abstract_query(query)
        + (" AND SRC:PPR" if preprints else " AND NOT SRC:PPR")
        + _EUROPEPMC_TYPES[publication_type],
        "format": "json", "resultType": "core", "pageSize": str(count),
    }
    if sort == "most_cited":
        params["sort"] = "CITED desc"
    data = json.loads(await client.request(source, "GET", _EUROPEPMC_SEARCH, params=params))
    builder = _Builder(client, source, query, _EUROPEPMC_SEARCH)
    results = data.get("resultList", {}).get("result", [])
    records = [_europepmc_record(builder, item, SEARCH_PASSAGE_CHARS) for item in results]
    return [item for item in records if item][:count], int(data.get("hitCount") or 0)


async def _search_pubmed(
    client: LiteratureClient, source: Source, query: str, count: int, publication_type: str,
) -> tuple[list[Evidence], int]:
    found = json.loads(await client.request(source, "GET", _PUBMED_SEARCH, params={
        "db": "pubmed", "term": query + _PUBMED_TYPES[publication_type], "retmode": "json",
        "retmax": str(count), "sort": "relevance",
    }))["esearchresult"]
    ids = [str(value) for value in found.get("idlist", [])][:count]
    total = int(found.get("count") or 0)
    if not ids:
        return [], total
    summary = json.loads(await client.request(source, "GET", _PUBMED_SUMMARY, params={
        "db": "pubmed", "id": ",".join(ids), "retmode": "json",
    }))["result"]
    builder = _Builder(client, source, query, _PUBMED_SEARCH)
    records = []
    for pmid in ids:
        item = summary.get(pmid)
        if not isinstance(item, dict):
            continue
        articles = {
            str(entry.get("idtype")): str(entry.get("value"))
            for entry in item.get("articleids", []) if isinstance(entry, dict)
        }
        identifiers = {"pmid": pmid, **{
            key: articles[name]
            for key, name in (("doi", "doi"), ("pmcid", "pmc"))
            if name in articles
        }}
        types = [str(value) for value in item.get("pubtype", [])]
        records.append(builder.build(
            kind="LITERATURE", identifier=("PMID", pmid), title=_plain(item.get("title")),
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            date=str(item.get("sortpubdate") or item.get("pubdate") or "")[:10].replace("/", "-"),
            authority=str(item.get("fulljournalname") or item.get("source") or ""),
            passage="", access="METADATA_ONLY", identifiers=identifiers,
            scrutiny={"publication_type": ", ".join(types) or "not stated"},
        ))
    return records, total


async def _search_ctis(
    client: LiteratureClient, source: Source, query: str, count: int,
) -> tuple[list[Evidence], int]:
    body = json.dumps({
        "pagination": {"page": 1, "size": count},
        "sort": {"property": "decisionDate", "direction": "DESC"},
        # CTIS matches containAll as one phrase; commas make each word a required term.
        "searchCriteria": {"containAll": ",".join(query.split())},
    }, separators=(",", ":"))
    data = json.loads(await client.request(source, "POST", _CTIS_SEARCH, body=body))
    builder = _Builder(client, source, query, _CTIS_SEARCH)
    records = []
    for item in data.get("data", [])[:count]:
        number = str(item.get("ctNumber") or "")
        if not re.fullmatch(r"\d{4}-\d{6}-\d{2}-\d{2}", number):
            continue
        countries = ", ".join(str(value).split(":")[0] for value in item.get("trialCountries", []))
        fields = {
            "Conditions": item.get("conditions"), "Phase": item.get("trialPhase"),
            "Sponsor": item.get("sponsor"), "Countries": countries,
            "Enrolled": item.get("totalNumberEnrolled"),
        }
        records.append(builder.build(
            kind="TRIAL_REGISTRATION", identifier=("EUCT", number),
            title=_plain(item.get("ctTitle")),
            url=f"https://euclinicaltrials.eu/search-for-clinical-trials/?lang=en&EUCT={number}",
            date=_iso_date(str(item.get("decisionDateOverall") or item.get("lastUpdated") or "")),
            authority=f"CTIS register · {item.get('sponsor') or 'sponsor not stated'}",
            passage="; ".join(f"{key}: {_plain(value)}" for key, value in fields.items() if value),
            access="METADATA_ONLY", identifiers={"eu_ct_number": number},
            scrutiny={
                "study_design": _plain(item.get("trialPhase")) or "not extracted",
                "population": _plain(item.get("conditions")) or "not extracted",
                "registration_status": "Registered trial; results not retrieved",
            },
        ))
    return records, int(data.get("pagination", {}).get("totalRecords") or len(records))


async def _search_ctgov(
    client: LiteratureClient, source: Source, query: str, count: int,
) -> tuple[list[Evidence], int]:
    data = json.loads(await client.request(source, "GET", _CTGOV_SEARCH, params={
        "query.term": query, "pageSize": str(count), "format": "json",
        "fields": _CTGOV_FIELDS, "countTotal": "true",
    }))
    builder = _Builder(client, source, query, _CTGOV_SEARCH)
    records = []
    for study in data.get("studies", [])[:count]:
        protocol = study.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        number = str(ident.get("nctId") or "")
        if not re.fullmatch(r"NCT\d{8}", number):
            continue
        status = protocol.get("statusModule", {})
        design = protocol.get("designModule", {})
        countries = sorted({
            str(location.get("country")) for location in
            protocol.get("contactsLocationsModule", {}).get("locations", [])
            if isinstance(location, dict) and location.get("country")
        })
        phases = ", ".join(str(value) for value in design.get("phases", [])) or "not stated"
        records.append(builder.build(
            kind="TRIAL_REGISTRATION", identifier=("NCT", number),
            title=_plain(ident.get("briefTitle")),
            url=f"https://clinicaltrials.gov/study/{number}",
            date=str(status.get("startDateStruct", {}).get("date") or ""),
            authority="ClinicalTrials.gov · "
            + str(protocol.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get(
                "name", "sponsor not stated"
            )),
            passage=_shorten(_plain(
                protocol.get("descriptionModule", {}).get("briefSummary")
            ), SEARCH_PASSAGE_CHARS),
            access="PUBLIC_ABSTRACT_ONLY", identifiers={"nct": number},
            scrutiny={
                "study_design": f"{design.get('studyType', 'not stated')}; phase {phases}",
                "population": ", ".join(
                    protocol.get("conditionsModule", {}).get("conditions", [])
                ) or "not extracted",
                "registration_status": str(status.get("overallStatus") or "not stated"),
                "countries": ", ".join(countries[:8]) or "not stated",
            },
        ))
    return records, int(data.get("totalCount") or len(records))


_GUIDELINE_ITEM = re.compile(r'<div class="list-group-item">(.*?)</div>', re.DOTALL)
_GUIDELINE_TOTAL = re.compile(r"<strong>([\d.]+) resultaten</strong>")


async def _search_guidelines(
    client: LiteratureClient, source: Source, query: str, count: int,
) -> tuple[list[Evidence], int]:
    page = await client.request(source, "GET", _GUIDELINE_SEARCH, params={"query": query})
    builder = _Builder(client, source, query, _GUIDELINE_SEARCH)
    records = []
    for block in _GUIDELINE_ITEM.findall(page):
        link = re.search(r'<a data-search-query[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not link:
            continue
        path = html.unescape(link.group(1))
        if not path.startswith("/richtlijn/"):
            continue
        title_match = re.search(r"<strong[^>]*>(.*?)</strong>", link.group(2), re.S)
        crumbs = [_plain(value) for value in re.findall(
            r'<li class="breadcrumb-item">(.*?)</li>', block, re.S
        )]
        snippet = " ".join(
            _plain(value) for value in re.findall(r"<li>(.*?)</li>", link.group(2), re.S)
        )
        guideline = crumbs[0] if crumbs else "Richtlijnendatabase"
        records.append(builder.build(
            kind="GUIDELINE",
            identifier=("NLGUIDE", hashlib.sha256(path.encode()).hexdigest()[:12]),
            title=_plain(title_match.group(1) if title_match else link.group(2)),
            url=f"https://richtlijnendatabase.nl{path}", date="Revision date not shown in search",
            authority=f"Richtlijnendatabase · {guideline}",
            passage=_shorten(snippet, SEARCH_PASSAGE_CHARS),
            access="METADATA_ONLY", identifiers={"guideline_module": path},
            scrutiny={"guideline": guideline, "module_path": " › ".join(crumbs)},
            limitations=["Open the module to read its recommendations and revision date."],
        ))
        if len(records) >= count:
            break
    total = _GUIDELINE_TOTAL.search(page)
    return records, int(total.group(1).replace(".", "")) if total else len(records)


def _curated_match(item: Evidence, curated: list[Evidence]) -> str | None:
    patterns = [
        re.compile(rf"(?<![0-9A-Za-z]){re.escape(value)}(?![0-9A-Za-z])", re.IGNORECASE)
        for key in ("pmid", "doi", "nct", "eu_ct_number", "pmcid")
        if (value := item.identifiers.get(key))
    ]
    for known in curated:
        text = f"{known.url} {known.authority} {known.title} {known.passage}"
        if any(pattern.search(text) for pattern in patterns):
            return known.id
    return None


async def run_search(
    client: LiteratureClient,
    name: str,
    arguments: dict[str, Any],
    *,
    curated: list[Evidence],
    returned: dict[str, Evidence],
    identifiers: set[str],
) -> SearchOutcome:
    """Run one validated search tool; failures become visible outcomes, not exceptions."""
    parsed, problem = parse_arguments(name, arguments)
    query = str((parsed or arguments).get("query") or (parsed or arguments).get("evidence_id", ""))
    if parsed is None:
        return SearchOutcome(name, query[:MAX_QUERY_CHARS], "refused", message=problem)
    if name != "fetch_abstract" and (reason := query_violation(parsed["query"], identifiers)):
        return SearchOutcome(name, "", "refused", message=reason)
    outcome = SearchOutcome(name, query, "completed")
    if name == "fetch_abstract":
        return await _fetch_abstract(client, parsed["evidence_id"], returned, outcome)
    spec = TOOL_SPECS[name]
    keys = list(spec.sources)
    if name == "search_clinical_trials":
        keys = {"ctis": ["ctis"], "clinicaltrials_gov": ["clinicaltrials_gov"]}.get(
            parsed["registry"], keys
        )
    count = int(parsed["max_results"])
    for key in keys:
        source = SOURCES[key]
        try:
            if key in {"europepmc", "preprints"}:
                records, total = await _search_europepmc(
                    client, source, parsed["query"], count, parsed.get("publication_type", "any"),
                    parsed.get("sort", "newest"),
                )
            elif key == "pubmed":
                records, total = await _search_pubmed(
                    client, source, parsed["query"], count, parsed["publication_type"],
                )
            elif key == "ctis":
                records, total = await _search_ctis(client, source, parsed["query"], count)
            elif key == "clinicaltrials_gov":
                records, total = await _search_ctgov(client, source, parsed["query"], count)
            else:
                records, total = await _search_guidelines(client, source, parsed["query"], count)
        except (LiteratureError, ValueError, KeyError, TypeError) as error:
            message = str(error) if isinstance(error, LiteratureError) else (
                f"{source.label} returned a response that could not be read."
            )
            outcome.checks.append(SourceCheck(source, "unavailable", message=message))
            continue
        kept = []
        for record in records:
            if match := _curated_match(record, curated):
                outcome.already_curated.append(match)
            else:
                kept.append(record)
        outcome.evidence.extend(kept)
        outcome.checks.append(SourceCheck(source, "completed", total, len(records)))
    if not any(check.status == "completed" for check in outcome.checks):
        outcome.status = "unavailable"
    outcome.already_curated = list(dict.fromkeys(outcome.already_curated))
    return outcome


async def _fetch_abstract(
    client: LiteratureClient, evidence_id: str, returned: dict[str, Evidence],
    outcome: SearchOutcome,
) -> SearchOutcome:
    source = SOURCES["europepmc"]
    item = returned.get(evidence_id)
    ids = item.identifiers if item and item.retrieval in {"LIVE", "RECORDED"} else {}
    outcome.query = item.title if item else evidence_id
    if not ids.get("pmid") and not ids.get("preprint"):
        outcome.status = "refused"
        outcome.message = (
            "Only a PubMed or preprint record returned earlier in this review can be opened."
        )
        return outcome
    target = (
        f"EXT_ID:{ids['pmid']} AND SRC:MED" if ids.get("pmid")
        else f"EXT_ID:{ids['preprint']} AND SRC:PPR"
    )
    try:
        data = json.loads(await client.request(source, "GET", _EUROPEPMC_SEARCH, params={
            "query": target, "format": "json", "resultType": "core", "pageSize": "1",
        }))
        results = data.get("resultList", {}).get("result", [])
    except (LiteratureError, ValueError) as error:
        message = str(error) if isinstance(error, LiteratureError) else "Unreadable response."
        outcome.checks.append(SourceCheck(source, "unavailable", message=message))
        outcome.status = "unavailable"
        return outcome
    assert item is not None
    builder = _Builder(client, SOURCES["preprints"] if ids.get("preprint") else source,
                       item.query or "", _EUROPEPMC_SEARCH)
    record = _europepmc_record(builder, results[0], ABSTRACT_CHARS) if results else None
    if record is None or not record.passage:
        outcome.checks.append(SourceCheck(source, "completed", 0, 0, "No abstract is available."))
        outcome.message = "No abstract is available for this record."
        return outcome
    record = record.model_copy(update={"id": item.id})
    outcome.evidence.append(record)
    outcome.checks.append(SourceCheck(source, "completed", 1, 1))
    return outcome


def trim_for_recording(key: str, text: str) -> str:
    """Keep only the parts of a captured response the parsers read, to bound fixture size."""
    if key.startswith(f"GET {_GUIDELINE_SEARCH}"):
        start, end = text.find('<section class="search-results">'), text.find("</section>")
        return text[start:end + len("</section>")] if 0 <= start < end else text
    if key.startswith(f"GET {_EUROPEPMC_SEARCH}"):
        data = json.loads(text)
        keep = {
            "id", "source", "pmid", "pmcid", "doi", "title", "journalInfo", "pubYear",
            "firstPublicationDate", "pubTypeList", "abstractText", "isOpenAccess",
            "bookOrReportDetails", "meshHeadingList",
        }
        for item in data.get("resultList", {}).get("result", []):
            for name in list(item):
                if name not in keep:
                    del item[name]
            if isinstance(item.get("journalInfo"), dict):
                journal = item["journalInfo"].get("journal", {})
                item["journalInfo"] = {"journal": {
                    key: journal[key] for key in ("title", "isoabbreviation") if key in journal
                }}
        return json.dumps({
            "hitCount": data.get("hitCount"), "resultList": data.get("resultList", {}),
        }, ensure_ascii=False, separators=(",", ":"))
    return text
