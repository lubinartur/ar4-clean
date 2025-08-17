# backend/app/tools/web.py
from __future__ import annotations

import re
import urllib.parse
from typing import List, Dict, Any, Optional

import httpx
from bs4 import BeautifulSoup
from readability import Document
from duckduckgo_search import DDGS

UA = "AIR4Bot/1.0 (+local)"
TIMEOUT = 20


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


def web_search(
    query: str,
    max_results: int = 5,
    region: str = "wt-wt",
    safesearch: str = "moderate",  # "off" | "moderate" | "strict"
    timelimit: Optional[str] = None,  # "d","w","m","y"
) -> List[Dict[str, Any]]:
    """
    Поиск с многоступенчатым фоллбеком:
    1) duckduckgo_search.DDGS().text(...)
    2) HTML парсинг DuckDuckGo (lite/html)
    3) JSON SearXNG публичные инстансы
    4) Спец-кейс: прямой поиск по docs.python.org (Sphinx)
    + пост-фильтр по 'site:domain'
    """
    results: List[Dict[str, Any]] = []

    # домены из site:
    site_tokens = re.findall(r"site:([^\s]+)", query)
    allowed = {tok.strip().lstrip(".").lower() for tok in site_tokens if tok.strip()}
    # fast-path: если фильтр по docs.python.org — используем прямой поиск по индексу Sphinx
    if allowed and any(d == "docs.python.org" or d.endswith(".docs.python.org") for d in allowed):
        q_no_site = re.sub(r"\s*site:[^\s]+", "", query).strip() or query
        try:
            return _search_docs_python_org(q_no_site, max_results=max_results)
        except Exception:
            pass


    # -----------------------
    # 1) библиотека DDGS
    # -----------------------
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

    # -----------------------
    # 2) HTML фоллбеки DDG
    # -----------------------
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    def _parse_ddg_html(client: httpx.Client, base_url: str, q: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        params = {"q": q, "kl": region, "kp": "-2", "kz": "-1"}  # no personalization
        if safesearch == "strict":
            params["kp"] = "1"
        url = base_url + "?" + urllib.parse.urlencode(params)
        resp = client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        # расширенный набор селекторов
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
                # /l/?..&uddg=<url>
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

    # -----------------------
    # 3) SearXNG JSON фоллбек
    # -----------------------
    searx_instances = [
        "https://searx.be/search",
        "https://searxng.site/search",
        "https://search.bus-hit.me/search",
    ]
    params_base = {
        "q": query,
        "format": "json",
        "language": "en",
        "safesearch": 1 if safesearch == "strict" else 0,
        "categories": "general",
    }
    for endpoint in searx_instances:
        try:
            with httpx.Client(follow_redirects=True, headers={"User-Agent": UA}, timeout=TIMEOUT) as client:
                resp = client.get(endpoint, params=params_base)
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
                    results.append({"title": title, "url": url, "snippet": snippet})
                    if len(results) >= max_results:
                        return results[:max_results]
        except Exception:
            continue

    # -----------------------
    # 4) Спец-кейс: прямой поиск по docs.python.org (Sphinx)
    # -----------------------
    try:
        if not results and (("docs.python.org" in query) or ("docs.python.org" in allowed)):
            q_no_site = re.sub(r"\s*site:[^\s]+", "", query).strip() or query
            direct = _search_docs_python_org(q_no_site, max_results=max_results)
            if direct:
                # если был site: с иным доменом — отфильтруем (на всякий)
                direct = [r for r in direct if _domain_matches(r["url"], allowed)]
                return direct[:max_results]
    except Exception:
        pass

    return results[:max_results]


def _search_docs_python_org(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Поиск по индекс-файлу Sphinx: https://docs.python.org/<ver>/searchindex.js
    Без JS-рендеринга. Плюс ранжирование по совпадениям в title/имени документа.
    """
    import json

    headers = {"User-Agent": UA}
    versions = ["3.13", "3"]  # пробуем актуальную минорную и общую ветку
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9_.]+", query)]

    def _flatten_idxs(val) -> List[int]:
        # элементы terms могут быть int или [doc, ...] — берём id документа
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
                # тянем индекс
                url = f"https://docs.python.org/{ver}/searchindex.js"
                r = client.get(url)
                r.raise_for_status()
                text = r.text

                # извлекаем JSON из "Search.setIndex({...});"
                m = re.search(r"Search\.setIndex\((\{.*\})\);?\s*$", text, re.S)
                if not m:
                    continue
                data = json.loads(m.group(1))

                docnames = data.get("docnames", [])
                titles = data.get("titles", [])
                terms = data.get("terms", {})  # word -> list[int] | list[list[int]]

                # собираем кандидатов по токенам
                sets = []
                for tok in tokens:
                    if tok in terms:
                        idxs = set(_flatten_idxs(terms[tok]))
                        if idxs:
                            sets.append(idxs)
                    else:
                        # мягкий матч: ключ содержит токен
                        cand = set()
                        for k, v in terms.items():
                            if tok in k:
                                cand.update(_flatten_idxs(v))
                        if cand:
                            sets.append(cand)

                if sets:
                    docs = set.intersection(*sets) if len(sets) > 1 else sets[0]
                else:
                    # фоллбек — фильтр по имени файла
                    docs = {i for i, name in enumerate(docnames) if all(t in name.lower() for t in tokens)}

                # --- ранжирование: предпочитаем совпадения в title/docname, бонус за 'asyncio'
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

                # если среди токенов есть 'asyncio', мягко приоритизируем такие документы
                if any(t == "asyncio" for t in tokens):
                    pref = [i for i in docs if (
                        "asyncio" in (titles[i] if i < len(titles) else "").lower()
                        or "asyncio" in (docnames[i] if i < len(docnames) else "").lower()
                    )]
                    docs = pref or list(docs)

                docs = sorted(docs, key=_score, reverse=True)

                # формируем результаты
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


def web_fetch(url: str, max_chars: int = 20000, timeout: int = TIMEOUT) -> Dict[str, Any]:
    """
    Забирает страницу и выжимает читаемый текст (Readability -> BeautifulSoup).
    Возвращает: {title, url, text}
    """
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

    # очистка и ограничение
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) > max_chars:
        text = text[:max_chars]

    return {"title": title, "url": url, "text": text}

def docs_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Прямой поиск по https://docs.python.org/3/search.html?q=..."""
    return _search_docs_python_org(query, max_results=max_results)

def http_get(url: str, max_chars: int = 2000, timeout: int = TIMEOUT) -> Dict[str, Any]:
    """Простой GET: вернёт статус, длину и первые max_chars HTML."""
    headers = {"User-Agent": UA}
    with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
        resp = client.get(url)
    text = resp.text if isinstance(resp.text, str) else str(resp.text)
    return {"status": resp.status_code, "length": len(text), "preview": text[:max_chars]}

