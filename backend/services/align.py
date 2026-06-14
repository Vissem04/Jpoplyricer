"""Genius 가사 줄들에 Whisper 구간 타임스탬프를 정렬해 줄별 시작시각(초)을 부여."""
import json

from openai import OpenAI

from ..config import OPENAI_API_KEY, IDENTIFY_MODEL

SYSTEM_PROMPT = """너는 노래의 가사-오디오 싱크 전문가다.
입력으로 두 가지를 받는다:
1) segments: 음성인식이 만든 (start초, text) 구간 목록. text는 부정확할 수 있다.
2) lines: 정식 가사의 줄 목록(순서대로, 인덱스 포함).

두 목록은 같은 노래를 같은 순서로 다룬다. 각 정식 가사 줄(lines[i])이
오디오에서 대략 몇 초에 시작하는지 segments의 start 값을 근거로 추정하라.
규칙:
- 시작시각은 줄 순서대로 단조 증가(앞 줄보다 같거나 커야 함)해야 한다.
- segment text와 가사 줄을 발음/의미로 매칭하라(한자<->소리 차이 감안).
- 매칭이 애매하면 앞뒤 줄 사이를 자연스럽게 보간하라.
반드시 아래 JSON으로만 답하라. lines의 모든 인덱스에 대해 start를 채워라:
{"timings": [{"index": 0, "start": 12.3}, ...]}"""


def align_lines(lines: list[str], segments: list[dict]) -> list[float]:
    """각 가사 줄의 시작시각(초) 리스트를 반환. 실패 시 균등 분배로 폴백."""
    n = len(lines)
    if n == 0:
        return []

    # 오디오 길이 추정(마지막 세그먼트 end)
    duration = max((s.get("end", 0.0) for s in segments), default=0.0) or (n * 3.0)

    if not segments:
        # 타임스탬프가 없으면 균등 분배
        return [round(duration * i / n, 2) for i in range(n)]

    client = OpenAI(api_key=OPENAI_API_KEY)
    payload = {
        "segments": [
            {"start": round(s["start"], 2), "text": s["text"]}
            for s in segments if s.get("text")
        ],
        "lines": [{"index": i, "text": t} for i, t in enumerate(lines)],
    }

    starts: list[float | None] = [None] * n
    try:
        resp = client.chat.completions.create(
            model=IDENTIFY_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        data = json.loads(resp.choices[0].message.content)
        for item in data.get("timings", []):
            idx = item.get("index")
            if isinstance(idx, int) and 0 <= idx < n:
                starts[idx] = float(item.get("start", 0.0))
    except Exception:
        starts = [None] * n

    return _sanitize(starts, duration)


def _sanitize(starts: list[float | None], duration: float) -> list[float]:
    """누락 보간 + 단조 증가 + 범위 클램프."""
    n = len(starts)
    # 1) 앞쪽 누락은 0, 뒤쪽 누락은 duration 으로 임시 채움 후 보간
    known = [(i, v) for i, v in enumerate(starts) if v is not None]
    if not known:
        return [round(duration * i / n, 2) for i in range(n)]

    result = list(starts)
    # 앞쪽 None
    first_i, first_v = known[0]
    for i in range(first_i):
        result[i] = max(0.0, first_v * i / max(first_i, 1))
    # 뒤쪽 None
    last_i, last_v = known[-1]
    for i in range(last_i + 1, n):
        frac = (i - last_i) / max(n - last_i, 1)
        result[i] = last_v + (duration - last_v) * frac
    # 중간 None 보간
    for a, b in zip(known, known[1:]):
        (ia, va), (ib, vb) = a, b
        for i in range(ia + 1, ib):
            frac = (i - ia) / (ib - ia)
            result[i] = va + (vb - va) * frac

    # 단조 증가 + 클램프
    out: list[float] = []
    prev = 0.0
    for v in result:
        v = max(0.0, min(float(v or 0.0), duration))
        v = max(v, prev)
        out.append(round(v, 2))
        prev = v
    return out
