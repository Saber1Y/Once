"""ACME knowledge base.

Articles are the real public neatlogs `support-copilot-demo-kb` fixture, fetched
live and cached under data/kb_cache. Two views exist on purpose:

* ``KnowledgeBase.page(article_id)`` is the live help-center page, including the
  status banner ("Outdated" / "Current") and the superseded-by link.
* ``SearchIndex`` is what the agent retrieves from. Like neatlogs' own demo, it
  stores article bodies only (no banner) and is seeded with the outdated refund
  policy instead of the current one.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import httpx

from once.config import DATA_DIR, settings

ARTICLE_IDS = [
    "refund-policy-v3.0",
    "refund-policy-v2.1",
    "billing-dispute-sop",
    "password-reset",
    "starter-support-sla",
    "checkout-outage-runbook",
]

# The index neatlogs' demo manufactures: v2.1 in, v3.0 out.
SEEDED_INDEX = [
    "refund-policy-v2.1",
    "billing-dispute-sop",
    "password-reset",
    "starter-support-sla",
    "checkout-outage-runbook",
]

CACHE_DIR = DATA_DIR / "kb_cache"


@dataclass
class Article:
    id: str
    title: str
    status: str  # "current" | "outdated" | "unmarked"
    superseded_by: str | None
    last_updated: str | None
    body: str
    url: str

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "superseded_by": self.superseded_by,
            "last_updated": self.last_updated,
            "url": self.url,
        }


def _text(fragment: str) -> str:
    fragment = re.sub(r"(?s)<(script|style).*?</\1>", "", fragment)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(fragment)).strip()


def parse_article(article_id: str, raw: str, url: str) -> Article:
    title_match = re.search(r"(?s)<h1>(.*?)</h1>", raw)
    title = _text(title_match.group(1)) if title_match else article_id
    banner_match = re.search(r'(?s)<div class="banner[^"]*">(.*?)</div>', raw)
    banner = banner_match.group(1) if banner_match else ""
    banner_text = _text(banner).lower()
    if banner_text.startswith("outdated"):
        status = "outdated"
    elif banner_text.startswith("current"):
        status = "current"
    else:
        status = "unmarked"
    superseded_by = None
    if status == "outdated":
        link = re.search(r'href="([^"]+)\.html"', banner)
        superseded_by = link.group(1).split("/")[-1] if link else None
    updated = re.search(r"Last updated ([A-Z][a-z]+ \d{1,2}, \d{4})", raw)
    body_start = title_match.end() if title_match else 0
    body = re.sub(r"(?s)<p class=\"meta\">.*?</p>", "", raw[body_start:])
    return Article(
        id=article_id,
        title=title,
        status=status,
        superseded_by=superseded_by,
        last_updated=updated.group(1) if updated else None,
        body=_text(body),
        url=url,
    )


class KnowledgeBase:
    """Live help-center pages with a local cache for offline runs."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.kb_base_url
        self._articles: dict[str, Article] = {}

    def page(self, article_id: str) -> Article:
        if article_id not in self._articles:
            self._articles[article_id] = self._load(article_id)
        return self._articles[article_id]

    def all(self) -> list[Article]:
        return [self.page(a) for a in ARTICLE_IDS]

    def _load(self, article_id: str) -> Article:
        url = f"{self.base_url}/kb/{article_id}.html"
        cache = CACHE_DIR / f"{article_id}.html"
        try:
            response = httpx.get(url, timeout=10, follow_redirects=True)
            response.raise_for_status()
            raw = response.text
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(raw)
        except httpx.HTTPError:
            if not cache.exists():
                raise
            raw = cache.read_text()
        return parse_article(article_id, raw, url)


_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the",
    "a",
    "an",
    "to",
    "of",
    "and",
    "or",
    "is",
    "i",
    "my",
    "you",
    "your",
    "for",
    "in",
    "on",
    "it",
    "can",
    "be",
    "with",
    "me",
    "do",
    "was",
    "this",
    "that",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _WORD.findall(text.lower()) if t not in _STOP]


@dataclass
class SearchIndex:
    """Keyword retrieval over article bodies. Mutable so a fix can repair it."""

    kb: KnowledgeBase
    article_ids: list[str] = field(default_factory=lambda: list(SEEDED_INDEX))

    def search(self, query: str, k: int = 2) -> list[dict]:
        q = set(_tokens(query))
        scored = []
        for article_id in self.article_ids:
            article = self.kb.page(article_id)
            words = _tokens(article.title + " " + article.body)
            score = sum(words.count(t) for t in q) + 3 * len(q & set(_tokens(article.title)))
            if score:
                scored.append((score, article))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [{"article_id": a.id, "title": a.title, "text": a.body} for _, a in scored[:k]]

    def replace(self, stale_id: str, current_id: str) -> None:
        self.article_ids = [current_id if a == stale_id else a for a in self.article_ids]
        if current_id not in self.article_ids:
            self.article_ids.append(current_id)
