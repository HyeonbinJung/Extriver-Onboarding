#!/usr/bin/env python3
"""Hourly Korea influencer discovery. Only store explicitly public contact emails."""
from __future__ import annotations

import csv
import html
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse, unquote

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "korean_influencer_leads.csv"
GLOBAL = ROOT / "data" / "extriver_influencer_leads.csv"
CAP = max(1, min(30, int(os.getenv("MAX_LEADS", "30"))))
MAX_QUERIES = max(1, int(os.getenv("MAX_QUERIES", "36")))
DEADLINE = time.monotonic() + max(90, int(os.getenv("MAX_RUNTIME_SECONDS", "1500")))
SERPER_KEY = os.getenv("SERPER_API_KEY", "").strip()

FIELDS = [
    "Creator Name", "Category", "Public business email", "Email status",
    "Instagram URL", "YouTube URL", "TikTok URL", "Primary profile URL",
    "Contact evidence URL", "Discovered at (UTC)", "Source query", "Notes"
]

# Query order rotates hourly, and search results are paginated to limit repeats.
QUERIES = {
    "금융·경제·투자": [
        '한국 재테크 유튜버 비즈니스 문의 이메일',
        '국내 주식 투자 인스타그램 협업 이메일',
        '경제 금융 유튜브 비즈니스 문의 gmail.com',
        'site:instagram.com 재테크 "협업" "gmail.com"',
    ],
    "취업·커리어": [
        '한국 취업 커리어 인플루언서 광고 문의 이메일',
        '직장인 이직 인스타그램 협업 메일',
        'site:youtube.com/@ 취업 "비즈니스 문의" "@"',
    ],
    "입시·교육": [
        '대학 입시 교육 유튜버 비즈니스 문의 이메일',
        '공부법 수능 인스타그램 협업 gmail.com',
        '유학 입시 컨설팅 크리에이터 광고 문의',
    ],
    "뷰티·패션": [
        '한국 뷰티 유튜버 협업 문의 이메일',
        '패션 인스타그램 크리에이터 비즈니스 문의 이메일',
        'site:instagram.com 뷰티 "협찬" "naver.com"',
    ],
    "IT·테크": [
        '한국 테크 유튜버 비즈니스 이메일 문의',
        '개발자 IT 인스타그램 광고 협업 이메일',
        '노트북 테크 리뷰 크리에이터 비즈니스 문의',
    ],
    "게임·엔터": [
        '한국 게임 유튜버 비즈니스 이메일 문의',
        '마인크래프트 유튜버 광고 협업 메일',
        '한국 스트리머 비즈니스 문의 이메일',
    ],
    "여행·맛집": [
        '한국 여행 유튜버 비즈니스 이메일 문의',
        '맛집 인스타그램 협업 문의 이메일',
        '국내 여행 크리에이터 광고 문의 gmail.com',
    ],
    "운동·건강": [
        '한국 헬스 유튜버 광고 협업 이메일',
        '피트니스 인스타그램 비즈니스 문의 메일',
        '운동 크리에이터 비즈니스 협업 이메일',
    ],
    "육아·라이프스타일": [
        '한국 육아 인플루언서 협업 문의 이메일',
        '국내 라이프스타일 브이로그 비즈니스 이메일',
        '인테리어 살림 인스타그램 협업 문의 메일',
    ],
}
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@(?:[\w-]+\.)+[A-Za-z]{2,24}(?![\w.-])")
SOCIAL = ("youtube.com", "youtu.be", "instagram.com", "tiktok.com")
BAD_DOMAINS = {
    "example.com", "domain.com", "email.com", "test.com",
    "youtube.com", "instagram.com", "tiktok.com", "google.com",
    "facebook.com", "x.com", "twitter.com", "sentry.io",
}
BAD_LOCAL = {"example", "test", "no-reply", "noreply", "privacy", "support", "abuse"}
IGNORED_WEB_HOSTS = {
    "feedspot.com", "modash.io", "socialblade.com", "namu.wiki", "wikipedia.org",
    "playboard.co", "vling.net", "influencers.feedspot.com", "fandom.com",
    "linktr.ee", "lit.link", "beacons.ai", "youtube.com",
}
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ExtriverResearchBot/1.0; public-contact-only)"})

def clean_url(url: str) -> str:
    url = html.unescape((url or "").strip())
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ""
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if not host or host.startswith("localhost"):
            return ""
        path = unquote(parsed.path).rstrip("/")
        return urlunparse(("https", host, path, "", "", ""))
    except ValueError:
        return ""

def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")

def profile_url(url: str) -> str:
    """Return a single creator profile; never mistake a post/video/list for a creator."""
    url = clean_url(url)
    if not url:
        return ""
    h, parts = host_of(url), [p for p in urlparse(url).path.split("/") if p]
    if "instagram.com" in h and parts:
        if parts[0].lower() in {"p", "reel", "stories", "explore", "accounts", "direct", "tags"}:
            return ""
        return "https://www.instagram.com/" + parts[0].lower()
    if "youtube.com" in h and parts:
        if parts[0].startswith("@") or (parts[0] in {"channel", "user", "c"} and len(parts) > 1):
            return "https://www.youtube.com/" + "/".join(parts[:1] if parts[0].startswith("@") else parts[:2])
        return ""
    if "tiktok.com" in h and parts and parts[0].startswith("@"):
        return "https://www.tiktok.com/" + parts[0].lower()
    return ""

def is_email_valid(value: str) -> bool:
    e = value.lower().strip(" .,;:()<>\"'")
    local, _, domain = e.partition("@")
    return bool(local and domain and domain not in BAD_DOMAINS
                and local not in BAD_LOCAL and len(e) <= 254
                and not e.endswith((".png", ".jpg", ".webp", ".css", ".js"))
                and ".." not in e)

def emails_in(text: str) -> list[str]:
    result = []
    for e in EMAIL_RE.findall(html.unescape(text or "")):
        e = e.lower().strip(" .,;:()<>\"'")
        if is_email_valid(e) and e not in result:
            result.append(e)
    return result

def existing_keys() -> set[str]:
    keys = set()
    for file in (OUTPUT, GLOBAL):
        if not file.is_file():
            continue
        with file.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                for field in ("Public business email", "email", "Email"):
                    if row.get(field):
                        keys.add("mail:" + row[field].strip().lower())
                for field in ("Primary profile URL", "Instagram URL", "YouTube URL", "TikTok URL"):
                    p = profile_url(row.get(field, ""))
                    if p:
                        keys.add("profile:" + p.lower())
    return keys

def search(query: str, page: int) -> list[dict]:
    if SERPER_KEY:
        try:
            res = SESSION.post("https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
                json={"q": query, "gl": "kr", "hl": "ko", "num": 20, "page": page},
                timeout=20)
            res.raise_for_status()
            return [{"title": r.get("title", ""), "body": r.get("snippet", ""),
                     "href": r.get("link", "")} for r in res.json().get("organic", [])]
        except Exception as exc:
            print(f"Serper search failed: {exc}", file=sys.stderr)
    try:
        return DDGS(timeout=15).text(query, region="kr-kr", max_results=15,
                                    page=page, backend="auto") or []
    except Exception as exc:
        print(f"Free search failed ({query}): {exc}", file=sys.stderr)
        return []

def read_page(url: str) -> tuple[str, list[str], str]:
    """Extract visible text and links only, excluding scripts / embedded trackers."""
    try:
        res = SESSION.get(url, timeout=9, allow_redirects=True)
        if res.status_code != 200 or "text/html" not in res.headers.get("content-type", ""):
            return "", [], ""
        if len(res.content) > 1_500_000:
            return "", [], ""
        soup = BeautifulSoup(res.text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        links = [a.get("href", "") for a in soup.find_all("a", href=True)]
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)[:100_000], links, title
    except requests.RequestException:
        return "", [], ""

def plausible_korean(*parts: str) -> bool:
    return any(re.search(r"[가-힣]", str(p)) for p in parts)

def display_name(title: str, profile: str, page_title: str) -> str:
    raw = (page_title or title or "").strip()
    raw = re.split(r"\s+[|•–—-]\s+| \(|\s*:\s*", raw, maxsplit=1)[0]
    for token in ("Instagram", "YouTube", "TikTok", " (@", "(@"):
        raw = raw.replace(token, "").strip()
    raw = re.sub(r"\s+", " ", raw).strip(" .-–—|")
    if len(raw) < 2 or len(raw) > 85 or raw.lower() in {"home", "contact", "about", "로그인", "홈"}:
        bits = urlparse(profile).path.strip("/").split("/")
        raw = bits[-1] if bits else ""
    return raw[:85]

def candidate(result: dict, category: str, query: str) -> dict | None:
    url = clean_url(result.get("href", ""))
    if not url:
        return None
    title, snippet = result.get("title", ""), result.get("body", "")
    host = host_of(url)
    direct_profile = profile_url(url)
    # External sites must clearly be a creator-owned page with social links.
    if not direct_profile and (any(host == h or host.endswith("." + h) for h in IGNORED_WEB_HOSTS)
                               or any(host.endswith(s) for s in SOCIAL)):
        return None
    visible, links, page_title = read_page(url)
    social_links = []
    if direct_profile:
        social_links.append(direct_profile)
    for link in links[:150]:
        p = profile_url(link)
        if p and p not in social_links:
            social_links.append(p)
    if not social_links:
        return None
    if not direct_profile and len(social_links) > 8:
        # Directory / influencer roundups are not a creator's own site.
        return None
    if not plausible_korean(title, snippet, visible[:2500]):
        return None
    # The result text may expose a public email even when platforms block scraping.
    page_emails = emails_in(visible)
    snippet_emails = emails_in(snippet)
    email = (page_emails or snippet_emails or [""])[0]
    if not email:
        return None

    primary = direct_profile or social_links[0]
    name = display_name(title, primary, page_title if not direct_profile else "")
    if not name:
        return None
    columns = {"Instagram URL": "", "YouTube URL": "", "TikTok URL": ""}
    for p in social_links:
        h = host_of(p)
        field = ("Instagram URL" if "instagram.com" in h else
                 "YouTube URL" if "youtube.com" in h else
                 "TikTok URL" if "tiktok.com" in h else "")
        if field and not columns[field]:
            columns[field] = p
    status = "페이지에 이메일 공개" if page_emails else "검색결과 스니펫 공개(원문 재확인 권장)"
    return {
        "Creator Name": name, "Category": category,
        "Public business email": email, "Email status": status,
        **columns, "Primary profile URL": primary,
        "Contact evidence URL": url,
        "Discovered at (UTC)": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Source query": query,
        "Notes": "연락처는 공개 페이지/검색결과에서 추출; 실제 제휴 담당 여부 별도 확인 필요",
    }

def run() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if not OUTPUT.exists():
        with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()
    keys = existing_keys()
    hour = int(time.time() // 3600)
    items = [(cat, q) for cat, group in QUERIES.items() for q in group]
    random.Random(hour).shuffle(items)
    page = 2 if hour % 3 == 0 else 1
    found = []
    searched = 0
    for cat, query in items[:MAX_QUERIES]:
        if len(found) >= CAP or time.monotonic() > DEADLINE:
            break
        searched += 1
        print(f"Searching [{cat}] {query}", flush=True)
        for item in search(query, page):
            if len(found) >= CAP or time.monotonic() > DEADLINE:
                break
            row = candidate(item, cat, query)
            if not row:
                continue
            mail_key = "mail:" + row["Public business email"].lower()
            profile_key = "profile:" + row["Primary profile URL"].lower()
            # Do not add creators already in either the domestic or international file.
            if mail_key in keys or profile_key in keys:
                continue
            found.append(row)
            keys.update([mail_key, profile_key])
        time.sleep(0.3)
    if found:
        with OUTPUT.open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerows(found)
    print(f"Summary: {len(found)} / {CAP} new email-backed Korean creator leads; "
          f"{searched} searches; stored in {OUTPUT.relative_to(ROOT)}")
    if not found:
        print("No verified public emails found; no invented emails or placeholder records.")

if __name__ == "__main__":
    run()
