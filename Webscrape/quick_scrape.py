"""
quick_scrape.py — minimal web scraper

Usage:
    results = scrape_url("https://example.com", "price", "wait times", "rating")

    # Works with JS-heavy sites too — pass the root URL and a subpage name:
    results = scrape_url("https://www.er-watch.ca/", "WRHN Midtown (Kitchener)")
"""

from __future__ import annotations

import re
import warnings
from urllib.parse import urlparse

# Must be set before importing requests/urllib3 or the warning already fires
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")
warnings.filterwarnings("ignore", message=".*LibreSSL.*")

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# When a field resolves to a subpage (e.g. a hospital name on er-watch.ca),
# we try these standard "primary value" labels on that subpage.
_PRIMARY_FIELDS = ["current wait time", "price", "rating", "score", "status"]


# ── Network helpers ───────────────────────────────────────────────────────────

def _fetch(url: str) -> requests.Response | None:
    """GET a URL, return Response or None on error."""
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        return r
    except requests.exceptions.RequestException as e:
        print(f"[fetch error] {url} — {e}")
        return None


def _sitemap_urls(root_url: str) -> list[str]:
    """Fetch /sitemap.xml from the root domain and return all <loc> URLs."""
    parsed = urlparse(root_url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    r = _fetch(sitemap_url)
    if not r:
        return []
    return re.findall(r"<loc>(https?://[^<]+)</loc>", r.text)


def _best_subpage(field: str, sitemap_urls: list[str]) -> str | None:
    """
    Find the sitemap URL whose path slug best matches the field text.

    Scoring (per field word found in the URL path):
      3 — every significant word matches
      2 — more than half match
      1 — at least one matches
    """
    words = [w for w in re.split(r"\W+", field.lower()) if len(w) > 2]
    if not words:
        return None

    best_score, best_url = 0, None
    for u in sitemap_urls:
        path = urlparse(u).path.lower()
        matches = sum(1 for w in words if w in path)
        if matches == len(words):
            score = 3
        elif matches > len(words) / 2:
            score = 2
        elif matches >= 1:
            score = 1
        else:
            score = 0
        if score > best_score:
            best_score, best_url = score, u

    return best_url if best_score >= 1 else None


# ── Core extraction ───────────────────────────────────────────────────────────

def _extract(html: str, fields: list[str]) -> dict[str, str | None]:
    """
    Parse HTML and extract each requested field.
    Returns a dict mapping field name → value (or None).
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # ── Build structured label→value pairs ────────────────────────────────────
    label_value_pairs: list[tuple[str, str]] = []

    # (a) <table> rows
    for row in soup.select("table tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            label = _norm(cells[0].get_text(" ", strip=True))
            value = cells[1].get_text(" ", strip=True)
            if label and value:
                label_value_pairs.append((label, value))

    # (b) <dl> definition lists
    for dt in soup.select("dl dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            label = _norm(dt.get_text(" ", strip=True))
            value = dd.get_text(" ", strip=True)
            if label and value:
                label_value_pairs.append((label, value))

    # (c) <strong>/<b> inline labels followed by adjacent text
    for bold in soup.find_all(["strong", "b", "th"]):
        label = _norm(bold.get_text(" ", strip=True))
        if not label:
            continue
        sibling = bold.next_sibling
        value = ""
        while sibling and not value:
            if isinstance(sibling, str):
                value = sibling.strip().lstrip(":").strip()
            elif hasattr(sibling, "get_text"):
                value = sibling.get_text(" ", strip=True).lstrip(":").strip()
            sibling = getattr(sibling, "next_sibling", None)
        if not value and bold.parent:
            parent_text = bold.parent.get_text(" ", strip=True)
            value = parent_text.replace(bold.get_text(" ", strip=True), "").lstrip(":").strip()
        if label and value and value != label:
            label_value_pairs.append((label, value))

    full_text = re.sub(r"\s+", " ", soup.get_text(separator=" "))
    page_lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]

    meta_desc = ""
    meta_tag = soup.find("meta", property="og:description")
    if meta_tag:
        meta_desc = meta_tag.get("content", "")

    # ── Extract each field ────────────────────────────────────────────────────
    results: dict[str, str | None] = {}

    for field in fields:
        field_norm = _norm(field)
        field_tokens = set(field_norm.split())
        value = None

        # Strategy A: structured label→value pairs (table / dl / bold)
        best_score, best_val = 0, None
        for label, val in label_value_pairs:
            score = _match_score(field_norm, field_tokens, label)
            if score > best_score and len(val) < 80:
                best_score, best_val = score, val
        if best_score >= 1:
            value = best_val

        # Strategy B: adjacent-line scan
        #   Handles SSR/React pages where label and value are sequential DOM nodes.
        #   Also handles reverse pattern ("29" / "waiting").
        if value is None:
            value = _adjacent_line_extract(field_norm, field_tokens, page_lines)

        # Strategy C: CSS class / id keyword scan
        if value is None:
            sig_tokens = [t for t in field_tokens if len(t) > 3]
            for token in sig_tokens:
                for el in (
                    soup.find_all(True, attrs={"class": re.compile(token, re.I)})
                    + soup.find_all(True, attrs={"id": re.compile(token, re.I)})
                ):
                    text = el.get_text(" ", strip=True)
                    if text and text.lower() != token and len(text) < 80:
                        value = text
                        break
                if value:
                    break

        # Strategy D: regex over full text
        if value is None:
            value = _regex_extract(field_norm, full_text)

        # Strategy E: regex over og:description meta tag
        if value is None and meta_desc:
            value = _regex_extract(field_norm, meta_desc)

        results[field] = value

    return results


# ── Public API ────────────────────────────────────────────────────────────────

def scrape_url(url: str, *fields: str) -> dict[str, str | None]:
    """
    Fetch a webpage and extract the requested fields.

    Args:
        url:     The page to scrape. Can be a root URL for a JS-heavy site —
                 the scraper will automatically find the matching subpage via
                 the site's sitemap if the root page has no extractable content.
        *fields: Field names to extract, e.g.:
                   "price", "current wait time", "rating"
                 For JS-heavy sites, a field can also be a subpage name:
                   "WRHN Midtown (Kitchener)" → resolves via sitemap

    Returns:
        Dict mapping each field name to its extracted value (or None).

    Examples:
        scrape_url("https://homelesshub.ca/community-profiles/waterloo-region",
                   "apartment vacancy rate", "people experiencing homelessness")

        scrape_url("https://www.er-watch.ca/",
                   "WRHN Midtown (Kitchener)", "Cambridge Memorial Hospital")
    """
    resp = _fetch(url)
    if not resp:
        return {f: None for f in fields}

    results = _extract(resp.text, list(fields))

    # ── Subpage resolution for JS-heavy sites ─────────────────────────────────
    # If the page text is very short it's likely a client-side-only SPA.
    # For fields that returned None, find the best matching subpage from the
    # sitemap, fetch it, and try again with standard "primary value" targets.
    unresolved = [f for f in fields if results[f] is None]
    if not unresolved:
        return results

    soup_check = BeautifulSoup(resp.text, "html.parser")
    for tag in soup_check(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = soup_check.get_text(separator=" ", strip=True)

    if len(visible_text) < 500:  # thin page → likely JS-only SPA
        sitemap = _sitemap_urls(url)
        if sitemap:
            for field in unresolved:
                subpage_url = _best_subpage(field, sitemap)
                if not subpage_url or subpage_url == url:
                    continue
                sub_resp = _fetch(subpage_url)
                if not sub_resp:
                    continue
                # The field name identified the subpage — now extract primary values
                # from it. Don't use the field name as a label here because it will
                # match the page's own title and return an adjacent non-value line.
                sub_results = _extract(sub_resp.text, _PRIMARY_FIELDS)
                value = next(
                    (sub_results[p] for p in _PRIMARY_FIELDS if sub_results.get(p)),
                    None,
                )
                results[field] = value

    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Lowercase, strip punctuation noise, collapse whitespace."""
    text = text.lower().strip().rstrip(":").strip()
    text = re.sub(r"[^\w\s\-/]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _adjacent_line_extract(
    field_norm: str, field_tokens: set[str], lines: list[str]
) -> str | None:
    """
    Scan ordered page lines for a label matching the field, then return the
    adjacent value line (forward or backward).

    Handles two common SSR/React patterns:
      - Label above value:  "Current Wait Time" / "6h 2m"
      - Value above label:  "29" / "waiting"
    """
    _NOISE = {
        "all hospitals", "toggle theme", "updated", "live data available",
        "static information only", "get directions", "open in maps",
        "visit website", "call hospital", "loading map", "wait time trends",
        "hospital information", "ontario health west", "ontario health east",
        "ontario health north", "ontario health central", "ontario health toronto",
    }
    sig_tokens = {t for t in field_tokens if len(t) > 3}

    def is_noise(line: str) -> bool:
        return not line or _norm(line) in _NOISE or len(line) > 120

    def is_label_match(line: str) -> bool:
        n = _norm(line)
        return (
            field_norm in n
            or (n in field_norm and len(n.split()) >= 2)
            or (sig_tokens and sig_tokens.issubset(set(n.split())))
        )

    def is_valid_candidate(c: str) -> bool:
        return (
            bool(c)
            and not is_noise(c)
            and _norm(c) != field_norm
            and bool(re.search(r"[a-zA-Z0-9]", c))
            and len(c) >= 2
        )

    def value_score(s: str) -> int:
        if re.search(r"\d", s):   return 2   # digit → likely a value
        if len(s.split()) == 1:   return 1   # single word
        return 0                              # multi-word → likely another label

    for i, line in enumerate(lines):
        if not is_label_match(line):
            continue

        candidates: list[str] = []

        for j in range(i + 1, min(i + 4, len(lines))):
            c = lines[j].strip()
            if is_valid_candidate(c):
                candidates.append(c)
                break

        for j in range(i - 1, max(i - 3, -1), -1):
            c = lines[j].strip()
            if is_valid_candidate(c):
                candidates.append(c)
                break

        if candidates:
            candidates.sort(key=value_score, reverse=True)
            return candidates[0]

    return None


def _match_score(field_norm: str, field_tokens: set[str], label: str) -> int:
    """Score how well a structured label matches the requested field."""
    label_tokens = set(label.split())
    if field_norm in label or label in field_norm:
        return len(field_norm) + 10
    shared = {t for t in field_tokens & label_tokens if len(t) > 2}
    return len(shared)


def _regex_extract(field_norm: str, text: str) -> str | None:
    """
    Find the field label in text and capture the value that follows it.
    Handles numeric, monetary, percentage, duration, and plain-text values.
    """
    flexible = re.escape(field_norm).replace(r"\ ", r"[\s\W]+")
    pattern = re.compile(
        rf"{flexible}"
        r"[\s:–\-]+?"
        r"("
        r"\$?[\d,]+(?:\.\d+)?(?:\s*(?:%|hours?|mins?|minutes?|days?|/month|/year|k))?"
        r"|[A-Za-z][^\n.;|]{1,80}"
        r")",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    return m.group(1).strip().rstrip(".,;") if m else None


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Homeless Hub: structured stats page
    homeless = scrape_url(
        "https://homelesshub.ca/community-profiles/waterloo-region",
        "people experiencing homelessness",
        "chronic homelessness",
        "unemployment rate",
        "appartment vacancy rate",
        "average cost of rent (1 bdrm)",
    )
    print("\n── Waterloo Region (homelesshub.ca) ───────────────")
    for field, value in homeless.items():
        print(f"  {field:<42} {value}")

    # ER Watch: JS-heavy SPA — pass root URL + hospital names as fields
    er = scrape_url(
        "https://www.er-watch.ca/",
        "WRHN Midtown",
        "WRHN Queen's",
        "Cambridge Memorial Hospital",
        "Guelph General Hospital",
    )
    print("\n── Waterloo-Area ER Wait Times (er-watch.ca) ──────")
    for field, value in er.items():
        print(f"  {field:<35} {value}")
