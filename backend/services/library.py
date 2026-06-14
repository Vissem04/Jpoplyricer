"""저장된 노래(라이브러리) 관리: JSON 인덱스 + 오디오 파일 영속 저장."""
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from ..config import AUDIO_DIR, LIBRARY_FILE

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def extract_video_id(url: str) -> str:
    """유튜브 URL에서 영상 ID 추출. 실패 시 랜덤 ID."""
    patterns = [
        r"[?&]v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"/embed/([A-Za-z0-9_-]{11})",
        r"/shorts/([A-Za-z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url or "")
        if m:
            return m.group(1)
    return uuid.uuid4().hex


def is_valid_id(song_id: str) -> bool:
    return bool(song_id) and bool(_ID_RE.match(song_id)) and ".." not in song_id


def audio_path(song_id: str) -> Path:
    return AUDIO_DIR / f"{song_id}.mp3"


def _load() -> list[dict]:
    if not LIBRARY_FILE.exists():
        return []
    try:
        return json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write(records: list[dict]) -> None:
    LIBRARY_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _audio_referenced(records: list[dict], song_id: str) -> bool:
    """남은 레코드 중 해당 오디오(song_id)를 쓰는 게 있는지(다른 사용자 포함)."""
    return any(r.get("id") == song_id for r in records)


def _remove_audio_if_unused(records: list[dict], song_id: str) -> None:
    if _audio_referenced(records, song_id):
        return
    p = audio_path(song_id)
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


def save_song(song_id: str, result: dict, src_audio: Path, user: str) -> None:
    """오디오를 영속 폴더로 복사하고, 사용자별 레코드를 저장(같은 사용자+곡이면 갱신).

    오디오 파일은 영상 id 기준으로 공유한다(중복 저장 안 함).
    """
    dest = audio_path(song_id)
    try:
        if not dest.exists() or src_audio.resolve() != dest.resolve():
            shutil.copyfile(src_audio, dest)
    except Exception:
        pass

    record = dict(result)
    record["id"] = song_id
    record["user"] = user
    record["created"] = datetime.now().isoformat(timespec="seconds")

    records = _load()
    # 같은 사용자의 같은 곡만 제거(갱신). 다른 사용자 레코드는 보존.
    records = [r for r in records if not (r.get("id") == song_id and r.get("user") == user)]
    records.insert(0, record)  # 최신이 위로
    _write(records)


def list_songs(user: str) -> list[dict]:
    """해당 사용자의 저장 곡 목록(경량 메타데이터)."""
    out = []
    for r in _load():
        if r.get("user") != user:
            continue
        g = r.get("genius", {})
        out.append({
            "id": r.get("id"),
            "title": g.get("title") or r.get("video_title", ""),
            "artist": g.get("artist", ""),
            "created": r.get("created", ""),
        })
    return out


def get_song(song_id: str, user: str) -> dict | None:
    """해당 사용자가 저장한 곡만 반환."""
    for r in _load():
        if r.get("id") == song_id and r.get("user") == user:
            return r
    return None


def clear_all(user: str) -> int:
    """해당 사용자의 저장 곡 전체 삭제(다른 사용자가 안 쓰는 오디오만 파일 삭제)."""
    records = _load()
    removed = [r for r in records if r.get("user") == user]
    remaining = [r for r in records if r.get("user") != user]
    _write(remaining)
    for r in removed:
        _remove_audio_if_unused(remaining, r.get("id", ""))
    return len(removed)


def update_lines(song_id: str, user: str, new_lines: list[dict]) -> bool:
    """해당 사용자가 저장한 곡의 가사 줄(원문/독음/해석)을 갱신. 타이밍(start)은 보존."""
    records = _load()
    found = False
    for r in records:
        if r.get("id") == song_id and r.get("user") == user:
            old = r.get("lines", [])
            merged = []
            for i, nl in enumerate(new_lines):
                line = {
                    "original": str(nl.get("original", "")),
                    "reading": str(nl.get("reading", "")),
                    "translation": str(nl.get("translation", "")),
                }
                if i < len(old) and isinstance(old[i], dict) and "start" in old[i]:
                    line["start"] = old[i]["start"]
                merged.append(line)
            r["lines"] = merged
            found = True
    if found:
        _write(records)
    return found


def delete_song(song_id: str, user: str) -> bool:
    """해당 사용자의 특정 곡 삭제(다른 사용자가 안 쓰면 오디오 파일도 삭제)."""
    records = _load()
    remaining = [r for r in records if not (r.get("id") == song_id and r.get("user") == user)]
    if len(remaining) == len(records):
        return False
    _write(remaining)
    _remove_audio_if_unused(remaining, song_id)
    return True
