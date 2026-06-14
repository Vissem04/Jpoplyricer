---
title: Jpoplyricer
emoji: 🎵
colorFrom: pink
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# 🎵 J-POP 가사 독음 · 해석기

일본 노래 유튜브 URL을 넣으면 **가사 + 한국어 독음 + 해석**을 한 번에 보여주고,
**노래방(가사 싱크)** 와 **TJ 노래방 곡번호**까지 제공하는 웹앱.

## 동작 파이프라인

1. **오디오 추출** — yt-dlp + ffmpeg
2. **음성 → 텍스트** — OpenAI Whisper(받아쓰기)
3. **곡 추론** — GPT가 영상 제목 + 받아쓴 가사로 원곡 추론
4. **정식 가사(교차검증)** — Genius + Uta-Net 두 출처를 대조해 더 정확한 가사 채택
5. **독음 + 해석** — GPT가 줄별 한글 독음/해석 생성(조사·문맥 한자 보정)
6. **노래방 싱크** — LRCLIB 동기가사 / 로컬 강제정렬(stable-ts, 선택) / 근사 정렬
7. **TJ 노래방 곡번호** 조회

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# (선택) 고정밀 보컬 싱크: pip install -r requirements-align.txt
```

`.env.example` 을 복사해 `.env` 에 키를 채운다:

```
OPENAI_API_KEY=sk-...
GENIUS_ACCESS_TOKEN=...
ADMIN_USERNAME=본인아이디
ADMIN_PASSWORD=강한-비밀번호
```

실행:

```powershell
uvicorn backend.main:app --reload --port 8000   # 로컬
./run.ps1                                        # 같은 네트워크의 폰 등 외부 접속
```

브라우저에서 http://localhost:8000 접속.

## 배포 (Hugging Face Spaces, 무료)

이 저장소는 **Docker Space** 로 바로 배포된다(루트의 `Dockerfile`, 위 front matter).

1. https://huggingface.co/new-space → SDK: **Docker**, 이 GitHub 저장소 연결(또는 푸시)
2. Space **Settings → Variables and secrets** 에 등록:
   - `OPENAI_API_KEY`, `GENIUS_ACCESS_TOKEN` (Secret)
   - `ADMIN_USERNAME`, `ADMIN_PASSWORD` (Secret, 강한 값)
   - `SESSION_SECRET` (Secret, 임의 32바이트 hex 권장)
   - `COOKIE_SECURE=1` (HTTPS이므로)
3. 데이터 영속이 필요하면 **Persistent Storage** 추가 후 `DATA_DIR=/data` 설정
   (무료/임시 스토리지는 재시작 시 가입자·저장곡이 초기화됨)

> ⚠️ `.env` 와 `data/` 는 절대 커밋/업로드 금지(.gitignore/.dockerignore 로 차단됨). 키는 호스트 Secret 으로만.

## 보안

- 비밀번호 pbkdf2-sha256 해시, 세션 쿠키 hmac 서명(HttpOnly, HTTPS 시 Secure)
- 회원가입 후 **관리자 승인**이 있어야 콘텐츠 이용 가능
- 약한/기본 `ADMIN_PASSWORD` 로는 관리자 자동 생성을 거부
