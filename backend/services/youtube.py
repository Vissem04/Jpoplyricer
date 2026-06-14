"""YouTube URL -> 오디오 파일(mp3) 추출."""
import base64
import os
import subprocess
import uuid
from pathlib import Path

from ..config import TMP_DIR

_COOKIE_FILE: str | None = None


def _cookie_args() -> list[str]:
    """환경변수 YTDLP_COOKIES_B64(쿠키 txt를 base64 인코딩)가 있으면 --cookies 로 사용.

    클라우드 IP가 YouTube에 차단될 때 로그인 쿠키로 우회하기 위한 escape hatch.
    """
    global _COOKIE_FILE
    b64 = os.getenv("YTDLP_COOKIES_B64", "")
    if not b64:
        return []
    if _COOKIE_FILE is None:
        try:
            path = TMP_DIR / "yt_cookies.txt"
            path.write_bytes(base64.b64decode(b64))
            _COOKIE_FILE = str(path)
        except Exception:
            return []
    return ["--cookies", _COOKIE_FILE]


def _base_opts() -> list[str]:
    """yt-dlp 공통 옵션: 데이터센터 환경에서의 SSL EOF/차단 회피용.

    - --force-ipv4: 데이터센터 IPv6 경로의 TLS 끊김(UNEXPECTED_EOF) 회피
    - player_client=android: 실패하기 쉬운 watch 웹페이지 fetch를 건너뜀(InnerTube API)
    - YTDLP_PROXY / YTDLP_COOKIES_B64 환경변수로 프록시·쿠키 우회 지원
    """
    opts = [
        "--force-ipv4",
        "--no-playlist",
        "--no-warnings",
        "--retries", "3",
    ]
    # 클라이언트 우회 옵션은 환경변수로 조정 가능(기본은 yt-dlp 최신 기본값 사용).
    #   예: YTDLP_PLAYER_CLIENT="web_safari,tv"  /  비우면 미지정.
    pc = os.getenv("YTDLP_PLAYER_CLIENT", "")
    if pc:
        opts += ["--extractor-args", f"youtube:player_client={pc}"]
    proxy = os.getenv("YTDLP_PROXY", "")
    if proxy:
        opts += ["--proxy", proxy]
    opts += _cookie_args()
    return opts


def download_audio(url: str) -> Path:
    """주어진 YouTube URL의 오디오를 mp3로 다운로드하고 파일 경로를 반환한다.

    yt-dlp + ffmpeg 를 사용한다. 재생 음질과 Whisper 25MB 제한을 고려해 VBR mp3로 추출한다.
    """
    out_id = uuid.uuid4().hex
    out_template = str(TMP_DIR / f"{out_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        *_base_opts(),
        "-x",                          # 오디오만 추출
        "--audio-format", "mp3",
        "--audio-quality", "5",        # VBR ~130k: 재생 음질 + Whisper 25MB 제한 양립
        "-o", out_template,
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"오디오 다운로드 실패: {result.stderr.strip()[:500]}")

    mp3_path = TMP_DIR / f"{out_id}.mp3"
    if not mp3_path.exists():
        # 확장자가 다르게 떨어진 경우 탐색
        candidates = list(TMP_DIR.glob(f"{out_id}.*"))
        if not candidates:
            raise RuntimeError("오디오 파일을 찾을 수 없습니다.")
        mp3_path = candidates[0]

    return mp3_path


def get_video_title(url: str) -> str:
    """영상 제목을 가져온다(제목 추론 보조용).

    yt-dlp 의 기본 포맷 선택이 실패해도 제목만은 얻도록 메타데이터(--dump-json)를
    사용한다. Windows에서 일본어 깨짐을 막기 위해 UTF-8로 디코드한다.
    """
    cmd = [
        "yt-dlp", *_base_opts(), "--skip-download",
        "--print", "%(title)s", url,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not result.stdout:
        return ""
    return result.stdout.decode("utf-8", errors="replace").strip()


def get_duration(path: Path) -> float:
    """오디오 길이(초). 실패 시 0.0."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except Exception:
        return 0.0
