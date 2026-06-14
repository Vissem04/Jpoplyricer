"""대략적인 가사 + 영상 제목 -> 곡 검색 후보/검색어 생성 (GPT).

GPT가 곡을 '단정'하면 환각으로 틀리는 경우가 많으므로, 여기서는 곡을 확정하지 않고
Genius에서 찾기 위한 '검색 후보'와 '검색어'를 폭넓게 만든다. 실제 확정은 상위 단계에서
Whisper 받아쓰기와 가사를 대조 검증해 결정한다.
"""
import json

from openai import OpenAI

from ..config import OPENAI_API_KEY, IDENTIFY_MODEL

SYSTEM_PROMPT = """너는 일본 음악 검색 전문가다.
유튜브 영상 제목과 음성인식으로 받아쓴 일본어 가사(부정확할 수 있음)를 받는다.
목표: 이 곡을 가사 사이트(Genius)에서 찾기 위한 검색 후보를 만든다.

규칙:
- 영상 제목이 영어/번역/로마자면 원래 일본어 제목을 추론하라. (예: "Route 66" -> "66号線")
- 유명곡으로 함부로 단정하지 마라. 확신이 없으면 여러 후보를 제시하라.
- 가사에 실제로 등장하는 '특징적인 단어/고유명사/구절'을 검색어에 포함하라
  (이게 곡을 정확히 찾는 핵심 단서다).
- artist를 모르면 "Unknown" 으로 둬도 된다.

반드시 아래 JSON으로만 답하라:
{
  "candidates": [{"title": "추정 제목", "artist": "아티스트 또는 Unknown"}],  // 최대 3개, 가능성 순
  "search_queries": ["Genius 검색어", ...]  // 최대 6개: 제목/원어제목/가사 특징어구 등
}"""


def identify_song(video_title: str, rough_lyrics: str) -> dict:
    """검색 후보와 검색어를 생성해 반환."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    user_msg = (
        f"[유튜브 영상 제목]\n{video_title}\n\n"
        f"[음성인식 대략 가사]\n{rough_lyrics[:1500]}"
    )
    try:
        resp = client.chat.completions.create(
            model=IDENTIFY_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        data = {}

    candidates = []
    for c in data.get("candidates", [])[:3]:
        title = (c.get("title") or "").strip()
        artist = (c.get("artist") or "").strip()
        if title:
            candidates.append({"title": title, "artist": artist})

    queries = [q.strip() for q in data.get("search_queries", []) if isinstance(q, str) and q.strip()]

    # 최상위 후보(표시·폴백용)
    top = candidates[0] if candidates else {"title": video_title, "artist": ""}
    return {
        "title": top["title"],
        "artist": top.get("artist", ""),
        "candidates": candidates,
        "search_queries": queries[:6],
    }
