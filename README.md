# 🎵 J-POP 가사 독음 · 해석기

일본 노래 유튜브 URL을 넣으면 **가사 + 한국어 독음 + 해석**을 한 번에 보여주는 웹앱.

## 동작 파이프라인

1. **오디오 추출** — yt-dlp + ffmpeg 로 유튜브 영상을 mp3(16kHz)로 변환
2. **음성 → 텍스트** — OpenAI Whisper 로 대략적인 일본어 가사 받아쓰기
3. **곡 추론** — GPT 가 영상 제목 + 받아쓴 가사로 원곡 제목/가수 추론
4. **정식 가사** — Genius API 로 해당 곡의 정확한 가사 크롤링
5. **독음 + 해석** — GPT 가 각 줄마다 한글 독음과 한국어 해석 생성

## 필요 조건

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) (PATH에 등록)
- OpenAI API 키
- Genius API Access Token — https://genius.com/api-clients

## 설치

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 환경변수

`.env.example` 을 참고해 `.env` 파일에 키를 채운다:

```
OPENAI_API_KEY=sk-...
GENIUS_ACCESS_TOKEN=...
```

## 실행

```powershell
uvicorn backend.main:app --reload --port 8000
```

브라우저에서 http://localhost:8000 접속 → 유튜브 URL 붙여넣기 → 변환.

## 참고

- 한 번 처리에 약 30초~1분 소요(다운로드 + Whisper + GPT 호출).
- Whisper 25MB 제한 때문에 64kbps/16kHz로 추출한다(긴 곡도 대부분 안전).
- 곡 추론이 틀리면 Genius 검색이 실패할 수 있다 — 추후 "수동 곡명 입력" 보완 예정.
