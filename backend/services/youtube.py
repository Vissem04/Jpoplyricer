"""YouTube URL -> 오디오 파일(mp3) 추출."""
import subprocess
import uuid
from pathlib import Path

from ..config import TMP_DIR


def download_audio(url: str) -> Path:
    """주어진 YouTube URL의 오디오를 mp3로 다운로드하고 파일 경로를 반환한다.

    yt-dlp + ffmpeg 를 사용한다. Whisper의 25MB 제한을 고려해 64kbps mp3로 추출한다.
    """
    out_id = uuid.uuid4().hex
    out_template = str(TMP_DIR / f"{out_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "-x",                          # 오디오만 추출
        "--audio-format", "mp3",
        "--audio-quality", "5",        # VBR ~130k: 재생 음질 + Whisper 25MB 제한 양립
        "-o", out_template,
        "--no-playlist",
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
        "yt-dlp", "--skip-download", "--no-warnings", "--no-playlist",
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
