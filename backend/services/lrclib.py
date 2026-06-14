"""LRCLIB 동기가사(LRC) 조회.

무료·무키(API 키 불필요)로 시간동기 가사를 제공한다. 보컬이 없는 반주(MR)
트랙처럼 음향 정렬이 불가능한 경우에도 '실제 곡의 줄별 타임스탬프'를 얻어
정확한 노래방 싱크를 만들 수 있다. 동기가사가 없으면 None.
"""
import re

import requests

API = "https://lrclib.net/api"
HEADERS = {"User-Agent": "jpop-lyrics-app (local karaoke helper)"}
TIMEOUT = 10
DUR_TOLERANCE = 25  # 곡 길이가 이보다 더 차이 나는 버전은 신뢰하지 않음


def _parse_lrc(synced: str) -> list[tuple[float, str]]:
    """'[mm:ss.xx] 텍스트' 형식을 (초, 텍스트) 목록으로 파싱."""
    out: list[tuple[float, str]] = []
    for line in (synced or "").splitlines():
        m = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)", line)
        if not m:
            continue
        t = int(m.group(1)) * 60 + float(m.group(2))
        out.append((round(t, 2), m.group(3).strip()))
    return out


def fetch_synced(title: str, artist: str, duration: float = 0,
                 tolerance: float = DUR_TOLERANCE) -> list[tuple[float, str]] | None:
    """제목/아티스트(+곡 길이)로 동기가사를 찾는다.

    tolerance: 곡 길이 허용 오차(초). 이보다 더 차이 나는 버전은 타이밍이 어긋날 수
        있으므로 신뢰하지 않는다. (보컬 곡은 작게, 보컬 없는 MR은 크게 줘서 호출)
    반환: [(시작초, 가사줄)] (간주 등 빈 줄 제외) 또는 None.
    """
    title = (title or "").strip()
    if not title:
        return None
    try:
        r = requests.get(
            f"{API}/search",
            params={"track_name": title, "artist_name": (artist or "").strip()},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        items = [it for it in r.json() if it.get("syncedLyrics")]
    except Exception:
        return None
    if not items:
        return None

    # 곡 길이가 가까운 버전 우선
    if duration:
        items.sort(key=lambda it: abs((it.get("duration") or 0) - duration))
        if abs((items[0].get("duration") or 0) - duration) > tolerance:
            # 길이가 너무 다른 버전뿐이면 신뢰하지 않음(타이밍 어긋남)
            return None

    lines = _parse_lrc(items[0]["syncedLyrics"])
    lines = [(t, txt) for t, txt in lines if txt]  # 빈 줄(간주) 제외
    return lines or None
