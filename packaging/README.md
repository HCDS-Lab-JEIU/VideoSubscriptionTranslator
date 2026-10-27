# Windows 앱 빌드

Miniconda `translator` 환경에서 프로젝트 루트 기준으로 실행합니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' -m pip install -r packaging/requirements-build.txt
.\packaging\build_windows.ps1
```

출력은 `dist/VideoSubtitleTranslator/`와 `VideoSubtitleTranslator-windows-x64.zip`입니다.
GUI·CLI EXE, Python 런타임, Qt, FFmpeg, 스타일과 예제 텍스트북을 포함합니다.
빌드 후 API 호출 없이 GUI 시작, CLI, 오디오 추출과 순차·병렬 자막 합성을 검사합니다.
배포 시 ZIP 전체를 전달하세요. 실제 API 키와 로컬 텍스트북은 수집하지 않습니다.
생성물은 Git에서 제외하며, 소스와 빌드 설정만 커밋합니다.

구성은 [PyInstaller 공식 문서](https://pyinstaller.org/en/stable/spec-files.html)를 따릅니다.
