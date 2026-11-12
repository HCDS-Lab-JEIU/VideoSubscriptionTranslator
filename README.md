# Video Subtitle Translator

한국어 영상의 음성을 받아쓰고 영어로 번역해 **SRT 자막 파일과 자막이 들어간 MP4 영상**을 만드는 Windows 앱입니다.

**[Windows 앱 다운로드 · v2026.11.12](https://github.com/HCDS-Lab-JEIU/VideoSubscriptionTranslator/releases/tag/v2026.11.12)** · **[그림으로 보는 사용법](docs/user-guide/README.md)**

## 1. 다운로드하고 실행하기

1. 다운로드 페이지의 **Assets**에서 `VideoSubtitleTranslator-v2026.11.12-windows-x64.zip`을 받습니다. `Source code`는 실행용 앱이 아닙니다.
2. ZIP **전체를 압축 해제**합니다. 예를 들어 `D:\VideoSubtitleTranslator`처럼 파일을 저장할 수 있는 폴더를 사용하세요.
3. 압축을 푼 폴더에서 `VideoSubtitleTranslator.exe`를 실행합니다. `_internal` 등 함께 들어 있는 폴더도 필요하므로 EXE만 따로 옮기지 마세요.
4. 아래에서 사용할 전사·번역 방식을 준비한 뒤 첫 영상을 선택합니다.

Windows 64비트용 패키지에는 Python과 FFmpeg가 포함되어 있어 별도로 설치할 필요가 없습니다. 이전 버전에서 옮겨 온다면 새 폴더에 풀고 기존 텍스트북과 결과 파일을 보관하세요.

<details>
<summary>소스 코드로 UI 앱을 실행하려면</summary>

프로젝트와 `translator` 환경이 이미 준비된 이 PC에서는 PowerShell에 다음을 입력합니다.

```powershell
cd D:\VideoSubsribProject
& 'D:\Miniconda3\envs\translator\python.exe' -m subtitle_app.ui.app
```

처음 소스로 실행한다면 [환경 준비부터 설명한 소스 실행 안내](docs/source-setup.md)를 따라 하세요. 프로젝트와 Miniconda의 위치가 다르면 경로를 맞춰야 합니다.

</details>

## 2. 전사·번역 방식 준비하기

**전사**는 한국어 음성을 글로 옮기는 단계이고, **번역**은 그 글을 영어로 옮기는 단계입니다. 오른쪽 설정창에서 각각 선택합니다.

| 사용할 방식 | 전사 방식 | 번역 방식 | 준비할 것 |
| --- | --- | --- | --- |
| OpenAI API로 처리 | OpenAI API | OpenAI API | API 키 파일 |
| 음성은 내 PC에서 처리 | 로컬 Whisper | OpenAI API | 첫 모델 다운로드 + API 키 파일 |
| Codex 로그인 계정으로 번역 | 로컬 Whisper | Codex CLI | 첫 모델 다운로드 + Codex 설치·로그인 |

API 사용에는 API 요금이, Codex 사용에는 로그인 계정의 사용 한도가 적용됩니다. 로컬 전사는 음성을 업로드하지 않으며, 번역할 텍스트와 용어장은 선택한 번역 서비스에 전송합니다. 번역에는 인터넷 연결이 필요합니다.

<details>
<summary>OpenAI API 키 설정하기</summary>

1. [OpenAI API 키 페이지](https://platform.openai.com/api-keys)에서 API 키를 준비합니다. API 사용을 위한 결제·사용 가능 상태도 확인하세요.
2. 메모장을 열어 **키만 한 줄로** 붙여 넣습니다.
3. 앱 폴더의 `secrets` 폴더에 `openai_api_key.txt`라는 이름으로 저장합니다. 메모장의 파일 형식은 **모든 파일**, 인코딩은 **UTF-8**로 선택하면 `.txt`가 중복으로 붙는 것을 피할 수 있습니다.
4. 앱 오른쪽 **키 파일 선택**에서 저장한 파일을 선택합니다. 다른 위치에 저장한 TXT도 선택할 수 있습니다.

**로컬 Whisper + Codex CLI**만 사용한다면 이 키 파일은 필요 없습니다. Auto 단어장 생성에서 OpenAI API를 선택할 때도 같은 키 파일을 사용합니다.

</details>

### Codex CLI 설치 및 로그인 (Windows)

Codex를 선택한 경우에만 아래 설치 안내를 펼쳐 진행하세요. Codex CLI는 앱 ZIP에 포함되어 있지 않습니다.

<details>
<summary>Codex 설치 → 로그인 → 앱에서 모델 선택하기</summary>

앱을 실행하는 **같은 Windows 사용자 계정**의 PowerShell에서 진행합니다.

1. Node.js와 npm이 없다면 아래 명령으로 설치합니다. 설치가 끝나면 **PowerShell을 닫고 새로 엽니다**. 이미 있다면 `node --version`, `npm.cmd --version`으로 확인하고 2번으로 넘어갑니다.

   ```powershell
   winget install --id OpenJS.NodeJS.LTS -e
   ```

2. Codex를 설치하고 로그인합니다. `login` 실행 후 열리는 브라우저에서 사용할 ChatGPT 계정으로 로그인하세요.

   ```powershell
   npm.cmd install -g @openai/codex@latest
   codex.cmd --version
   codex.cmd login
   codex.cmd login status
   ```

3. 로그인 상태를 확인한 뒤 이 앱을 다시 실행합니다.
4. **번역 방식 → Codex CLI → 목록 새로고침**을 누릅니다. 나타나는 **모델과 추론 수준**을 확인합니다. 처음에는 자동 선택된 값을 사용할 수 있습니다.

VS Code에서 선택한 모델과는 별도로 설정합니다. 추론 수준은 모델이 답변을 만들 때 추론하는 정도이며, 높은 수준은 처리 시간과 사용량이 늘어날 수 있습니다. 텍스트북 Auto 창에서도 같은 로그인을 사용합니다.

WSL 안에만 설치하면 Windows 앱에서 찾지 못합니다. 설치 명령이 인식되지 않거나 모델 목록이 비어 있으면 아래 **문제 해결**을 확인하세요. 공식 안내: [Windows 설치](https://learn.chatgpt.com/docs/enterprise/windows-deployment#deploy-codex-cli-on-windows), [로그인](https://learn.chatgpt.com/docs/auth).

</details>

<details>
<summary>로컬 Whisper 모델 설정과 첫 다운로드</summary>

- **전사 방식 → 로컬 Whisper**를 선택합니다. 처음에는 모델 `large-v2`, 실행 장치 **GPU 우선 / 부족·오류 시 CPU**를 사용할 수 있습니다.
- 첫 전사 실행 때 모델을 자동 다운로드합니다. 인터넷 연결과 모델 저장 공간이 필요하며, `large-v2` 다운로드는 약 3GB입니다. 이후에는 저장된 모델을 재사용합니다.
- NVIDIA GPU를 사용하려면 드라이버가 설치되어 있어야 합니다. GPU를 사용할 수 없거나 메모리가 부족하면 CPU로 재시도하며, 이 경우 느려질 수 있습니다.
- 메모리를 더 절약하려면 `medium` 또는 `small`을 선택할 수 있습니다. 모델에 따라 전사 정확도가 달라집니다.
- 모델은 앱 폴더의 `models/whisper/`에 저장됩니다. 다운로드 도중에는 진행 콘솔을 확인하세요.

</details>

## 3. 첫 영상에 자막 만들기

1. 오른쪽 **영상 선택**을 눌러 한국어 영상 파일을 엽니다. 처음에는 짧은 영상으로 확인하세요.
2. **텍스트북 불러오기**에서 앱 폴더의 `secrets/textbook.txt`를 선택합니다. 텍스트북은 강의별 용어와 번역 규칙을 담은 파일입니다. 패키지에 포함된 예제로 동작을 확인할 수 있습니다.
3. **과목**을 선택합니다. 실제 강의에 사용할 때는 **Tools → 텍스트북 편집기**에서 해당 과목과 용어를 작성하고 **Save**한 뒤 다시 불러오세요.
4. **전사 방식·번역 방식**을 선택합니다. API를 선택했다면 키 파일을, Codex를 선택했다면 모델과 추론 수준을 확인합니다.
5. **저장 위치 선택**에서 결과 폴더를 지정합니다. 처음에는 기본 위치를 사용하고, 병렬 처리 옵션은 해제된 상태로 두어도 됩니다.
6. 오른쪽 아래 **파이프라인 실행**을 누릅니다. 왼쪽 아래 콘솔에서 진행 상태를 확인하고, 완료되면 **결과 폴더 열기**를 누릅니다.

설정이 한 화면에 보이지 않으면 오른쪽 설정창을 스크롤하세요. 화면별 버튼 위치는 **[그림으로 보는 사용법](docs/user-guide/README.md)**에서 확인할 수 있습니다.

## 4. 결과 확인하기

기본 저장 위치는 앱 폴더의 `output_runs/`이며, 실행할 때마다 새 하위 폴더를 만듭니다. **결과 폴더 열기**로 해당 실행의 파일을 확인하세요.

| 결과물 | 용도 |
| --- | --- |
| `.mp4` | 영어 자막이 영상에 합성된 완성본. 자막을 끌 수 없습니다. |
| `.srt` | 별도로 보관하거나 자막을 지원하는 플레이어에서 사용할 자막 파일 |
| 한국어·영어 `.txt` | 전사와 번역 내용을 검토할 때 사용 |

원본 영상은 보존됩니다. 생성된 자막은 전문 용어와 숫자를 중심으로 확인하세요.

<details>
<summary>인코딩 중 자막 미리보기와 화면 조절</summary>

SRT 생성이 끝나면 위쪽 원본 영상에 자막이 자동으로 표시됩니다. MP4 인코딩 중에도 재생·탐색할 수 있으며 **미리보기 자막**으로 표시를 켜고 끕니다. 미리보기와 최종 MP4는 글꼴이나 줄바꿈이 다를 수 있습니다.

파형을 클릭하거나 드래그하면 재생 위치를 옮길 수 있습니다. 영상·콘솔·설정창 사이의 경계선을 드래그하면 영역 크기가 바뀝니다.

**영상 자막 합성 자막 기준 병렬 처리**를 켜면 여러 구간을 동시에 인코딩합니다. CPU·메모리·임시 디스크 사용량이 늘며 속도는 PC 환경에 따라 달라집니다.

</details>

<details>
<summary>PPT에서 단어장 자동 만들기 (Auto)</summary>

1. **Tools → 텍스트북 편집기 → Auto**를 엽니다.
2. 여러 PPT/PPTX를 드래그하거나 **Open · PPT 파일 추가**로 선택합니다.
3. 기존 과목을 선택하거나 새 과목명을 입력하고, **OpenAI API / Codex CLI** 중 생성 방식을 선택합니다.
4. **단어장 생성** 후 후보와 출처를 확인합니다. 필요한 단어만 체크하고 한글명·영어명을 수정합니다.
5. **선택 단어를 편집기에 추가 → Save**로 저장한 뒤 메인 화면에서 텍스트북을 다시 불러옵니다.

PPTX는 Office 없이 읽을 수 있습니다. 구형 PPT에는 설치된 PowerPoint가 필요하며, 이미지 속 글자와 발표자 노트는 읽지 않습니다. 생성할 때 슬라이드 텍스트와 텍스트북 규칙·기존 단어를 선택한 서비스로 전송합니다.

[Auto 화면 설명 보기](docs/user-guide/README.md#auto-ppt-단어장-생성)

</details>

## 문제가 생겼을 때

<details>
<summary>실행 버튼, API 키, Codex, 모델 다운로드 문제 해결</summary>

| 증상 | 확인할 것 |
| --- | --- |
| EXE가 실행되지 않거나 파일이 없다고 나옴 | ZIP 전체를 압축 해제했는지, `_internal` 폴더가 EXE 옆에 있는지 확인합니다. |
| 파이프라인 실행 버튼이 비활성화됨 | 영상·텍스트북·과목 선택과 API 키 파일을 확인합니다. Codex라면 모델 목록 로딩 완료 여부도 확인합니다. |
| 텍스트북이 없거나 과목이 나타나지 않음 | 패키지의 `secrets/textbook.txt`를 선택합니다. 직접 만들었다면 편집기에서 과목·단어를 입력하고 Save한 파일을 다시 불러옵니다. |
| API 인증 또는 사용량 오류 | 키 파일에 키만 한 줄로 들어 있는지, 해당 API 계정의 결제·사용 한도가 유효한지 확인합니다. |
| `winget`을 찾을 수 없음 | [Node.js 공식 사이트](https://nodejs.org/)에서 LTS 설치 파일로 설치한 뒤 새 PowerShell에서 Codex 설치를 진행합니다. |
| `npm.cmd` 또는 `codex.cmd`를 찾을 수 없음 | PowerShell과 앱을 완전히 닫고 다시 엽니다. 같은 Windows 계정에 설치했는지 확인하고 `Get-Command codex.cmd`로 경로를 확인합니다. |
| Codex 모델 목록을 불러오지 못함 | `codex.cmd login status`로 로그인을 확인하고 앱의 **목록 새로고침**을 누릅니다. |
| Codex에서 지원하지 않는 옵션 오류 | `npm.cmd install -g @openai/codex@latest`로 업데이트합니다. 이 앱에는 `--ignore-user-config`, `--ephemeral`을 지원하는 CLI가 필요합니다. `codex.cmd exec --help`로 확인하세요. |
| 첫 로컬 전사가 오래 걸림 | 콘솔에서 모델 다운로드 중인지 확인하고 인터넷 연결·저장 공간을 확인합니다. CPU로 실행 중이면 전사 속도가 느릴 수 있습니다. |
| GPU 메모리 부족·CUDA 오류 | 다른 GPU 사용 프로그램을 종료하거나 로컬 모델을 `medium`/`small`로 바꾸거나 **CPU 전용**을 선택합니다. |
| 도중에 실패함 | 콘솔의 마지막 오류와 결과 폴더를 확인합니다. 완료된 중간 파일은 남지만, **파이프라인 실행**을 다시 누르면 새 작업을 시작합니다. |

오류를 공유할 때는 콘솔의 오류 문구와 선택한 전사·번역 방식을 알려 주세요.

</details>

## 더 자세한 안내

- [그림으로 보는 화면별 사용법](docs/user-guide/README.md) · [오프라인 설명서 ZIP](docs/user-guide.zip?raw=true) — ZIP을 풀고 `index.html`을 브라우저로 여세요.
- [소스 코드로 실행하기와 CLI 명령](docs/source-setup.md)
- [모델·메모리·복구 등 상세 동작](docs/advanced.md)
- [개발 문서와 소스 구조](docs/development.md) · [Windows 패키지 빌드](packaging/README.md)
