# backend/app/tools/web.py
from __future__ import annotations

import os, json, time, hashlib
import re
import urllib.parse
from typing import List, Dict, Any, Optional

import httpx
from bs4 import BeautifulSoup
from readability import Document
from duckduckgo_search import DDGS

UA = "AIR4Bot/1.0 (+local)"
TIMEOUT = 20

# ---------- Дисковый кэш для web_fetch ----------
CACHE_DIR = os.path.join("storage", "web_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def _cache_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest() + ".json"

def _cache_path(url: str) -> str:
    return os.path.join(CACHE_DIR, _cache_key(url))

def _cache_get(url: str, ttl_sec: int) -> dict | None:
    path = _cache_path(url)
    if not os.path.exists(path):
        return None
    try:
        if (time.time() - os.path.getmtime(path)) > ttl_sec:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _cache_set(url: str, payload: dict) -> None:
    try:
        with open(_cache_path(url), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass

# ---------- Вспомогательное ----------
def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def _domain_matches(url: str, allowed: set[str]) -> bool:
    if not allowed:
        return True
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return False
    return any(netloc == d or netloc.endswith("." + d) for d in allowed)

# ---------- Поиск ----------
def web_search(
    query: str,
    max_results: int = 5,
    region: str = "wt-wt",
    safesearch: str = "moderate",  # "off" | "moderate" | "strict"
    timelimit: Optional[str] = None,  # "d","w","m","y"
) -> List[Dict[str, Any]]:
    """
    Каскадный поиск (переставлен порядок, чтобы избежать 429 от DDG):
    1) Fast-path: docs.python.org (индекс Sphinx)
    2) Fast-path: pypi.org (JSON API + HTML)
    3) SearXNG JSON (несколько инстансов)  ← СНАЧАЛА
       + пара альтернативных переформулировок для общих запросов
    4) duckduckgo_search.DDGS().text(...)
    5) HTML DuckDuckGo (lite/html)
    + пост-фильтр по 'site:domain'
    """
    results: List[Dict[str, Any]] = []

    # домены из site:
    site_tokens = re.findall(r"site:([^\s]+)", query)
    allowed = {tok.strip().lstrip(".").lower() for tok in site_tokens if tok.strip()}

    # 1) fast-path для docs.python.org
    if allowed and any(d == "docs.python.org" or d.endswith(".docs.python.org") for d in allowed):
        q_no_site = re.sub(r"\s*site:[^\s]+", "", query).strip() or query
        try:
            return _search_docs_python_org(q_no_site, max_results=max_results)
        except Exception:
            pass

    # 2) fast-path для pypi.org
    if allowed and any(d == "pypi.org" or d.endswith(".pypi.org") for d in allowed):
        q_no_site = re.sub(r"\s*site:[^\s]+", "", query).strip() or query
        try:
            hits = _search_pypi(q_no_site, max_results=max_results)
            if hits:
                return hits
        except Exception:
            pass
        # если пусто — идём дальше по каскаду

    # 3) SearXNG JSON (в первую очередь)
    searx_instances = [
        "https://searx.be/search",
        "https://searxng.site/search",
        "https://search.bus-hit.me/search",
        "https://search.ononoki.org/search",
        "https://searx.tiekoetter.com/search",
        "https://search.stinpriza.org/search",
    ]
    params_base = {
        "q": query,
        "format": "json",
        "language": "en",
        "safesearch": 1 if safesearch == "strict" else 0,
        "categories": "general",
    }

    def _searx_query(q: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for endpoint in searx_instances:
            try:
                with httpx.Client(follow_redirects=True, headers={"User-Agent": UA}, timeout=TIMEOUT) as client:
                    resp = client.get(endpoint, params={**params_base, "q": q})
                    if not resp.is_success:
                        continue
                    data = resp.json()
                    items = data.get("results", []) or []
                    for it in items:
                        url = it.get("url")
                        title = _clean(it.get("title"))
                        snippet = _clean(it.get("content") or it.get("snippet") or "")
                        if not url or not title:
                            continue
                        if not _domain_matches(url, allowed):
                            continue
                        out.append({"title": title, "url": url, "snippet": snippet})
                        if len(out) >= max_results:
                            return out
            except Exception:
                continue
        return out

    # сначала пробуем как есть
    results = _searx_query(query)
    # если совсем пусто и нет site-фильтра — попробуем парочку «разумных» переформулировок
    if not results and not allowed:
        for alt in [
            f"site:readthedocs.io {query}",
            f"site:github.com {query}",
        ]:
            results = _searx_query(alt)
            if results:
                break
    if results:
        return results[:max_results]

    # 4) библиотека DDGS (может дать 429; это ок — пойдём дальше)
    try:
        oversample = max_results * 4 if allowed else max_results
        with DDGS() as ddgs:
            for r in ddgs.text(
                query,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
                max_results=oversample,
            ):
                url = r.get("href")
                if not url:
                    continue
                if not _domain_matches(url, allowed):
                    continue
                results.append({"title": r.get("title"), "url": url, "snippet": r.get("body")})
                if len(results) >= max_results:
                    return results
    except Exception:
        pass

    # 5) HTML-фоллбеки DDG
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    def _parse_ddg_html(client: httpx.Client, base_url: str, q: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        params = {"q": q, "kl": region, "kp": "-2", "kz": "-1"}
        if safesearch == "strict":
            params["kp"] = "1"
        url = base_url + "?" + urllib.parse.urlencode(params)
        resp = client.get(url)
        if resp.status_code == 429:
            return []  # отдаём пусто — оставим каскад идти дальше
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        link_selectors = [
            "td.result-link a[href]",         # lite
            "div.result__body a.result__a",   # html
            "a.result__a[href]",              # html fallback
            "a[href^='/l/?']",                # редиректы
        ]
        seen = set()
        for sel in link_selectors:
            for a in soup.select(sel):
                href = a.get("href")
                title = _clean(a.get_text())
                if not href or not title:
                    continue
                if href.startswith("/l/?"):
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    if "uddg" in qs:
                        href = urllib.parse.unquote(qs["uddg"][0])
                if not _domain_matches(href, allowed):
                    continue
                key = (title, href)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"title": title, "url": href, "snippet": ""})
                if len(out) >= max_results:
                    return out
        return out

    try:
        with httpx.Client(follow_redirects=True, headers=headers, timeout=TIMEOUT) as client:
            results = _parse_ddg_html(client, "https://duckduckgo.com/lite/", query)
            if not results:
                results = _parse_ddg_html(client, "https://duckduckgo.com/html/", query)
            if results:
                return results[:max_results]
    except Exception:
        pass

    return results[:max_results]

# ---------- Спец-поиски ----------
def _search_docs_python_org(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Поиск по индекс-файлу Sphinx: https://docs.python.org/<ver>/searchindex.js
    Без JS-рендеринга. Плюс ранжирование по совпадениям.
    """
    import json as _json

    headers = {"User-Agent": UA}
    versions = ["3.13", "3"]
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9_.]+", query)]

    def _flatten_idxs(val) -> List[int]:
        out = []
        if isinstance(val, int):
            out.append(val)
        elif isinstance(val, list):
            for x in val:
                if isinstance(x, int):
                    out.append(x)
                elif isinstance(x, list) and x:
                    out.append(x[0])
        return out

    results: List[Dict[str, Any]] = []

    with httpx.Client(follow_redirects=True, headers=headers, timeout=TIMEOUT) as client:
        for ver in versions:
            try:
                url = f"https://docs.python.org/{ver}/searchindex.js"
                r = client.get(url)
                r.raise_for_status()
                text = r.text

                m = re.search(r"Search\.setIndex\((\{.*\})\);?\s*$", text, re.S)
                if not m:
                    continue
                data = _json.loads(m.group(1))

                docnames = data.get("docnames", [])
                titles = data.get("titles", [])
                terms = data.get("terms", {})

                sets = []
                for tok in tokens:
                    if tok in terms:
                        idxs = set(_flatten_idxs(terms[tok]))
                        if idxs:
                            sets.append(idxs)
                    else:
                        cand = set()
                        for k, v in terms.items():
                            if tok in k:
                                cand.update(_flatten_idxs(v))
                        if cand:
                            sets.append(cand)

                if sets:
                    docs = set.intersection(*sets) if len(sets) > 1 else sets[0]
                else:
                    docs = {i for i, name in enumerate(docnames) if all(t in name.lower() for t in tokens)}

                def _score(i: int) -> int:
                    name = (docnames[i] if i < len(docnames) else "").lower()
                    title_i = (titles[i] if i < len(titles) else "").lower()
                    score = 0
                    for t in tokens:
                        if t in title_i:
                            score += 3
                        if t in name:
                            score += 2
                    if "asyncio" in title_i or "asyncio" in name:
                        score += 3
                    return score

                if any(t == "asyncio" for t in tokens):
                    pref = [i for i in docs if (
                        "asyncio" in (titles[i] if i < len(titles) else "").lower()
                        or "asyncio" in (docnames[i] if i < len(docnames) else "").lower()
                    )]
                    docs = pref or list(docs)

                docs = sorted(docs, key=_score, reverse=True)

                for i in docs:
                    if i < 0 or i >= len(docnames):
                        continue
                    name = docnames[i]
                    title = (titles[i] if i < len(titles) else "") or name
                    results.append({
                        "title": title,
                        "url": f"https://docs.python.org/{ver}/{name}.html",
                        "snippet": ""
                    })
                    if len(results) >= max_results:
                        return results
            except Exception:
                continue

    return results

def _search_pypi(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Поиск по PyPI:
    1) Если запрос — одно слово (имя пакета), пробуем JSON API: /pypi/<name>/json.
    2) Фоллбек: HTML-страница поиска.
    """
    headers = {"User-Agent": UA}
    q = (query or "").strip()
    results: List[Dict[str, Any]] = []

    # 1) точное имя пакета -> JSON API
    if re.match(r"^[A-Za-z0-9_.\-]+$", q):
        try:
            with httpx.Client(follow_redirects=True, headers=headers, timeout=TIMEOUT) as client:
                r = client.get(f"https://pypi.org/pypi/{q}/json")
                if r.status_code == 200:
                    data = r.json()
                    info = data.get("info", {}) or {}
                    name = info.get("name") or q
                    summary = _clean(info.get("summary") or "")
                    url = f"https://pypi.org/project/{name}/"
                    results.append({"title": name, "url": url, "snippet": summary})
                    return results[:max_results]
        except Exception:
            pass  # молча падаем на фоллбек

    # 2) HTML фоллбек
    try:
        params = {"q": q}
        with httpx.Client(follow_redirects=True, headers=headers, timeout=TIMEOUT) as client:
            resp = client.get("https://pypi.org/search/", params=params)
            if resp.is_success and ("package-snippet" in resp.text or "/project/" in resp.text):
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.select("a.package-snippet, a[href^='/project/']"):
                    href = a.get("href")
                    if not href:
                        continue
                    url = "https://pypi.org" + href if href.startswith("/") else href
                    title_tag = a.select_one("h3.package-snippet__title") or a
                    name = title_tag.select_one(".package-snippet__name").get_text(strip=True) if title_tag.select_one(".package-snippet__name") else _clean(title_tag.get_text())
                    version = title_tag.select_one(".package-snippet__version").get_text(strip=True) if title_tag.select_one(".package-snippet__version") else ""
                    title = f"{name} {version}".strip()
                    desc = a.select_one("p.package-snippet__description")
                    snippet = _clean(desc.get_text()) if desc else ""
                    results.append({"title": title, "url": url, "snippet": snippet})
                    if len(results) >= max_results:
                        break
    except Exception:
        pass

    return results[:max_results]

# ---------- Публичные обёртки ----------
def docs_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Прямой поиск по Python Docs (индекс Sphinx)."""
    return _search_docs_python_org(query, max_results=max_results)

def http_get(url: str, max_chars: int = 2000, timeout: int = TIMEOUT) -> Dict[str, Any]:
    """Простой GET: вернёт статус, длину и первые max_chars HTML."""
    headers = {"User-Agent": UA}
    with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
        resp = client.get(url)
    text = resp.text if isinstance(resp.text, str) else str(resp.text)
    return {"status": resp.status_code, "length": len(text), "preview": text[:max_chars]}

def web_fetch(
    url: str,
    max_chars: int = 20000,
    timeout: int = TIMEOUT,
    use_cache: bool = True,
    ttl_sec: int = 60 * 60 * 24 * 3  # 3 дня
) -> Dict[str, Any]:
    """
    Забирает страницу и выжимает читаемый текст (Readability -> BeautifulSoup).
    Кэширует результат (storage/web_cache) на ttl_sec.
    Возвращает: {title, url, text, cached: bool}
    """
    if use_cache:
        hit = _cache_get(url, ttl_sec=ttl_sec)
        if hit:
            txt = hit.get("text", "")
            if len(txt) > max_chars:
                txt = txt[:max_chars]
            return {"title": hit.get("title", ""), "url": url, "text": txt, "cached": True}

    headers = {"User-Agent": UA}
    with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.text

    # основной контент через Readability
    try:
        doc = Document(html)
        title = _clean(doc.short_title())
        summary_html = doc.summary(html_partial=True)
        soup = BeautifulSoup(summary_html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except Exception:
        # фоллбек: целый текст страницы
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = _clean(soup.title.get_text() if soup.title else "")
        text = soup.get_text(separator="\n")

    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) > max_chars:
        text = text[:max_chars]

    if use_cache:
        _cache_set(url, {"title": title, "text": text})

    return {"title": title, "url": url, "text": text, "cached": False}

