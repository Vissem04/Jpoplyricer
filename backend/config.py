"""환경변수 로딩 및 공용 설정."""
import os
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트의 .env 로드
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GENIUS_ACCESS_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN", "")

IDENTIFY_MODEL = os.getenv("OPENAI_IDENTIFY_MODEL", "gpt-4o")
ANNOTATE_MODEL = os.getenv("OPENAI_ANNOTATE_MODEL", "gpt-4o-mini")
WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")

# 임시 오디오 파일 저장 위치
TMP_DIR = ROOT_DIR / "tmp"
TMP_DIR.mkdir(exist_ok=True)

# 저장된 노래(라이브러리) 영속 저장 위치
DATA_DIR = ROOT_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
LIBRARY_FILE = DATA_DIR / "library.json"
DATA_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)

# --- 인증/관리자 ---
USERS_FILE = DATA_DIR / "users.json"
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def get_session_secret() -> bytes:
    """세션 쿠키 서명용 비밀키. env에 없으면 data/secret.key 에 생성·보관."""
    env_secret = os.getenv("SESSION_SECRET", "")
    if env_secret:
        return env_secret.encode("utf-8")
    key_file = DATA_DIR / "secret.key"
    if key_file.exists():
        return key_file.read_bytes()
    secret = os.urandom(32)
    key_file.write_bytes(secret)
    return secret


def require_keys() -> None:
    """필수 키가 없으면 명확한 에러를 던진다."""
    missing = []
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-...") or OPENAI_API_KEY == "sk-...":
        missing.append("OPENAI_API_KEY")
    if not GENIUS_ACCESS_TOKEN or GENIUS_ACCESS_TOKEN in ("", "..."):
        missing.append("GENIUS_ACCESS_TOKEN")
    if missing:
        raise RuntimeError(
            f".env 파일에 다음 키를 입력해야 합니다: {', '.join(missing)}"
        )
