"""Uta-Net(우타넷) 일본어 가사 조회.

일본 네이티브 가사 사이트라 J-POP 가사의 한자/가나 표기 정확도가 Genius보다 대체로 높다.
Genius와 교차검증해 '맞는 곡인데 가사 내용이 틀린' 경우를 줄이는 보조 출처로 쓴다.
공식 API는 없어 검색/곡 페이지를 스크래핑한다. 찾지 못하면 found=False.
"""
import re

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.uta-net.com/search/"
SONG_URL = "https://www.uta-net.com/song/{id}/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10


def _strip_parens(s: str) -> str:
    return re.sub(r"[(（【\[].*?[)）】\]]", "", s or "").strip()


def _norm(s: str) -> str:
    s = _strip_parens(s)
    s = re.sub(r"[^0-9a-zA-Z぀-ヿ一-鿿가-힣]", "", s)
    return s.lower()


def _search(title: str) -> list[dict]:
    """제목으로 검색(Aselect=2: 곡명). [{id, title, artist}] 반환."""
    resp = requests.get(
        SEARCH_URL,
        params={"Aselect": 2, "Keyword": _strip_parens(title) or title},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rows = []
    for tr in soup.select("tbody tr"):
        song_a = tr.select_one('a[href^="/song/"]')
        artist_a = tr.select_one('a[href^="/artist/"]')
        if not song_a:
            continue
        m = re.search(r"/song/(\d+)/", song_a.get("href", ""))
        if not m:
            continue
        artist = artist_a.get_text(strip=True) if artist_a else ""
        title_txt = song_a.get_text(strip=True)
        # 제목 셀 텍스트에 아티스트가 붙어 나오는 경우 제거
        if artist and title_txt.endswith(artist):
            title_txt = title_txt[: -len(artist)].strip()
        rows.append({"id": m.group(1), "title": title_txt, "artist": artist})
    return rows


def _scrape_lyrics(song_id: str) -> str:
    resp = requests.get(SONG_URL.format(id=song_id), headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    el = soup.select_one("#kashi_area")
    if not el:
        return ""
    for br in el.find_all("br"):
        br.replace_with("\n")
    lines = [ln.strip() for ln in el.get_text().splitlines()]
    return "\n".join(ln for ln in lines if ln)


def fetch_lyrics(candidates: list[dict] | None) -> dict:
    """후보(제목/아티스트)로 Uta-Net에서 가사를 찾는다.

    반환: {"found", "title", "artist", "url", "lyrics", "source"}
    """
    for c in candidates or []:
        title = (c.get("title") or "").strip()
        artist = (c.get("artist") or "").strip()
        if not title:
            continue
        try:
            rows = _search(title)
        except Exception:
            continue
        if not rows:
            continue

        core = _norm(title)
        artist_n = _norm(artist)
        best, best_score = None, -1
        for r in rows:
            rt, ra = _norm(r["title"]), _norm(r["artist"])
            score = 0
            if core and (core in rt or rt in core):
                score += 100
            if artist_n and ra and (artist_n in ra or ra in artist_n):
                score += 30
            if score > best_score:
                best, best_score = r, score
        # 제목 일치가 전혀 없으면 신뢰하지 않음
        if not best or best_score < 100:
            continue

        try:
            lyrics = _scrape_lyrics(best["id"])
        except Exception:
            continue
        if not lyrics:
            continue
        return {
            "found": True,
            "title": best["title"],
            "artist": best["artist"],
            "url": SONG_URL.format(id=best["id"]),
            "lyrics": lyrics,
            "source": "Uta-Net",
        }

    return {"found": False, "title": "", "artist": "", "url": "",
            "lyrics": "", "source": "Uta-Net"}
