"""일본어 -> 한국어 독음(한글) 결정론적 변환.

GPT가 만든 히라가나 요미가나를 입력받아 규칙 기반으로 한글로 변환한다.
한자가 섞여 들어와도 pykakasi로 히라가나화한 뒤 변환하므로 '미변환 일본어'가 남지 않는다.
"""
import re

import pykakasi

_kks = pykakasi.kakasi()
_tagger = None

# 형태소 앞에 공백을 넣지 않을 품사(앞 단어에 붙는 것들)
_NO_SPACE_BEFORE = {"助詞", "助動詞", "接尾辞", "補助記号", "空白", "記号"}


def _get_tagger():
    """fugashi(UniDic) 형태소 분석기 지연 로드. 미설치 시 None."""
    global _tagger
    if _tagger is None:
        try:
            import fugashi
            _tagger = fugashi.Tagger()
        except Exception:
            _tagger = False  # 실패 표시(재시도 방지)
    return _tagger or None

# 한글 자모 (조합용)
_CHO = ["ㄱ","ㄲ","ㄴ","ㄷ","ㄸ","ㄹ","ㅁ","ㅂ","ㅃ","ㅅ","ㅆ","ㅇ","ㅈ","ㅉ","ㅊ","ㅋ","ㅌ","ㅍ","ㅎ"]
_JUNG = ["ㅏ","ㅐ","ㅑ","ㅒ","ㅓ","ㅔ","ㅕ","ㅖ","ㅗ","ㅘ","ㅙ","ㅚ","ㅛ","ㅜ","ㅝ","ㅞ","ㅟ","ㅠ","ㅡ","ㅢ","ㅣ"]
_JONG = ["","ㄱ","ㄲ","ㄳ","ㄴ","ㄵ","ㄶ","ㄷ","ㄹ","ㄺ","ㄻ","ㄼ","ㄽ","ㄾ","ㄿ","ㅀ","ㅁ","ㅂ","ㅄ","ㅅ","ㅆ","ㅇ","ㅈ","ㅊ","ㅋ","ㅌ","ㅍ","ㅎ"]

# 요음(2글자) 우선 매핑
_YOUON = {
    "きゃ": "캬", "きゅ": "큐", "きょ": "쿄",
    "ぎゃ": "갸", "ぎゅ": "규", "ぎょ": "교",
    "しゃ": "샤", "しゅ": "슈", "しょ": "쇼",
    "じゃ": "자", "じゅ": "주", "じょ": "조",
    "ちゃ": "차", "ちゅ": "추", "ちょ": "초",
    "ぢゃ": "자", "ぢゅ": "주", "ぢょ": "조",
    "にゃ": "냐", "にゅ": "뉴", "にょ": "뇨",
    "ひゃ": "햐", "ひゅ": "휴", "ひょ": "효",
    "びゃ": "뱌", "びゅ": "뷰", "びょ": "뵤",
    "ぴゃ": "퍄", "ぴゅ": "퓨", "ぴょ": "표",
    "みゃ": "먀", "みゅ": "뮤", "みょ": "묘",
    "りゃ": "랴", "りゅ": "류", "りょ": "료",
}

# 단일 가나 매핑
_KANA = {
    "あ": "아", "い": "이", "う": "우", "え": "에", "お": "오",
    "か": "카", "き": "키", "く": "쿠", "け": "케", "こ": "코",
    "が": "가", "ぎ": "기", "ぐ": "구", "げ": "게", "ご": "고",
    "さ": "사", "し": "시", "す": "스", "せ": "세", "そ": "소",
    "ざ": "자", "じ": "지", "ず": "즈", "ぜ": "제", "ぞ": "조",
    "た": "타", "ち": "치", "つ": "츠", "て": "테", "と": "토",
    "だ": "다", "ぢ": "지", "づ": "즈", "で": "데", "ど": "도",
    "な": "나", "に": "니", "ぬ": "누", "ね": "네", "の": "노",
    "は": "하", "ひ": "히", "ふ": "후", "へ": "헤", "ほ": "호",
    "ば": "바", "び": "비", "ぶ": "부", "べ": "베", "ぼ": "보",
    "ぱ": "파", "ぴ": "피", "ぷ": "푸", "ぺ": "페", "ぽ": "포",
    "ま": "마", "み": "미", "む": "무", "め": "메", "も": "모",
    "や": "야", "ゆ": "유", "よ": "요",
    "ら": "라", "り": "리", "る": "루", "れ": "레", "ろ": "로",
    "わ": "와", "ゐ": "이", "ゑ": "에", "を": "오",
    "ゔ": "부",
    # 작은 가나(단독으로 올 때 대비)
    "ぁ": "아", "ぃ": "이", "ぅ": "우", "ぇ": "에", "ぉ": "오",
    "ゃ": "야", "ゅ": "유", "ょ": "요", "ゎ": "와",
}

# ん 뒤가 양순음이면 ㅁ받침, 그 외 ㄴ받침
_BILABIAL = set("まみむめもばびぶべぼぱぴぷぺぽ")


def _decompose(ch: str):
    code = ord(ch) - 0xAC00
    return code // 588, (code % 588) // 28, code % 28


def _add_jong(ch: str, jong: str) -> str:
    """받침 없는 한글 음절에 받침을 더한다."""
    if not ("가" <= ch <= "힣"):
        return ch
    cho, jung, cur_jong = _decompose(ch)
    if cur_jong != 0:
        return ch
    ki = _JONG.index(jong)
    return chr(0xAC00 + cho * 588 + jung * 28 + ki)


def _kata_to_hira(c: str) -> str:
    """가타카나 -> 히라가나."""
    if "ァ" <= c <= "ヶ":
        return chr(ord(c) - 0x60)
    return c


def kana_to_hangul(text: str) -> str:
    """히라가나/가타카나(+잔여 한자) 문자열을 한국어 독음으로 변환."""
    # 잔여 한자가 있으면 pykakasi로 히라가나화
    if re.search(r"[一-鿿]", text):
        text = "".join(x["hira"] for x in _kks.convert(text))

    chars = [_kata_to_hira(c) for c in text]
    out: list[str] = []
    i = 0
    n = len(chars)
    pending_sokuon = False

    def flush_sokuon():
        nonlocal pending_sokuon
        if pending_sokuon and out and "가" <= out[-1] <= "힣":
            out[-1] = _add_jong(out[-1], "ㅅ")
        pending_sokuon = False

    while i < n:
        c = chars[i]
        two = c + (chars[i + 1] if i + 1 < n else "")

        if two in _YOUON:
            flush_sokuon()
            out.append(_YOUON[two])
            i += 2
            continue
        if c in ("っ", "ッ"):
            pending_sokuon = True
            i += 1
            continue
        if c == "ん":
            nxt = chars[i + 1] if i + 1 < n else ""
            jong = "ㅁ" if nxt in _BILABIAL else "ㄴ"
            if out and "가" <= out[-1] <= "힣":
                out[-1] = _add_jong(out[-1], jong)
            else:
                out.append("음" if jong == "ㅁ" else "은")
            i += 1
            continue
        if c in ("ー", "〜", "～"):  # 장음 기호: 생략
            i += 1
            continue
        if c in _KANA:
            flush_sokuon()
            out.append(_KANA[c])
            i += 1
            continue

        # 그 외(공백·문장부호·로마자 등)는 그대로
        flush_sokuon()
        out.append(c)
        i += 1

    return "".join(out).strip()


def japanese_reading(text: str) -> str:
    """fugashi(UniDic)로 일본어 줄의 독음을 생성.

    - 단어 발음은 사전형 kana(장음 ウ/イ 유지)
    - 조사 は->ワ, へ->エ, を->オ 는 품사(助詞)로 판정해 문법적으로 정확히 변환
    - 같은 한자의 문맥별 읽기도 형태소 분석으로 구분
    """
    tagger = _get_tagger()
    if tagger is None:
        return ""  # 미설치 -> 상위에서 폴백

    pieces: list[str] = []
    for i, w in enumerate(tagger(text)):
        f = w.feature
        pos1 = getattr(f, "pos1", "") or ""
        surf = w.surface
        kana = getattr(f, "kana", None)

        # 조사 발음 보정
        if pos1 == "助詞":
            if surf == "は":
                kana = "ワ"
            elif surf == "へ":
                kana = "エ"
            elif surf == "を":
                kana = "オ"

        if not kana or kana == "*":
            kana = surf  # 미지어/기호/숫자/영어 등은 표면형 유지

        # 단어 경계 공백(조사·조동사·접미사 등은 앞에 붙임)
        if i > 0 and pos1 not in _NO_SPACE_BEFORE:
            pieces.append(" ")
        pieces.append(kana)

    return kana_to_hangul("".join(pieces))


def _correct_particles_and_space(yomigana_hiragana: str) -> str:
    """GPT 히라가나 요미가나를 fugashi로 토큰화해 조사 발음을 교정하고 단어 경계 공백 부여.

    - 한자 읽기는 입력(GPT)을 그대로 신뢰 -> 文脈/시적 읽기 보존 (예: 水面->みなも)
    - 조사 は->わ, へ->え, を->お 만 품사(助詞)로 판정해 교정 (はくぎん 의 は 등은 그대로)
    """
    tagger = _get_tagger()
    text = re.sub(r"\s+", "", yomigana_hiragana)
    if tagger is None:
        return text

    pieces: list[str] = []
    for i, w in enumerate(tagger(text)):
        pos1 = getattr(w.feature, "pos1", "") or ""
        surf = w.surface
        kana = surf
        if pos1 == "助詞":
            if surf == "は":
                kana = "わ"
            elif surf == "へ":
                kana = "え"
            elif surf == "を":
                kana = "お"
        if i > 0 and pos1 not in _NO_SPACE_BEFORE:
            pieces.append(" ")
        pieces.append(kana)
    return "".join(pieces)


def to_korean_reading(japanese: str, yomigana: str = "") -> str:
    """독음 생성.

    우선순위:
    1) 영어가 섞인 줄: GPT 요미가나(영어 발음 한글 포함)를 그대로 변환.
    2) 순수 일본어 + GPT 히라가나 요미가나: GPT의 한자 읽기(문맥/시적) + fugashi 조사 교정.
    3) 폴백: fugashi 로 원문 직접 변환(조사 정확, 한자는 사전 기본 읽기).
    """
    has_latin = bool(re.search(r"[A-Za-z]", japanese))
    ymg = (yomigana or "").strip()

    if has_latin:
        return kana_to_hangul(ymg or japanese)

    # GPT 요미가나가 있고 한자가 남아있지 않으면: GPT 한자읽기 + fugashi 조사교정
    if ymg and not re.search(r"[一-鿿]", ymg):
        corrected = _correct_particles_and_space(ymg)
        return kana_to_hangul(corrected)

    # 폴백: fugashi 로 원문 직접 변환
    jp = japanese_reading(japanese)
    if jp:
        return jp
    return kana_to_hangul(ymg or japanese)
