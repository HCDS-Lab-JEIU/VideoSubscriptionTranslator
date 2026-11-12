# 소스 코드로 실행하기

Windows에서 소스 코드로 UI 앱이나 CLI를 실행하는 방법입니다. 설치 없이 실행하려면 [README의 Windows 패키지 안내](../README.md)를 사용하세요.

## 1. 프로젝트와 Python 환경 준비

프로젝트 폴더는 `README.md`, `requirements.txt`, `subtitle_app/`이 들어 있는 폴더입니다. 아래 명령의 `D:\VideoSubsribProject`는 실제 프로젝트 위치에 맞추세요.

Miniconda와 Python 3.10 이상이 필요하며, 이 프로젝트는 **`translator` Conda 환경**을 사용합니다. 아래는 Miniconda가 `D:\Miniconda3`에 설치된 경우입니다. 다른 위치에 설치했다면 인터프리터와 Conda 경로를 함께 바꾸세요.

```powershell
cd D:\VideoSubsribProject
# translator 환경이 없을 때만 생성합니다.
& 'D:\Miniconda3\Scripts\conda.exe' create -n translator python=3.11 pip -y
& 'D:\Miniconda3\envs\translator\python.exe' -m pip install -r requirements.txt
```

<details>
<summary>기본 의존성과 FFmpeg</summary>

| 패키지 | 버전 범위 | 용도 |
| --- | --- | --- |
| `imageio-ffmpeg` | `>=0.6.0,<0.7` | FFmpeg 실행 파일 제공 |
| `mutagen` | `>=1.47,<2` | 오디오 길이·비트레이트 읽기 |
| `openai` | `>=2,<4` | 전사·번역 API 호출 |
| `PyQt6` | `>=6.7,<7` | UI와 영상 재생 |

정확한 의존성은 [requirements.txt](../requirements.txt)에 정의합니다. PATH의 FFmpeg를 먼저 찾고, 없으면 `imageio-ffmpeg`가 제공하는 실행 파일을 사용합니다. 시스템 FFmpeg를 사용한다면 자막 합성을 위한 `subtitles` 필터(libass 지원)가 필요합니다.

</details>

## 2. 로컬 전사를 사용할 경우

API 전사만 쓴다면 이 단계는 건너뜁니다. 사용할 장치에 맞춰 아래 명령 중 하나를 실행하세요.

```powershell
# 로컬 CPU 전사
& 'D:\Miniconda3\envs\translator\python.exe' -m pip install -r requirements-local.txt
# NVIDIA GPU 전사: CPU 패키지와 CUDA 실행 라이브러리를 함께 설치
& 'D:\Miniconda3\envs\translator\python.exe' -m pip install -r requirements-local-gpu.txt
```

NVIDIA 드라이버는 별도로 필요합니다. 가중치는 앱에서 첫 로컬 전사를 실행할 때 다운로드합니다. 메모리 사용과 CPU 재시도 방식은 [모델 상세 안내](advanced.md#로컬-whisper)를 참고하세요.

## 3. 텍스트북과 인증 준비

소스에는 개인 텍스트북과 API 키가 포함되지 않습니다. 첫 실행용 텍스트북은 [예제](../packaging/textbook.example.txt)를 복사합니다. 아래 명령은 **기존 텍스트북이 없을 때만** 복사합니다.

```powershell
New-Item -ItemType Directory -Force -Path secrets | Out-Null
if (-not (Test-Path -LiteralPath secrets/textbook.txt)) {
    Copy-Item -LiteralPath packaging/textbook.example.txt -Destination secrets/textbook.txt
}
```

API 방식은 [README의 API 키 안내](../README.md#2-전사번역-방식-준비하기)를, Codex 방식은 [CLI 설치·로그인 안내](../README.md#codex-cli-설치-및-로그인-windows)를 따라 준비합니다. 실제 강의의 규칙과 용어는 UI의 텍스트북 편집기에서 수정할 수 있습니다.

## 4. UI 실행

프로젝트 폴더에서 실행하세요.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' -m subtitle_app.ui.app
```

텍스트북 편집기만 열려면:

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' -m subtitle_app.ui.textbook_editor
```

이후에는 [첫 영상에 자막 만들기](../README.md#3-첫-영상에-자막-만들기)를 따라 진행합니다. `No module named subtitle_app` 오류가 나면 프로젝트 폴더에서 실행했는지 확인하세요. 다른 모듈이 없다는 오류라면 위와 같은 `translator` 인터프리터로 의존성을 설치했는지 확인합니다.

## CLI 사용

CLI는 화면 대신 명령으로 실행합니다. 전체 옵션은 도움말에서 확인할 수 있습니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' -m subtitle_app --help
& 'D:\Miniconda3\envs\translator\python.exe' -m subtitle_app --list-courses
```

<details>
<summary>전사·번역·전체 파이프라인 명령 예제</summary>

영상 경로와 과목명을 실제 파일과 텍스트북에 맞춰 바꿉니다. API/Codex 요청에는 선택한 서비스의 요금 또는 사용 한도가 적용됩니다.

```powershell
# OpenAI API로 전체 작업 실행
& 'D:\Miniconda3\envs\translator\python.exe' -m subtitle_app 'C:\videos\lecture.mp4' --course '회로'

# 로컬 Whisper로 전사만 실행
& 'D:\Miniconda3\envs\translator\python.exe' -m subtitle_app 'C:\videos\lecture.mp3' --transcribe --transcription-backend local --course '회로' --transcript-output-dir output_txts/local

# 로컬 전사 + OpenAI API 번역
& 'D:\Miniconda3\envs\translator\python.exe' -m subtitle_app 'C:\videos\lecture.mp4' --pipeline --transcription-backend local --course '회로'

# 기존 한국어 자막을 Codex로 번역
& 'D:\Miniconda3\envs\translator\python.exe' -m subtitle_app 'C:\subtitles\lecture_kr.txt' --translate --translation-backend codex --course '회로'

# 로컬 전사 + Codex 번역으로 전체 작업
& 'D:\Miniconda3\envs\translator\python.exe' -m subtitle_app 'C:\videos\lecture.mp4' --pipeline --transcription-backend local --translation-backend codex --course '회로'
```

`--local-model medium`은 로컬 모델을, `--local-device cpu`는 CPU 실행을 선택합니다. Codex 모델과 추론 수준은 `--codex-model`, `--codex-reasoning`으로 지정하며 계정에서 지원하는 값을 사용해야 합니다. 생략하면 모델 목록의 기본값을 확인한 뒤 실행합니다.

번역 재개·체크포인트는 [Codex 번역 상세](advanced.md#codex-번역), API 전사 복구와 나머지 옵션은 [개발 문서](development.md)를 참고하세요.

</details>

<details>
<summary>텍스트북 TXT 형식</summary>

UTF-8로 저장하며 규칙과 과목별 단어장을 아래 형식으로 작성합니다. UI의 **Tools → 텍스트북 편집기**로 편집해도 됩니다.

```text
[Common Rules]
Preserve technical terminology and meaning.

[Whisper Rules]
한국어 강의. 들리지 않은 단어나 수치는 추측하지 마세요.

[Translation Rules]
Translate Korean lecture speech into natural English subtitles.
Do not summarize or invent information.

[Course]
회로 (Circuits)

[Terminology]
전압 = voltage
전류 = current
저항 = resistance
```

전체 예제: [textbook.example.txt](../packaging/textbook.example.txt)

</details>

소스 구조와 테스트는 [개발 문서](development.md#소스-구조), EXE 빌드는 [패키징 안내](../packaging/README.md)를 참고하세요. 기존 `__main__.py`, `-m qtTest.app`, `-m qtTest.textbook_editor` 실행 명령도 지원합니다.
