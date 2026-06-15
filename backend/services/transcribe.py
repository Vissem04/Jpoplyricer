"""오디오 파일 -> 대략적인 가사 텍스트 + 구간 타임스탬프 (OpenAI Whisper)."""
from pathlib import Path

from openai import OpenAI

from ..config import OPENAI_API_KEY, WHISPER_MODEL


def transcribe_audio(audio_path: Path) -> dict:
    """오디오에서 일본어 가사를 받아쓴다.

    반환: {"text": 전체텍스트, "segments": [...], "words": [...]}
    - text: 제목/가수 추론용 힌트
    - segments: [{"start","end","text"}] (구간)
    - words:    [{"start","end","word"}] (단어 단위 — 노래방 싱크 정렬용)
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=f,
            language="ja",
            response_format="verbose_json",
            # 단어 단위 타임스탬프까지 요청(그 오디오의 실제 발화 시각 -> 정확한 싱크)
            timestamp_granularities=["segment", "word"],
        )

    text = getattr(resp, "text", "") or ""

    def _g(obj, key):
        v = getattr(obj, key, None)
        if v is None and isinstance(obj, dict):
            v = obj.get(key)
        return v

    segments = []
    for seg in getattr(resp, "segments", []) or []:
        segments.append({
            "start": float(_g(seg, "start") or 0.0),
            "end": float(_g(seg, "end") or 0.0),
            "text": (_g(seg, "text") or "").strip(),
        })

    words = []
    for w in getattr(resp, "words", []) or []:
        wt = (_g(w, "word") or "").strip()
        if not wt:
            continue
        start = _g(w, "start")
        end = _g(w, "end")
        words.append({
            "start": float(start or 0.0),
            "end": float(end if end is not None else start or 0.0),
            "word": wt,
        })

    return {"text": text, "segments": segments, "words": words}
