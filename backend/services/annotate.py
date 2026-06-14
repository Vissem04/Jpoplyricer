"""일본어 가사 각 줄 -> 한국어 독음 + 해석.

GPT는 (1) 히라가나 요미가나 (2) 한국어 해석만 생성하고,
독음(한글)은 reading.py 가 결정론적으로 변환한다. -> 미변환 일본어가 남지 않음.
"""
import json

from openai import OpenAI

from ..config import OPENAI_API_KEY, ANNOTATE_MODEL
from . import reading

SYSTEM_PROMPT = """너는 일본어를 한국인에게 가르치는 전문 번역가다.
입력으로 가사 줄들의 배열(JSON)을 받는다. 줄에는 일본어와 영어가 섞일 수 있다.
각 줄에 대해 다음을 만들어라:
1) original: 원문 (입력 그대로)
2) yomigana: 그 줄을 실제로 읽는 발음을 표기. 규칙:
   - 일본어(한자·가나) 부분 -> 히라가나로. 조사 は는 わ, へ는 え, を는 お 처럼 발음대로.
     한자는 노래에서 읽는 실제 발음의 히라가나로. (예: こたえを みつけだすのわ もう やめだ)
   - 영어·로마자 부분 -> 일본어식 가타카나로 바꾸지 말고, '영어 발음'을 한국어(한글)로 적어라.
     (예: Back to the history -> 백 투 더 히스토리,  I was born -> 아이 워즈 본,  Wow -> 와우)
   - 즉 yomigana 한 줄 안에 일본어는 히라가나, 영어는 한글 발음이 섞여도 된다.
   - 한자는 절대 남기지 마라. 단어 경계는 공백으로 구분.
3) translation: 자연스러운 한국어 해석(노래 가사답게)

반드시 아래 JSON 형식으로만 답하라. 입력 줄 수와 출력 lines 수가 정확히 같아야 한다:
{"lines": [{"original": "...", "yomigana": "...", "translation": "..."}, ...]}"""


def annotate_lyrics(lyrics: str) -> list[dict]:
    """가사 전체를 받아 줄별 {original, reading, translation} 리스트로 반환."""
    raw_lines = [ln for ln in lyrics.splitlines() if ln.strip()]
    if not raw_lines:
        return []

    client = OpenAI(api_key=OPENAI_API_KEY)

    CHUNK = 30
    results: list[dict] = []
    for i in range(0, len(raw_lines), CHUNK):
        chunk = raw_lines[i : i + CHUNK]
        user_msg = json.dumps({"lines": chunk}, ensure_ascii=False)
        resp = client.chat.completions.create(
            model=ANNOTATE_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        data = json.loads(resp.choices[0].message.content)
        lines = data.get("lines", [])
        for idx, original in enumerate(chunk):
            item = lines[idx] if idx < len(lines) else {}
            yomigana = item.get("yomigana", "") if isinstance(item, dict) else ""
            translation = item.get("translation", "") if isinstance(item, dict) else ""
            # 독음은 코드로 결정론적 변환 (일본어 잔류 방지)
            korean_reading = reading.to_korean_reading(original, yomigana)
            results.append({
                "original": original,
                "reading": korean_reading,
                "translation": translation,
            })

    return results
