"""배포 리소스와 구분되는 사용자 파일의 기본 위치."""

from pathlib import Path
import sys


def app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]
