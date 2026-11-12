# Video Subtitle Translator

현재 배포 버전: **v2026.11.12** · [Windows 패키지 다운로드](https://github.com/HCDS-Lab-JEIU/VideoSubscriptionTranslator/releases/tag/v2026.11.12)

한국어 강의 영상에서 음성을 받아쓰고 영어로 번역해 **SRT 자막과 자막이 합성된 MP4**를 만드는 Windows 데스크톱 앱입니다. 강의별 용어장을 적용하고, 영상 재생과 텍스트북 편집을 지원합니다.

붉은 박스와 화살표로 기능을 설명한 [화면별 사용법 안내](docs/user-guide/index.html)와 [전체 이미지·안내 ZIP](docs/user-guide.zip)을 제공합니다.

## Windows 앱 사용

빌드된 ZIP 전체를 압축 해제하고 `VideoSubtitleTranslator.exe`를 실행합니다.

1. API 전사 또는 API 번역을 사용할 경우 `secrets/openai_api_key.txt`에 OpenAI API 키를 한 줄로 저장합니다.
2. **영상 선택 → 텍스트북 불러오기 → 과목 선택 → 전사·번역 방식 선택 → 파이프라인 실행** 순서로 진행합니다.
3. **결과 폴더 열기**에서 SRT와 MP4를 확인합니다. 기본 저장 위치는 `output_runs/`입니다.

화면 왼쪽 위에는 영상과 재생 컨트롤, 왼쪽 아래에는 진행 상태와 콘솔, 오른쪽에는 설정 인스펙터가 있습니다. 영역 사이 경계선을 드래그해 크기를 조절할 수 있습니다. 설정은 오른쪽에서 스크롤하며, 실행 버튼과 결과 폴더 버튼은 인스펙터 하단에 표시됩니다.

번역 후 **SRT 생성**이 완료되면 위쪽 원본 영상에 미리보기 자막이 자동으로 표시됩니다. MP4 인코딩 중에도 재생·일시정지와 파형을 통한 구간 이동이 가능하며, **미리보기 자막** 체크박스로 표시를 켜고 끕니다. 자막을 불러올 때 현재 재생 위치는 유지합니다. 새 영상 선택 또는 새 파이프라인 실행 시 이전 자막을 지웁니다. 미리보기는 SRT를 화면에 겹쳐 표시하는 방식이므로 최종 MP4의 글꼴·줄바꿈과 외형은 다를 수 있습니다. 최종 MP4에는 기존처럼 자막을 영상에 합성합니다.

**영상 자막 합성 자막 기준 병렬 처리**를 체크하면 전체 자막 개수를 물리 코어 수에 맞춰 균등한 연속 묶음으로 나누어 동시 처리합니다. 예를 들어 자막 100개와 물리 코어 8개라면 자막 1~13, 14~26, …, 89~100을 각각 맡습니다. 각 영상 구간은 다음 묶음의 첫 자막 시작 시간까지이며, 자막 전후의 영상과 음성도 보존합니다. 동시 작업 수는 자막 수와 물리 코어 수 중 작은 값이며, 시작 시간이 같은 자막 등으로 구간을 나눌 수 없으면 더 적어질 수 있습니다. 물리 코어 수를 확인할 수 없으면 1개로 처리합니다. 기본값은 해제이며, CLI에서는 `--parallel-render`로 켭니다. CPU·메모리와 임시 디스크 사용량이 증가하며 처리 속도는 환경에 따라 달라집니다.

기본 텍스트북은 `secrets/textbook.txt`이며, **Tools → 텍스트북 편집기**에서 강의 용어와 규칙을 수정할 수 있습니다. 기본 전사·번역 방식은 기존 **OpenAI API**입니다. **로컬 Whisper**를 선택하면 음성을 서버에 업로드하지 않고 PC에서 전사합니다. 영어 번역은 **OpenAI API / Codex CLI** 중 선택하며 둘 다 인터넷 연결이 필요합니다. **로컬 Whisper + Codex CLI** 조합에는 이 앱의 API 키 파일이 필요 없습니다. 원본 영상은 보존됩니다.

## 소스에서 실행

### PPT에서 단어장 자동 생성 (Auto)

**Tools → 텍스트북 편집기 → Auto**에서 여러 `.pptx` / `.ppt` 파일을 드래그하거나 **Open · PPT 파일 추가**로 선택합니다. 한 번에 선택한 PPT들을 하나의 과목 단어장으로 모읍니다. 기존 과목을 선택하거나 새 과목명을 입력하세요.

생성 방식은 **OpenAI API (gpt-4.1)**와 **Codex CLI** 중 선택합니다. Codex는 로그인 계정에서 사용 가능한 모델과 추론 수준을 콤보박스로 선택하며, API 키 파일이 필요 없습니다. PPT에서 추출한 텍스트와 현재 편집 중인 텍스트북 규칙·선택 과목의 기존 단어를 해당 서비스에 전송합니다. API 요금 또는 Codex 계정의 사용 한도가 적용됩니다.

**단어장 생성 → 후보 검토·수정 → 선택 단어를 편집기에 추가 → Save** 순서로 사용합니다. 결과에는 출처 파일·슬라이드 번호가 표시됩니다. 기존 단어 및 충돌 후보는 기본 선택에서 제외하고 기존 번역을 덮어쓰지 않습니다. 기존 규칙과 다른 과목은 유지하며, 편집기에 추가하기 전까지 문서를 변경하지 않습니다. 저장 형식은 기존 `[Course]` / `[Terminology]`의 `한국어 용어 = English term` 형식입니다.

PPTX는 별도 Office 설치 없이 슬라이드 텍스트와 표를 읽습니다. 구형 PPT는 **Windows에 설치된 PowerPoint**로 읽기 전용 임시 변환합니다. 원본은 수정하지 않습니다. 이미지 속 글자(OCR), 발표자 노트, 이미지 기반 도표는 추출하지 않습니다. 텍스트 없는 슬라이드는 로그에 표시하며, 긴 자료는 여러 요청으로 나누어 처리합니다. 생성 취소는 현재 파일 처리·요청 종료 후 적용되고, 실패·취소 시 결과를 편집기에 자동 반영하지 않습니다.

API는 [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)를 사용하고, 두 방식 모두 결과를 앱의 텍스트북 형식으로 검증합니다. 생성된 용어는 저장 전에 검토하세요.

### 실행 요구사항

Windows와 **Python 3.10 이상**이 필요합니다. 아래는 [requirements.txt](requirements.txt)에 정의된 직접 의존성입니다. 설치 시 각 패키지가 필요로 하는 하위 의존성도 함께 설치됩니다.

| 패키지 | 버전 범위 | 용도 |
| --- | --- | --- |
| `imageio-ffmpeg` | `>=0.6.0,<0.7` | 시스템 FFmpeg가 없을 때 사용할 실행 파일 제공 |
| `mutagen` | `>=1.47,<2` | MP3 길이·비트레이트 등 오디오 정보 읽기 |
| `openai` | `>=2,<4` | 음성 전사·자막 번역 API 호출 |
| `PyQt6` | `>=6.7,<7` | 데스크톱 UI, 영상 재생과 텍스트북 편집 |

영상·오디오 처리에는 **FFmpeg**가 필요합니다. PATH에 설치된 FFmpeg를 먼저 사용하며, 없으면 `imageio-ffmpeg`가 제공하는 실행 파일을 사용합니다. 자막 합성에는 `subtitles` 필터(libass 지원)가 포함된 FFmpeg가 필요합니다. OpenAI API 방식의 전사 또는 번역을 선택한 경우 API 키가 필요합니다.

### 로컬 Whisper (RTX 2070 SUPER 8GB)

`whisper-1`은 OpenAI API의 모델 이름이며 공개 Whisper V2를 기반으로 합니다([OpenAI 문서](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create)). 이 앱의 로컬 기본값은 **faster-whisper / large-v2 / INT8**입니다. API 서비스와 로컬 실행은 디코딩·전처리가 달라 결과가 완전히 같지는 않습니다.

GPU에서는 `int8_float16`, CPU에서는 `int8`로 실행합니다. 배치 처리 없이 30초 창을 순차 처리하고, 모델 작업자 1개와 beam size 1을 사용합니다. [faster-whisper 공식 벤치마크](https://github.com/SYSTRAN/faster-whisper#benchmark)의 large-v2 INT8는 RTX 3070 Ti에서 VRAM 2,926MB였습니다. **3–4GB는 목표치이며 하드 제한이나 OOM 방지 보장은 아닙니다.** GPU 0의 여유 VRAM이 4GiB 미만이거나 조회할 수 없으면 CPU를 사용합니다. 로딩 또는 전사 도중 CUDA/OOM 오류가 발생해도 GPU를 해제하고 CPU에서 한 번 재시도합니다. CPU 재시도는 처음부터 진행하며 API로 전환하지 않습니다. 다른 앱의 GPU 사용량은 실행 도중에도 바뀔 수 있습니다.

이 PC의 RTX 2070 SUPER 8GB에서 한국어 강의 60초를 오프라인으로 전사한 초기 확인 결과는 약 10.6초, GPU 전체 사용량 증가분 최대 2,337MiB였습니다(faster-whisper 1.2.1, CTranslate2 4.9.0). `nvidia-smi`를 0.5초마다 조회한 값으로 다른 앱의 영향과 샘플 사이의 순간 피크는 포함하지 못하므로 전용 메모리 측정이나 장시간 최대치 보장은 아닙니다. 처리 종료 후 GPU 메모리 해제도 확인했습니다.

현재 프로젝트의 `translator` 환경에 선택 의존성을 설치합니다. 기존 API 방식만 쓴다면 추가 설치는 필요 없습니다.

```powershell
# 로컬 CPU 전사
& 'D:\Miniconda3\envs\translator\python.exe' -m pip install -r requirements-local.txt
# NVIDIA GPU 전사: 위 패키지 + 공식 CUDA 12 cuBLAS / cuDNN 9 런타임
& 'D:\Miniconda3\envs\translator\python.exe' -m pip install -r requirements-local-gpu.txt
```

Windows NVIDIA pip 패키지의 DLL 경로는 앱이 자동 등록합니다. 시스템 CUDA를 사용한다면 CUDA 12 cuBLAS와 cuDNN 9가 PATH에서 검색되어야 합니다. NVIDIA 드라이버는 별도 설치가 필요합니다. GPU 실행에 PyTorch는 사용하지 않습니다.

UI에서 **전사 방식 → 로컬 Whisper**를 선택한 뒤 `large-v2`, `medium`, `small`과 실행 장치를 선택합니다. `medium`/`small`은 메모리를 더 절약하지만 한국어·전문 용어 정확도는 별도 비교가 필요합니다. 첫 실행에는 공개 가중치를 Hugging Face에서 `models/whisper/`로 다운로드하므로 인터넷과 디스크 공간이 필요합니다(large-v2 다운로드 약 3GB). 이후 캐시를 재사용합니다. 전사 시 텍스트북의 과목·용어 힌트를 적용하고 VAD로 무음을 제외하며 TXT와 타임스탬프 JSON을 저장합니다. JSON에는 사용 모델·장치·완료 여부와 중간 결과가 기록됩니다. 기존 API 구간 복구는 API 방식에서 유지되며 로컬 JSON에는 적용되지 않습니다.

```powershell
# API 키 없이 한국어 전사만 실행
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py 'C:\videos\lecture.mp3' --transcribe --transcription-backend local --course '회로' --transcript-output-dir output_txts/local
# 로컬 전사 → 기존 API 영어 번역 → 자막 영상
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py 'C:\videos\lecture.mp4' --pipeline --transcription-backend local --course '회로'
```

`--local-model medium`으로 모델을 변경하거나 `--local-device cpu`로 CPU만 사용할 수 있습니다. `--transcription-response`는 기존 API 방식에서만 지원합니다. **v2026.11.12 Windows 패키지에는 로컬 전사 라이브러리와 CUDA DLL이 포함**됩니다. 모델 가중치는 첫 실행 시 다운로드하며, NVIDIA 드라이버는 별도로 설치되어 있어야 합니다. 이전 EXE는 새 ZIP 전체로 교체하세요.

### Codex로 영어 자막 번역

UI의 **번역 방식 → Codex CLI (로그인 계정 사용)**를 선택하면 **Codex 모델 / 추론 수준** 콤보박스에 실제 목록을 불러옵니다. 공식 [app-server의 `model/list`](https://learn.chatgpt.com/docs/app-server#models) 응답을 사용하며, 선택한 모델에서 지원하는 추론 수준만 표시합니다. **목록 새로고침**으로 갱신할 수 있습니다. 목록 조회는 백그라운드에서 진행하며, 최초 조회에 실패하면 번역 실행을 막고 재시도 안내를 표시합니다. 새로고침에서는 여전히 지원되는 기존 선택을 유지합니다.

이전 UI의 `default`는 모델 ID를 전달하지 않아 CLI 자체 기본값에 맡긴다는 뜻이었으며, VS Code에서 고른 모델과 연동되지 않았습니다. 이제 모델 ID와 추론 수준을 항상 명시적으로 전달하고 화면의 **실행 설정**과 로그에 기록합니다. 최초 조회 시 Codex가 기본으로 표시한 모델과 해당 모델의 기본 추론 수준을 선택합니다. 이 PC에서 확인한 값은 `gpt-6.1-sol` / `low`이며 계정·CLI 업데이트에 따라 달라질 수 있습니다. `low`는 가벼운 추론, `medium`은 균형, `high` 이상은 더 깊은 추론을 뜻합니다. 높은 수준은 응답 시간과 사용량이 늘어날 수 있습니다.

이 PC에서는 설치된 Codex CLI의 ChatGPT 로그인을 확인했고 예문 두 줄의 실제 번역을 검증했습니다. 별도 API 키 파일은 사용하지 않으며, 로그인 계정의 사용 한도·과금 조건을 따릅니다. 무제한 무료 번역이나 오프라인 번역은 아닙니다. Codex에 자막 텍스트, 주변 문맥, 선택한 과목의 번역 규칙과 용어장을 전송합니다.

이 기능은 공식 [`codex exec` 비대화형 실행](https://learn.chatgpt.com/docs/non-interactive-mode)을 사용합니다. 예전 `codex mcp-server`는 [현재 CLI에서 제거](https://learn.chatgpt.com/docs/developer-commands)되어 MCP 서버를 별도로 띄우지 않습니다. 최신 Codex CLI를 설치하고 같은 Windows 계정에서 `codex login`으로 로그인하세요. PATH의 실행 파일 또는 VS Code Codex 확장에 포함된 실행 파일을 자동 검색합니다. 필요하면 CLI의 `--codex-executable`로 경로를 지정할 수 있습니다. `--ignore-user-config`와 `--ephemeral`을 지원하는 버전이 필요합니다(확인한 버전: 0.162.0-alpha.17.2).

#### Codex CLI 설치 및 로그인 (Windows)

Codex CLI는 이 앱의 ZIP에 포함하지 않으므로 **Codex 번역 또는 Auto 생성 기능을 사용하는 PC마다 설치·로그인**합니다. Windows 앱과 같은 Windows 사용자 계정의 PowerShell에서 아래 순서로 실행하세요. WSL 안에만 설치하면 Windows EXE에서 자동 검색하지 못합니다.

1. Node.js LTS와 npm이 없다면 설치합니다. 설치 후 PowerShell을 새로 엽니다. 이미 설치했다면 `node --version`, `npm.cmd --version`으로 확인하고 다음 단계로 진행합니다.

   ```powershell
   winget install --id OpenJS.NodeJS.LTS -e
   ```

2. Codex CLI를 설치하거나 최신 버전으로 업데이트합니다. `.cmd`를 명시하면 PowerShell의 `.ps1` 실행 정책에 영향을 받지 않습니다.

   ```powershell
   npm.cmd install -g @openai/codex@latest
   codex.cmd --version
   codex.cmd login
   codex.cmd login status
   ```

3. 브라우저에서 사용할 ChatGPT 계정으로 로그인합니다. `login status`에서 로그인 상태를 확인한 뒤 이 앱을 다시 실행합니다. **Codex CLI → 목록 새로고침 → 모델·추론 수준 선택** 순서로 설정하면 됩니다. 텍스트북 편집기의 Auto 창에서도 같은 로그인을 사용합니다.

4. 앱에서 CLI를 찾지 못하면 `Get-Command codex.cmd`로 설치 경로를 확인하고 앱과 터미널을 완전히 종료한 뒤 다시 엽니다. 필요한 옵션을 지원하지 않는다는 오류가 나면 위 npm 설치 명령으로 업데이트하고 `codex.cmd exec --help`에서 `--ignore-user-config`, `--ephemeral` 지원 여부를 확인하세요. VS Code Codex 확장에 포함된 CLI도 자동 검색합니다.

Node.js/npm은 위 설치 방법을 위한 도구이며, 이 앱 자체는 패키지에 포함된 Python으로 실행합니다. Codex 계정 인증은 사용자의 PC에 보관되며 배포 ZIP이나 Git에 포함하지 않습니다. 공식 안내: [Windows 설치](https://learn.chatgpt.com/docs/enterprise/windows-deployment#deploy-codex-cli-on-windows), [로그인](https://learn.chatgpt.com/docs/auth).

```powershell
# 기존 한국어 자막만 Codex로 번역
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py 'C:\subtitles\lecture_kr.txt' --translate --translation-backend codex --course '회로'
# 모델과 추론 수준을 직접 지정 (계정에서 지원하는 조합 사용)
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py 'C:\subtitles\lecture_kr.txt' --translate --translation-backend codex --codex-model gpt-6.1-sol --codex-reasoning low --course '회로'
# API 키 파일 없이 전체 실행: 로컬 전사 + Codex 번역
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py 'C:\videos\lecture.mp4' --pipeline --transcription-backend local --translation-backend codex --course '회로'
```

번역은 50구간씩 요청하고 원본 타임스탬프를 그대로 보존합니다. 빈 번역은 해당 구간만 재요청하며, 정상 번역은 `.translation.json`에 저장합니다. 중단되면 생성된 한국어 TXT에 `--translate --translation-backend codex`를 같은 출력 경로로 다시 실행해 이어갈 수 있습니다. 전체 파이프라인 재실행은 기존 동작대로 새 결과 폴더를 만듭니다. API 방식과 Codex 방식의 체크포인트는 서로 섞어 사용하지 않습니다. Codex 오류나 사용 한도 도달 시 OpenAI API로 자동 전환하지 않습니다.

각 번역 요청은 임시 작업 폴더에서 읽기 전용 샌드박스·셸 실행 비활성화·웹 검색 비활성화로 실행합니다. 번역 실행은 사용자 `config.toml`을 읽지 않으며 CLI에 저장된 인증을 재사용합니다. 모델 목록 조회는 설치된 app-server의 설정과 계정을 사용합니다. CLI에서 `--codex-model` 또는 `--codex-reasoning`을 생략하면 모델 목록에서 해당 기본값을 확인한 뒤 명시적으로 전달합니다. 모델·추론 수준이 달라지면 기존 체크포인트를 섞어 사용하지 않으므로 새 출력 경로를 지정해야 합니다. 원문은 명령줄 인수가 아닌 표준 입력으로 전달하며, 앱 로그에는 원문이 포함될 수 있는 CLI 진단 출력을 노출하지 않습니다.

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
