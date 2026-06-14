"""오디오 파일 -> 대략적인 가사 텍스트 + 구간 타임스탬프 (OpenAI Whisper)."""
from pathlib import Path

from openai import OpenAI

from ..config import OPENAI_API_KEY, WHISPER_MODEL


def transcribe_audio(audio_path: Path) -> dict:
    """오디오에서 일본어 가사를 받아쓴다.

    반환: {"text": 전체텍스트, "segments": [{"start": float, "end": float, "text": str}, ...]}
    - text: 제목/가수 추론용 힌트
    - segments: 노래방 싱크용 구간 타임스탬프
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=f,
            language="ja",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    text = getattr(resp, "text", "") or ""
    segments = []
    for seg in getattr(resp, "segments", []) or []:
        # SDK 객체/딕셔너리 모두 대응
        start = getattr(seg, "start", None)
        end = getattr(seg, "end", None)
        seg_text = getattr(seg, "text", None)
        if start is None and isinstance(seg, dict):
            start, end, seg_text = seg.get("start"), seg.get("end"), seg.get("text")
        segments.append({
            "start": float(start or 0.0),
            "end": float(end or 0.0),
            "text": (seg_text or "").strip(),
        })

    return {"text": text, "segments": segments}
