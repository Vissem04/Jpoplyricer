"""TJ미디어 노래방 곡번호 조회.

공식 API는 없으나 공개 검색 페이지(/song/accompaniment_search)가 결과를 서버렌더로
반환하므로 이를 파싱한다. 추론하지 않고 실제 DB를 조회하므로 정확하다.
찾지 못하면 None 을 반환(상위에서 '-' 표시).
"""
import re

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.tjmedia.com/song/accompaniment_search"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _strip_parens(s: str) -> str:
    """괄호 보조표기 제거(검색어용, 일본어 본문은 유지)."""
    return re.sub(r"[(（【\[].*?[)）】\]]", "", s or "").strip()


def _norm(s: str) -> str:
    """비교용 정규화: 공백·괄호내용·기호 제거, 소문자."""
    s = _strip_parens(s)
    s = re.sub(r"[^0-9a-zA-Z぀-ヿ一-鿿가-힣]", "", s)
    return s.lower()


def _search(query: str, nation: str = "", str_type: int = 0) -> list[dict]:
    """TJ 검색 후 결과 행 목록 반환: [{number, title, artist}]."""
    params = {
        "nationType": nation,
        "strType": str_type,
        "searchTxt": re.sub(r"\s+", "", query or ""),
    }
    resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    for ul in soup.select("ul.grid-container.list"):
        num_el = ul.select_one(".num2")
        if not num_el:
            continue
        number = num_el.get_text(strip=True)
        if not number.isdigit():
            continue
        title_el = ul.select_one(".grid-item.title3")
        singer_el = ul.select_one(".grid-item.title4")
        results.append({
            "number": number,
            "title": title_el.get_text(" ", strip=True) if title_el else "",
            "artist": singer_el.get_text(" ", strip=True) if singer_el else "",
        })
    return results


def find_number(title: str, artist: str) -> str | None:
    """제목/아티스트로 TJ 곡번호를 찾는다. 없으면 None.

    일본어 원제로 검색(제목이 가장 변별력 높음)하고, 제목 일치 + 아티스트 보조로 최선의 행 선택.
    """
    core_title = _norm(title)
    if not core_title:
        return None
    artist_norm = _norm(artist)

    # 핵심 제목(괄호 제거)으로 검색. 일본곡 우선 -> 전체 국가 순.
    qtitle = _strip_parens(title) or title
    queries = [
        (qtitle, "JPN"),
        (qtitle, ""),
        (title, "JPN"),
    ]
    seen = set()
    candidates: list[dict] = []
    for q, nation in queries:
        try:
            rows = _search(q, nation=nation, str_type=0)
        except Exception:
            continue
        for r in rows:
            if r["number"] in seen:
                continue
            seen.add(r["number"])
            candidates.append(r)
        if candidates:
            break  # 첫 쿼리에서 결과가 나오면 그걸로 충분

    if not candidates:
        return None

    # 점수: 제목 포함(양방향) 우선, 아티스트 일치 보조
    best, best_score = None, 0
    for r in candidates:
        rt, ra = _norm(r["title"]), _norm(r["artist"])
        score = 0
        if core_title and (core_title in rt or rt in core_title):
            score += 100
        elif core_title and rt and (core_title[:6] in rt):
            score += 40
        if artist_norm and ra and (artist_norm in ra or ra in artist_norm):
            score += 30
        if score > best_score:
            best, best_score = r, score

    # 제목 매칭이 전혀 없으면 신뢰하지 않음
    if best is None or best_score < 40:
        return None
    return best["number"]
