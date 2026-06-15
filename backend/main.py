"""FastAPI 진입점: YouTube URL -> 가사/독음/해석 + 노래방 싱크 파이프라인."""
import re
from concurrent.futures import ThreadPoolExecutor

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import COOKIE_SECURE, ROOT_DIR, TMP_DIR, require_keys
from .services import (
    align,
    annotate,
    auth,
    auto_offset,
    forced_align,
    genius,
    identify,
    library,
    lrclib,
    tjkaraoke,
    transcribe,
    utanet,
    word_align,
    youtube,
)

# 교차검증 임계값
VOCAL_MATCH_MIN = 0.25   # 받아쓰기-가사 일치가 이 이상이면 보컬 근거가 있다고 판단
AGREE_MIN = 0.5          # 두 출처 가사 유사도가 이 미만이면 '불일치'로 표시


def _as_result(d: dict, source: str) -> dict:
    return {
        "title": d.get("title", ""),
        "artist": d.get("artist", ""),
        "url": d.get("url", ""),
        "lyrics": d.get("lyrics", ""),
        "source": source,
        "score": d.get("score"),
    }


def _select_lyrics(g: dict, u: dict, transcription: str):
    """Genius(보컬 대조)와 Uta-Net(일본 네이티브)을 교차검증해 더 정확한 가사를 고른다.

    반환: (lyrics_result | None, verified: bool, cross: dict)
    """
    gf, uf = bool(g.get("found")), bool(u.get("found"))
    if not gf and not uf:
        return None, False, {}
    if gf and not uf:
        return _as_result(g, "Genius"), True, {"sources": ["Genius"], "agreement": None, "conflict": False}
    if uf and not gf:
        # Genius 검증 실패(보컬 없음/MR 등 받아쓰기 대조 불가) -> 일본 네이티브 채택
        return _as_result(u, "Uta-Net"), False, {"sources": ["Uta-Net"], "agreement": None, "conflict": False}

    # 둘 다 있음 -> 교차검증
    cross = genius.text_similarity(g["lyrics"], u["lyrics"])
    g_tr = g.get("score") or 0.0                                   # Genius vs 받아쓰기
    u_tr = genius.text_similarity(transcription, u["lyrics"])      # Uta-Net vs 받아쓰기
    has_vocals = max(g_tr, u_tr) >= VOCAL_MATCH_MIN

    if has_vocals:
        # 실제 음성에 더 잘 맞는 출처 채택(틀린 가사가 올라온 출처를 거름)
        chosen = _as_result(u, "Uta-Net") if u_tr >= g_tr else _as_result(g, "Genius")
        verified = True
    else:
        # 음성 근거 없음 -> 일본 네이티브 우선
        chosen = _as_result(u, "Uta-Net")
        verified = False

    cross_info = {
        "sources": ["Genius", "Uta-Net"],
        "agreement": round(cross, 3),
        "conflict": cross < AGREE_MIN,
    }
    return chosen, verified, cross_info


def _lrc_norm(s: str) -> str:
    return re.sub(r"[^぀-ヿ一-鿿0-9a-z]", "", (s or "").lower())


def _map_lrc_times(annotated: list[dict], lrc: list[tuple]) -> list[float] | None:
    """LRC 타임스탬프를 우리 가사 줄(annotated)에 순차 텍스트 매칭으로 부여한다.

    줄 분할이 약간 달라도 동작하도록 정규화 텍스트로 앞에서부터 매칭하고,
    매칭 안 된 줄은 이웃 타임으로 선형 보간한다. 매칭률이 낮으면 None.
    """
    rn = [(t, _lrc_norm(txt)) for t, txt in lrc]
    n = len(annotated)
    times: list[float | None] = [None] * n
    j = 0
    valid_lines = 0
    for i, ln in enumerate(annotated):
        a = _lrc_norm(ln.get("original", ""))
        if not a:
            continue
        valid_lines += 1
        found, k = -1, j
        while k < len(rn) and k <= j + 8:
            b = rn[k][1]
            if b and (a == b or a in b or b in a):
                found = k
                break
            k += 1
        if found >= 0:
            times[i] = rn[found][0]
            j = found + 1

    matched = sum(1 for t in times if t is not None)
    if matched < max(3, 0.6 * max(1, valid_lines)):
        return None  # 매칭이 부실하면 LRC 타이밍을 신뢰하지 않음

    # 빈 곳 선형 보간
    known = [(i, t) for i, t in enumerate(times) if t is not None]
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
    return res


def _ensure_increasing(starts: list) -> list[float]:
    """반복 가사 등으로 시작시간이 같거나 역행하면, 다음 더 큰 값(또는 끝)까지 균등
    분배해 각 줄이 '구별되는, 증가하는' 시작시간을 갖게 한다(노래방 하이라이트 멈춤 방지).
    """
    n = len(starts)
    s = [float(x) if isinstance(x, (int, float)) else None for x in starts]
    for i in range(n):
        if s[i] is None:
            s[i] = 0.0 if i == 0 else s[i - 1]
    i = 1
    while i < n:
        if s[i] > s[i - 1]:
            i += 1
            continue
        j = i
        while j < n and s[j] <= s[i - 1]:
            j += 1
        lo = s[i - 1]
        hi = s[j] if j < n else lo + (j - (i - 1)) * 1.2
        span = (hi - lo) if hi > lo else (j - (i - 1)) * 0.5
        step = span / (j - (i - 1))
        for k in range(i, j):
            s[k] = round(lo + step * (k - (i - 1)), 2)
        i = j + 1 if j < n else j
    return s


app = FastAPI(title="J-POP 가사 독음/해석 + 노래방")

FRONTEND_DIR = ROOT_DIR / "frontend"


@app.on_event("startup")
def _startup():
    auth.seed_admin()


@app.middleware("http")
async def no_cache_assets(request: Request, call_next):
    """정적 자산(JS/CSS/HTML)을 항상 최신으로 받도록 캐시 비활성화."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class ProcessRequest(BaseModel):
    url: str


class AuthBody(BaseModel):
    username: str
    password: str


class LinesBody(BaseModel):
    lines: list[dict]


# ---------- 인증 ----------
@app.post("/api/auth/register")
def register(body: AuthBody):
    username = (body.username or "").strip()
    if len(username) < 2 or len(body.password) < 4:
        raise HTTPException(status_code=400, detail="아이디 2자 이상, 비밀번호 4자 이상이어야 합니다.")
    if auth.get_user(username):
        raise HTTPException(status_code=409, detail="이미 존재하는 아이디입니다.")
    auth.create_user(username, body.password)
    return {"ok": True, "status": "pending"}


@app.post("/api/auth/login")
def login(body: AuthBody, response: Response):
    user = auth.authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    token = auth.create_session_token(user["username"])
    response.set_cookie(
        auth.COOKIE_NAME, token, httponly=True, samesite="lax",
        secure=COOKIE_SECURE, max_age=auth.SESSION_TTL, path="/",
    )
    return auth.public_user(user)


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    u = auth.get_current_user(request)
    return auth.public_user(u) if u else None


# ---------- 관리자 ----------
@app.get("/api/admin/users")
def admin_list_users(admin=Depends(auth.require_admin)):
    return auth.list_users()


@app.post("/api/admin/users/{username}/approve")
def admin_approve(username: str, admin=Depends(auth.require_admin)):
    if not auth.set_status(username, "approved"):
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {"ok": True}


@app.post("/api/admin/users/{username}/reject")
def admin_reject(username: str, admin=Depends(auth.require_admin)):
    if not auth.set_status(username, "rejected"):
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {"ok": True}


@app.post("/api/admin/users/{username}/role")
def admin_set_role(username: str, value: str, admin=Depends(auth.require_admin)):
    ok, msg = auth.set_role(username, value)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True}


@app.delete("/api/admin/users/{username}")
def admin_delete(username: str, admin=Depends(auth.require_admin)):
    if not auth.delete_user(username):
        raise HTTPException(status_code=404, detail="삭제할 수 없습니다(존재하지 않거나 관리자).")
    return {"ok": True}


@app.post("/api/process")
def process(req: ProcessRequest, user=Depends(auth.require_approved)):
    try:
        require_keys()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL을 입력하세요.")

    try:
        # 1) 오디오 추출 + 영상 제목 (오디오는 노래방 재생을 위해 보존)
        #    audio_id 는 유튜브 영상 ID 기반(같은 곡 재처리 시 갱신)
        audio_id = library.extract_video_id(url)
        video_title = youtube.get_video_title(url)
        audio_path = youtube.download_audio(url)

        # 2) 음성 -> 대략 가사 + 구간 타임스탬프
        trans = transcribe.transcribe_audio(audio_path)

        # 3) 곡 검색 후보/검색어 생성
        song_info = identify.identify_song(video_title, trans["text"])

        # 4) 가사 수집 + 교차검증
        #    Genius(받아쓰기 대조) + Uta-Net(일본 네이티브)을 병렬로 가져와 대조한다.
        #    '맞는 곡인데 가사 내용이 틀린' 경우를 줄이고, 보컬이 없는 MR도 네이티브 출처로 처리.
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_g = ex.submit(
                genius.fetch_verified_lyrics,
                song_info["search_queries"], trans["text"], song_info["candidates"],
            )
            f_u = ex.submit(utanet.fetch_lyrics, song_info["candidates"])
            g_res = f_g.result()
            u_res = f_u.result()
            if not g_res.get("found"):
                # Genius 검증 실패 시 제목 기반 폴백도 한 번 시도(보조)
                g_res = genius.fetch_lyrics_by_title(song_info["candidates"])

        lyrics_result, verified, cross_check = _select_lyrics(g_res, u_res, trans["text"])
        if lyrics_result is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "가사를 찾지 못했습니다. 곡을 특정할 수 없어요. "
                    f"(추정: {song_info['title']})"
                ),
            )
        # 신뢰도: 받아쓰기 일치도(있으면) 또는 출처 간 일치도
        song_info["confidence"] = (
            lyrics_result.get("score")
            or cross_check.get("agreement")
            or 0.0
        )

        # 5) 가사 텍스트 결정
        #   LRCLIB 동기가사가 곡과 일치하면 그 '줄'을 가사로 사용(군더더기 없는 깨끗한 텍스트).
        #   아니면 교차검증(Genius/Uta-Net) 텍스트.
        dur = youtube.get_duration(audio_path)
        lrc = None
        try:
            cand_lrc = lrclib.fetch_synced(
                lyrics_result["title"], lyrics_result["artist"], dur, tolerance=30
            )
        except Exception:
            cand_lrc = None
        if cand_lrc and genius.text_similarity(
            "\n".join(t for _, t in cand_lrc), lyrics_result["lyrics"]
        ) >= 0.5:
            lrc = cand_lrc

        lyrics_text = "\n".join(t for _, t in lrc) if lrc else lyrics_result["lyrics"]
        annotated = annotate.annotate_lyrics(lyrics_text)
        originals = [ln["original"] for ln in annotated]

        # 6) 노래방 싱크 — 우선순위
        #   1순위: word-align — 그 오디오의 Whisper '단어 타임'에 정식 가사를 정렬(오디오
        #          그라운드). 버전/편곡/인트로 길이와 무관하게 실제 박자에 맞아 가장 정확.
        #   2순위: LRC 동기가사 타임(보컬 없는 MR 등 word-align 실패 시).
        #   3순위: 로컬 강제정렬(torch 있을 때) / Whisper 구간 근사.
        #   최후: 균등 분배.
        starts = word_align.align_lines(originals, trans.get("words") or [])
        sync_method = "word"
        if starts is None and lrc:
            starts = _map_lrc_times(annotated, lrc)
            sync_method = "lrc"
        if starts is None:
            forced = forced_align.align_lines(audio_path, originals)
            if forced is not None:
                starts, sync_method = forced, "forced"
            elif verified:
                starts = align.align_lines(originals, trans["segments"])
                sync_method = "approx"
            else:
                n = max(1, len(originals))
                starts = [round(dur * i / n, 2) for i in range(n)] if dur else [0.0] * n
                sync_method = "even"

        # 반복 가사 등으로 같은/역행 타임이 생기면 증가하도록 보정(하이라이트 멈춤 방지)
        starts = _ensure_increasing(starts)
        for ln, start in zip(annotated, starts):
            ln["start"] = start

        # 7) 전역 자동 오프셋 추정(onset 상관). 실패 시 None.
        suggested_offset = auto_offset.estimate_offset(audio_path, starts)

        # 8) TJ 노래방 곡번호 조회(없으면 None -> '-')
        try:
            tj_number = tjkaraoke.find_number(lyrics_result["title"], lyrics_result["artist"])
        except Exception:
            tj_number = None

        result = {
            "id": audio_id,
            "video_title": video_title,
            "url": url,
            "identified": song_info,
            "source": {
                "name": lyrics_result.get("source") or "Genius",
                "title": lyrics_result["title"],
                "artist": lyrics_result["artist"],
                "url": lyrics_result["url"],
            },
            "cross_check": cross_check,
            "tj_number": tj_number,
            "audio_url": f"/api/audio/{audio_id}",
            "verified": verified,
            "sync_method": sync_method,
            "suggested_offset": suggested_offset,
            "lines": annotated,
        }

        # 9) 라이브러리에 저장(오디오 영속 보관 + 인덱스)
        try:
            library.save_song(audio_id, result, audio_path, user["username"])
        except Exception:
            pass

        return result
    except HTTPException:
        raise
    except Exception as e:
        # 내부 예외 상세(스택/경로 등)는 서버 로그로만 남기고, 사용자에겐 일반 메시지.
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")


@app.get("/api/audio/{audio_id}")
def get_audio(audio_id: str, user=Depends(auth.require_approved)):
    # 경로 조작 방지
    if not library.is_valid_id(audio_id):
        raise HTTPException(status_code=400, detail="잘못된 오디오 ID")
    # 라이브러리(영속) 우선, 없으면 tmp
    path = library.audio_path(audio_id)
    if not path.exists():
        path = TMP_DIR / f"{audio_id}.mp3"
    if not path.exists():
        raise HTTPException(status_code=404, detail="오디오를 찾을 수 없습니다.")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/library")
def get_library(user=Depends(auth.require_approved)):
    return library.list_songs(user["username"])


@app.delete("/api/library")
def clear_library(user=Depends(auth.require_approved)):
    return {"cleared": library.clear_all(user["username"])}


@app.get("/api/library/{song_id}")
def get_library_song(song_id: str, user=Depends(auth.require_approved)):
    if not library.is_valid_id(song_id):
        raise HTTPException(status_code=400, detail="잘못된 ID")
    rec = library.get_song(song_id, user["username"])
    if rec is None:
        raise HTTPException(status_code=404, detail="저장된 노래를 찾을 수 없습니다.")
    return rec


@app.put("/api/library/{song_id}/lines")
def update_song_lines(song_id: str, body: LinesBody, user=Depends(auth.require_approved)):
    if not library.is_valid_id(song_id):
        raise HTTPException(status_code=400, detail="잘못된 ID")
    if not library.update_lines(song_id, user["username"], body.lines):
        raise HTTPException(status_code=404, detail="저장된 노래를 찾을 수 없습니다.")
    return {"ok": True}


@app.delete("/api/library/{song_id}")
def delete_library_song(song_id: str, user=Depends(auth.require_approved)):
    if not library.is_valid_id(song_id):
        raise HTTPException(status_code=400, detail="잘못된 ID")
    if not library.delete_song(song_id, user["username"]):
        raise HTTPException(status_code=404, detail="저장된 노래를 찾을 수 없습니다.")
    return {"deleted": song_id}


# --- 프론트엔드 정적 서빙 ---
@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
