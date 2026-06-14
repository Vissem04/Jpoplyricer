"""로컬 강제정렬(stable-ts): 정식 가사 텍스트를 오디오에 직접 정렬해 줄별 시작시각 산출.

WhisperX와 달리 '아는 텍스트'를 오디오에 박아 넣는 방식이라 한자 가사도 그대로 처리한다.
stable-ts 미설치/실패 시 None 을 반환해 상위에서 GPT 정렬로 폴백한다.
"""
import os
import re

_MODEL = None
_MODEL_NAME = None


def _strip_ws(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _get_model():
    """stable-ts 모델을 지연 로드(전역 캐시)."""
    global _MODEL, _MODEL_NAME
    model_name = os.getenv("STABLE_TS_MODEL", "small")
    if _MODEL is not None and _MODEL_NAME == model_name:
        return _MODEL
    import stable_whisper  # 미설치면 ImportError -> 상위에서 폴백
    _MODEL = stable_whisper.load_model(model_name)
    _MODEL_NAME = model_name
    return _MODEL


def _map_lines_to_words(lines: list[str], words: list) -> list[float]:
    """단어 타임스탬프 시퀀스를 각 줄의 글자 수만큼 소비하며 줄별 시작시각을 매핑.

    align 은 우리가 넣은 '정식 가사 텍스트 그대로' 정렬하므로
    단어들을 이어붙이면 원문이 복원된다 -> 글자 단위 매핑이 정확하다.
    """
    starts: list[float] = []
    wi = 0
    n = len(words)
    last_start = 0.0

    for line in lines:
        target = _strip_ws(line)
        if not target:
            starts.append(last_start)
            continue
        if wi >= n:
            starts.append(last_start)
            continue

        start = float(getattr(words[wi], "start", last_start) or last_start)
        consumed = 0
        # 이 줄의 글자 수만큼 단어를 소비
        while wi < n and consumed < len(target):
            w_text = _strip_ws(getattr(words[wi], "word", ""))
            consumed += len(w_text)
            wi += 1
        starts.append(start)
        last_start = start

    # 단조 증가 보정
    out: list[float] = []
    prev = 0.0
    for v in starts:
        v = max(float(v), prev)
        out.append(round(v, 2))
        prev = v
    return out


def align_lines(audio_path, lines: list[str]) -> list[float] | None:
    """각 가사 줄의 시작시각(초) 리스트. stable-ts 미설치/실패 시 None."""
    if not lines:
        return []
    try:
        model = _get_model()
    except Exception:
        return None  # 미설치 등 -> 폴백

    try:
        full_text = "\n".join(lines)
        result = model.align(str(audio_path), full_text, language="ja")
        # 전체 단어 시퀀스(순서 보장)
        words = []
        for seg in getattr(result, "segments", []) or []:
            words.extend(getattr(seg, "words", []) or [])
        if not words:
            return None
        return _map_lines_to_words(lines, words)
    except Exception:
        return None
