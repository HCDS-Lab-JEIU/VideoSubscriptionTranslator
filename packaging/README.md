# Windows 앱 빌드

Miniconda `translator` 환경에서 프로젝트 루트 기준으로 실행합니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' -m pip install -r packaging/requirements-build.txt
.\packaging\build_windows.ps1
```

출력은 `packaging/dist/VideoSubtitleTranslator/`와 `packaging/VideoSubtitleTranslator-v2026.11.12-windows-x64.zip`입니다.
파일명 버전은 `subtitle_app/common/app_version.py`에서 읽으며 SHA-256은 `packaging/SHA256SUMS.txt`에 기록합니다.
GUI·CLI EXE, Python 런타임, Qt, FFmpeg, faster-whisper, CTranslate2, CUDA DLL,
스타일, 예제 텍스트북, README와 화면별 HTML 사용법을 포함합니다.
Codex CLI·인증, Whisper 모델 가중치, NVIDIA 드라이버와 PowerPoint는 포함하지 않습니다.
모델은 첫 실행 시 다운로드합니다. Codex 설치·로그인은 루트 README를 참고하세요.
빌드 스크립트는 `translator`의 `Library/bin`을 빌드 프로세스의 PATH에 추가해 OpenSSL 등 네이티브 DLL을 수집합니다.
빌드 후 API 호출 없이 필수 DLL 포함 여부, GUI 시작, CLI, 오디오 추출과 순차·병렬 자막 합성을 검사합니다.
배포 시 ZIP 전체를 전달하세요. 실제 API 키와 로컬 텍스트북은 수집하지 않습니다.
앱 빌드 생성물은 Git에서 제외하며, 소스와 빌드 설정을 커밋하고 ZIP·체크섬을 GitHub Release에 첨부합니다.

구성은 [PyInstaller 공식 문서](https://pyinstaller.org/en/stable/spec-files.html)를 따릅니다.
