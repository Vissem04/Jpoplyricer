"""정식 가사를 '그 오디오의 Whisper 단어 타임스탬프'에 정렬해 줄별 시작시각 산출.

원리(WhisperX/강제정렬과 동일한 발상, torch 불필요):
- Whisper가 그 오디오를 받아쓴 '단어별 시각'은 (단어 내용이 좀 틀려도) 실제 발화 시각이다.
- 정식 가사(정확한 텍스트)와 Whisper 단어열을 '카나 문자' 수준에서 시퀀스 정렬하면,
  각 가사 줄을 그 오디오의 실제 시각에 박을 수 있다.
- 그 영상 오디오 자체에 맞추므로 버전/편곡/인트로 길이 차이에 영향받지 않는다.

받아쓰기가 부실(보컬 없음/실패)하면 매칭 커버리지가 낮아 None 을 반환 -> 상위에서 폴백.
"""
import difflib
import re

_KKS = None


def _kks():
    global _KKS
    if _KKS is None:
        import pykakasi
        _KKS = pykakasi.kakasi()
    return _KKS


def _to_kana(text: str) -> str:
    """일본어(한자/가타카나 포함)를 히라가나로, 영문은 소문자로 정규화(기호/공백 제거)."""
    try:
        items = _kks().convert(text or "")
    except Exception:
        items = []
    s = "".join(it.get("hira", "") for it in items).lower()
    return re.sub(r"[^ぁ-ゟ0-9a-z]", "", s)


def _fill_increasing(starts: list) -> list | None:
    """None 을 선형 보간하고 단조 증가 보장."""
    n = len(starts)
    known = [(i, t) for i, t in enumerate(starts) if t is not None]
    if not known:
        return None
    res = [0.0] * n
    fi, ft = known[0]
    for i in range(fi + 1):
        res[i] = ft if i == fi else max(0.0, round(ft - (fi - i) * 0.5, 2))
    for (i0, t0), (i1, t1) in zip(known, known[1:]):
        res[i0] = t0
        for i in range(i0 + 1, i1):
            res[i] = round(t0 + (t1 - t0) * (i - i0) / (i1 - i0), 2)
    li, lt = known[-1]
    res[li] = lt
    for i in range(li + 1, n):
        res[i] = round(lt + (i - li) * 2.0, 2)
    for i in range(1, n):
        if res[i] <= res[i - 1]:
            res[i] = res[i - 1] + 0.05
    return [round(x, 2) for x in res]


def align_lines(lines: list[str], words: list[dict], min_coverage: float = 0.22) -> list[float] | None:
    """가사 줄별 시작시각(초). 정렬 신뢰 불가 시 None.

    words: [{"word", "start", "end"}] (Whisper 단어 타임스탬프)
    """
    if not lines or not words:
        return None

    # 1) Whisper 단어 -> 카나 문자열 + 문자별 시각
    w_chars: list[str] = []
    w_times: list[float] = []
    for w in words:
        kana = _to_kana(w.get("word", ""))
        if not kana:
            continue
        s = float(w.get("start", 0.0))
        e = float(w.get("end", s))
        m = len(kana)
        for i, c in enumerate(kana):
            w_chars.append(c)
            w_times.append(s + (e - s) * (i / m) if m else s)
    w_seq = "".join(w_chars)
    if len(w_seq) < 4:
        return None

    # 2) 정식 가사 -> 카나 문자열 + 줄별 시작 문자 인덱스
    o_chars: list[str] = []
    line_first = []
    for line in lines:
        line_first.append(len(o_chars))
        o_chars.extend(_to_kana(line))
    o_seq = "".join(o_chars)
    if len(o_seq) < 4:
        return None

    # 3) 시퀀스 정렬(공통 블록) -> 정식 문자 인덱스별 시각
    sm = difflib.SequenceMatcher(a=o_seq, b=w_seq, autojunk=False)
    o_time: list = [None] * len(o_seq)
    matched = 0
    for i, j, k in sm.get_matching_blocks():
        for x in range(k):
            o_time[i + x] = w_times[j + x]
        matched += k
    if matched < max(4, min_coverage * len(o_seq)):
        return None  # 받아쓰기-가사 매칭이 부실 -> 신뢰 불가

    # 4) 각 줄 시작 = 그 줄 문자범위 내 첫 매칭 시각(없으면 None -> 보간)
    n_lines = len(lines)
    starts: list = [None] * n_lines
    for li in range(n_lines):
        lo = line_first[li]
        hi = line_first[li + 1] if li + 1 < n_lines else len(o_seq)
        for c in range(lo, hi):
            if o_time[c] is not None:
                starts[li] = o_time[c]
                break

    return _fill_increasing(starts)
