"""API 키는 로컬 파일에서만 읽고 출력하지 않습니다."""

from pathlib import Path


def load_api_key(file_path: str | Path) -> str:
    path = Path(file_path).expanduser().resolve()
    try:
        api_key = path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        raise ValueError("API 키 파일을 읽을 수 없습니다. 파일 경로와 접근 권한을 확인하세요.") from None
    if "=" in api_key:
        name, value = api_key.split("=", 1)
        if name.strip().lower() in {"key", "api_key", "openai_api_key"}:
            api_key = value.strip()
    if len(api_key) >= 2 and api_key[0] == api_key[-1] and api_key[0] in {"'", '"'}:
        api_key = api_key[1:-1].strip()
    if not api_key or any(character.isspace() for character in api_key):
        raise ValueError("API 키 파일에 키만 한 줄로 입력하세요.")
    return api_key
