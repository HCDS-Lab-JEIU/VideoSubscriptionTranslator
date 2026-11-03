# Video Subtitle Translator

한국어 강의 영상에서 음성을 받아쓰고 영어로 번역해 **SRT 자막과 자막이 합성된 MP4**를 만드는 Windows 데스크톱 앱입니다. 강의별 용어장을 적용하고, 영상 재생과 텍스트북 편집을 지원합니다.

## Windows 앱 사용

빌드된 ZIP 전체를 압축 해제하고 `VideoSubtitleTranslator.exe`를 실행합니다.

1. `secrets/openai_api_key.txt`에 OpenAI API 키를 한 줄로 저장합니다.
2. **영상 선택 → 텍스트북 불러오기 → 과목 선택 → 파이프라인 실행** 순서로 진행합니다.
3. **결과 폴더 열기**에서 SRT와 MP4를 확인합니다. 기본 저장 위치는 `output_runs/`입니다.

**영상 자막 합성 자막 기준 병렬 처리**를 체크하면 전체 자막 개수를 물리 코어 수에 맞춰 균등한 연속 묶음으로 나누어 동시 처리합니다. 예를 들어 자막 100개와 물리 코어 8개라면 자막 1~13, 14~26, …, 89~100을 각각 맡습니다. 각 영상 구간은 다음 묶음의 첫 자막 시작 시간까지이며, 자막 전후의 영상과 음성도 보존합니다. 동시 작업 수는 자막 수와 물리 코어 수 중 작은 값이며, 시작 시간이 같은 자막 등으로 구간을 나눌 수 없으면 더 적어질 수 있습니다. 물리 코어 수를 확인할 수 없으면 1개로 처리합니다. 기본값은 해제이며, CLI에서는 `--parallel-render`로 켭니다. CPU·메모리와 임시 디스크 사용량이 증가하며 처리 속도는 환경에 따라 달라집니다.

기본 텍스트북은 `secrets/textbook.txt`이며, **Tools → 텍스트북 편집기**에서 강의 용어와 규칙을 수정할 수 있습니다. 전사·번역에는 인터넷 연결과 유료 OpenAI API가 필요합니다. 원본 영상은 보존됩니다.

## 소스에서 실행

### 실행 요구사항

Windows와 **Python 3.10 이상**이 필요합니다. 아래는 [requirements.txt](requirements.txt)에 정의된 직접 의존성입니다. 설치 시 각 패키지가 필요로 하는 하위 의존성도 함께 설치됩니다.

| 패키지 | 버전 범위 | 용도 |
| --- | --- | --- |
| `imageio-ffmpeg` | `>=0.6.0,<0.7` | 시스템 FFmpeg가 없을 때 사용할 실행 파일 제공 |
| `mutagen` | `>=1.47,<2` | MP3 길이·비트레이트 등 오디오 정보 읽기 |
| `openai` | `>=2,<4` | 음성 전사·자막 번역 API 호출 |
| `PyQt6` | `>=6.7,<7` | 데스크톱 UI, 영상 재생과 텍스트북 편집 |

영상·오디오 처리에는 **FFmpeg**가 필요합니다. PATH에 설치된 FFmpeg를 먼저 사용하며, 없으면 `imageio-ffmpeg`가 제공하는 실행 파일을 사용합니다. 자막 합성에는 `subtitles` 필터(libass 지원)가 포함된 FFmpeg가 필요합니다. 전사·번역에는 인터넷 연결과 유료 OpenAI API 키가 필요합니다.

### 환경 생성과 패키지 설치

Miniconda를 설치했다면 Conda를 사용할 수 있는 PowerShell에서 프로젝트 루트로 이동한 뒤 아래 명령을 실행합니다. `translator`는 예시 환경 이름이며, Miniconda 설치 드라이브나 경로가 같을 필요는 없습니다. 이미 Python 3.10 이상의 환경이 있다면 해당 환경의 Python으로 `-m pip install -r requirements.txt`를 실행해도 됩니다.

```powershell
conda create -n translator python=3.11 pip -y
conda run --no-capture-output -n translator python -m pip install -r requirements.txt
```

### API 키와 텍스트북 파일

프로젝트 루트에 아래 두 파일을 UTF-8로 저장합니다.

```text
secrets/
├── openai_api_key.txt   # OpenAI API 키만 한 줄로 입력
└── textbook.txt         # 전사·번역 규칙과 과목별 용어장
```

`textbook.txt`는 다음 형식으로 작성합니다. 과목과 용어를 강의에 맞게 바꾸면 됩니다.

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

전체 예제는 [packaging/textbook.example.txt](packaging/textbook.example.txt)를 참고하세요. 텍스트북은 앱의 **Tools → 텍스트북 편집기**에서도 수정할 수 있습니다.

### 앱 실행

```powershell
conda run --no-capture-output -n translator python -m qtTest.app
```

명령줄에서도 실행할 수 있습니다.

```powershell
conda run --no-capture-output -n translator python __main__.py 'C:\videos\lecture.mp4' --course '회로'
conda run --no-capture-output -n translator python __main__.py --help
```

영상 경로와 과목 이름은 실제 파일과 텍스트북 내용에 맞게 바꿉니다. 다른 환경 이름을 사용한다면 위 명령의 `-n translator`도 해당 이름으로 바꿉니다.

Windows EXE·ZIP 생성에는 실행용 패키지 외에 `pyinstaller==6.22.3`이 필요하며, [packaging/requirements-build.txt](packaging/requirements-build.txt)에 정의되어 있습니다. 빌드 방법은 [packaging/README.md](packaging/README.md), 내부 동작과 상세 옵션은 [개발 문서](docs/development.md)를 참고하세요.
