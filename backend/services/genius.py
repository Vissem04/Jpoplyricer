"""Genius로 정식 가사 가져오기.

검색은 공식 인증 API(api.genius.com/search)를 쓰고,
가사 본문은 genius.com HTML 페이지를 브라우저 User-Agent로 스크래핑한다.
(lyricsgenius 기본 동작은 인증 없는 공개 엔드포인트라 403이 난다.)
"""
import re

import requests
from bs4 import BeautifulSoup

from ..config import GENIUS_ACCESS_TOKEN

SEARCH_URL = "https://api.genius.com/search"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _search_hits(query: str) -> list[dict]:
    resp = requests.get(
        SEARCH_URL,
        params={"q": query},
        headers={"Authorization": f"Bearer {GENIUS_ACCESS_TOKEN}"},
        timeout=15,
    )
    resp.raise_for_status()
    return [h["result"] for h in resp.json().get("response", {}).get("hits", [])]


MAX_LYRICS_LINES = 220  # 이보다 길면 가사 페이지가 아닌 잘못된 페이지로 간주


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


def _is_genius_meta(name: str) -> bool:
    """Genius 공식 메타 계정(Romanizations/Japan/English Translations 등)인가."""
    return _norm(name).startswith("genius")


def _core_title(title: str) -> str:
    """제목에서 괄호 보조표기를 떼어낸 핵심 부분."""
    return _norm(re.split(r"[(（]", title or "", 1)[0])


def _rank_candidates(hits: list[dict], title: str, artist: str) -> list[dict]:
    """메타 계정 제외 + 제목/아티스트 매칭 점수로 정렬."""
    core = _core_title(title)
    artist_norm = _norm(artist)

    scored = []
    for i, h in enumerate(hits):
        name = h["primary_artist"]["name"]
        if _is_genius_meta(name):
            continue  # 로마자/번역/목록 등 메타 계정 제외
        score = 0
        hit_title = _norm(h.get("title", ""))
        if core and core in hit_title:
            score += 100  # 제목 일치 최우선
        if artist_norm and artist_norm in _norm(name):
            score += 30
        score -= i  # 동점이면 검색 상위(원곡 가능성 높음) 우선
        scored.append((score, i, h))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [h for _, _, h in scored]


def _scrape_lyrics(url: str) -> str:
    resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    containers = soup.select('div[data-lyrics-container="true"]')
    if not containers:
        return ""

    parts: list[str] = []
    for c in containers:
        # <br> 를 줄바꿈으로
        for br in c.find_all("br"):
            br.replace_with("\n")
        parts.append(c.get_text())
    text = "\n".join(parts)

    # 맨 앞 "N ContributorsTranslations...곡명 Lyrics" 헤더 제거
    # (DOTALL 미사용 -> 첫 줄 안에서만 매칭)
    text = re.sub(r"^.*?Lyrics", "", text, count=1)
    # 끝부분 "12Embed" / "Embed" 제거
    text = re.sub(r"\d*Embed\s*$", "", text.strip())
    # [Verse], [Chorus] 등 구조 주석 제거
    text = re.sub(r"\[.*?\]", "", text)
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def _norm_jp(s: str) -> str:
    """일본어 문자만 남김(공백·문장부호·로마자 제거)."""
    return re.sub(r"[^ぁ-んァ-ヶ一-鿿]", "", s or "")


def _similarity(transcription: str, lyrics: str, n: int = 4) -> float:
    """Whisper 받아쓰기와 가사의 문자 n-gram 포함도(0~1).

    같은 곡이면 받아쓰기의 특징적 n-gram 상당수가 가사에 포함된다.
    """
    a = _norm_jp(transcription)
    b = _norm_jp(lyrics)
    if len(a) < n or len(b) < n:
        return 0.0
    ga = {a[i:i + n] for i in range(len(a) - n + 1)}
    gb = {b[i:i + n] for i in range(len(b) - n + 1)}
    if not ga:
        return 0.0
    return len(ga & gb) / len(ga)


def text_similarity(a: str, b: str, n: int = 4) -> float:
    """두 텍스트의 문자 n-gram 유사도(0~1). 방향 무관(양방향 포함도의 최댓값)."""
    return max(_similarity(a, b, n), _similarity(b, a, n))


# 받아쓰기-가사 매칭 임계값/탐색 한도
VERIFY_THRESHOLD = 0.25   # 이 이상이면 같은 곡으로 판단
VERIFY_STRONG = 0.55      # 이 이상이면 즉시 채택(빠른 종료)
MAX_SCRAPES = 10          # 검증을 위해 스크래핑할 최대 페이지 수


def fetch_verified_lyrics(queries: list[str], transcription: str,
                          candidates: list[dict] | None = None) -> dict:
    """여러 검색어로 후보를 모으고, Whisper 받아쓰기와 대조 검증해 가장 잘 맞는 가사를 반환.

    환각으로 엉뚱한 곡이 나오는 것을 방지한다. 임계값 미만이면 found=False.
    반환: {"found", "title", "artist", "url", "lyrics", "score"}
    """
    # 검색어 구성: 명시 검색어 + 후보(artist title / title) (중복 제거, 순서 유지)
    q_list: list[str] = []
    for q in queries or []:
        if q and q not in q_list:
            q_list.append(q)
    for c in candidates or []:
        t, a = c.get("title", ""), c.get("artist", "")
        if a and a.lower() != "unknown":
            cq = f"{a} {t}".strip()
            if cq and cq not in q_list:
                q_list.append(cq)
        if t and t not in q_list:
            q_list.append(t)

    # 후보 URL 풀 수집(검색어 순서대로, 중복 제거)
    pool: list[dict] = []
    seen_urls: set[str] = set()
    for q in q_list:
        try:
            hits = _search_hits(q)
        except Exception:
            continue
        for h in hits:
            if h["url"] not in seen_urls:
                seen_urls.add(h["url"])
                pool.append(h)

    # 메타 계정(로마자/번역/목록)은 후순위로
    pool.sort(key=lambda h: _is_genius_meta(h["primary_artist"]["name"]))

    best = None  # (score, result)
    scrapes = 0
    for h in pool:
        if scrapes >= MAX_SCRAPES:
            break
        lyrics = _scrape_lyrics(h["url"])
        scrapes += 1
        if not lyrics or len(lyrics.splitlines()) > MAX_LYRICS_LINES:
            continue
        score = _similarity(transcription, lyrics)
        if best is None or score > best[0]:
            best = (score, {
                "found": True,
                "title": h.get("title", ""),
                "artist": h["primary_artist"]["name"],
                "url": h["url"],
                "lyrics": lyrics,
                "score": round(score, 3),
            })
        if score >= VERIFY_STRONG:
            break  # 확실한 매칭 -> 즉시 종료

    if best and best[0] >= VERIFY_THRESHOLD:
        return best[1]
    return {"found": False, "title": "", "artist": "", "url": "", "lyrics": "",
            "score": round(best[0], 3) if best else 0.0}


def fetch_lyrics_by_title(candidates: list[dict] | None) -> dict:
    """받아쓰기 검증이 불가능할 때(반주/MR·연주 트랙 등 보컬 없음) 제목·아티스트만으로 가사를 찾는다.

    환각으로 엉뚱한 곡이 채택되지 않도록, Genius 결과 제목이 후보 제목과 실제로
    일치(핵심 제목 양방향 포함)할 때만 채택한다. 일치가 없으면 found=False.
    반환: fetch_verified_lyrics 와 동일한 스키마({found,title,artist,url,lyrics,score}).
    """
    for c in candidates or []:
        title = (c.get("title") or "").strip()
        artist = (c.get("artist") or "").strip()
        if not title:
            continue
        r = fetch_lyrics(title, artist)
        if not r.get("found"):
            continue
        core = _core_title(title)
        got = _norm(r.get("title", ""))
        if core and got and (core in got or got[: len(core)] in core or core[:6] in got):
            return {
                "found": True,
                "title": r["title"],
                "artist": r["artist"],
                "url": r["url"],
                "lyrics": r["lyrics"],
                "score": None,  # 받아쓰기 검증이 아닌 제목 매칭으로 채택됨
            }
    return {"found": False, "title": "", "artist": "", "url": "", "lyrics": "", "score": 0.0}


def fetch_lyrics(title: str, artist: str) -> dict:
    """제목/아티스트로 Genius에서 가사를 검색/스크래핑해 반환.

    여러 쿼리로 후보를 모아 메타 계정을 제외하고, 제목 매칭 순으로 후보를
    하나씩 스크래핑한다. 비정상적으로 긴(=잘못된) 페이지는 건너뛴다.

    반환: {"found": bool, "title", "artist", "url", "lyrics"}
    """
    try:
        # 여러 쿼리로 후보 수집(중복 url 제거, 순서 유지)
        seen_urls = set()
        hits: list[dict] = []
        for q in (f"{artist} {title}".strip(), title, f"{title} {artist}".strip()):
            if not q:
                continue
            for h in _search_hits(q):
                if h["url"] not in seen_urls:
                    seen_urls.add(h["url"])
                    hits.append(h)

        candidates = _rank_candidates(hits, title, artist)
        if not candidates:
            return {"found": False, "title": title, "artist": artist, "url": "", "lyrics": ""}

        # 후보를 순서대로 시도: 가사가 있고 길이가 정상이면 채택
        skipped_long = False
        for cand in candidates[:5]:
            lyrics = _scrape_lyrics(cand["url"])
            if not lyrics:
                continue
            n_lines = len(lyrics.splitlines())
            if n_lines > MAX_LYRICS_LINES:
                skipped_long = True
                continue  # 가사가 아닌 잘못된 페이지(목록/모음 등)로 간주
            return {
                "found": True,
                "title": cand.get("title", title),
                "artist": cand["primary_artist"]["name"],
                "url": cand["url"],
                "lyrics": lyrics,
            }

        msg = "정상 길이의 가사 페이지를 찾지 못했습니다." if skipped_long else ""
        return {"found": False, "error": msg, "title": title, "artist": artist,
                "url": "", "lyrics": ""}
    except Exception as e:
        return {"found": False, "error": str(e), "title": title,
                "artist": artist, "url": "", "lyrics": ""}
