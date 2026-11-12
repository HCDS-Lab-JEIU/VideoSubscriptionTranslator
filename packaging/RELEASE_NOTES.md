# v2026.11.12

기존 OpenAI API 전사·번역을 유지하면서 로컬 Whisper, Codex CLI 번역과 PPT 기반 단어장 자동 생성을 추가했습니다.

## 주요 변경

- 전사 방식 선택: OpenAI API / 로컬 Whisper. `large-v2`, `medium`, `small` INT8 실행과 모델 자동 다운로드, GPU 메모리 부족·CUDA 오류 시 CPU 재시도를 지원합니다.
- 번역 방식 선택: OpenAI API / Codex CLI. 로그인 계정에서 사용 가능한 모델과 추론 수준을 콤보박스로 선택합니다.
- 텍스트북 편집기 Auto: PPT/PPTX 복수 입력, API 또는 Codex 생성, 출처 슬라이드 확인, 후보 수정·선택 후 편집기에 추가합니다. 기존 단어를 덮어쓰지 않습니다.
- SRT 생성 직후 소프트 자막 미리보기: 인코딩 중에도 원본 영상을 재생·탐색하며 자막을 켜고 끌 수 있습니다.
- 레이아웃 변경: 왼쪽 영상·진행 콘솔, 오른쪽 설정 인스펙터. 경계선을 드래그해 크기를 조절합니다.
- Codex CLI 설치·로그인 안내와 붉은 박스·화살표가 포함된 화면별 사용법을 제공합니다.

## Windows 패키지

`VideoSubtitleTranslator-v2026.11.12-windows-x64.zip` 전체를 쓰기 가능한 폴더에 압축 해제하고 `VideoSubtitleTranslator.exe`를 실행하세요. Python, Qt, FFmpeg, 로컬 Whisper 실행 라이브러리와 CUDA DLL이 포함됩니다. `SHA256SUMS.txt`로 다운로드 파일의 SHA-256을 확인할 수 있습니다.

- Whisper 모델 가중치는 포함하지 않으며 첫 로컬 전사 실행 때 다운로드합니다.
- NVIDIA GPU 드라이버는 별도 설치가 필요합니다. GPU 사용이 불가능하면 CPU로 재시도합니다.
- Codex CLI는 별도로 설치·로그인합니다. README의 Windows 설치 절차를 참고하세요.
- API 방식에는 API 키·요금, Codex 방식에는 로그인 계정의 사용 한도가 적용됩니다.
- 구형 `.ppt` 입력에는 Windows PowerPoint가 필요합니다. PPTX는 Office 없이 읽으며 이미지 OCR·발표자 노트는 제외합니다.
- 최종 MP4는 자막이 합성된 영상입니다. 소프트 자막은 앱 내 미리보기에서 사용합니다.

이전 버전의 `secrets` 폴더와 작업 결과는 따로 보관하고 새 ZIP을 별도 폴더에 풀어 사용하세요. 사용법은 패키지의 `docs/user-guide/index.html`에서 확인할 수 있습니다.

## 검증

- translator 환경 전체 테스트 165개 통과.
- 합성 PPTX·구형 PPT를 이용한 실제 Codex 단어장 생성, 검토와 텍스트북 저장 확인.
- 실제 영상 재생·탐색과 FFmpeg 인코딩 중 자막 미리보기 확인.
- Windows 패키지의 독립 런타임, GUI·CLI, 로컬 CPU/VAD/CUDA DLL, PPT Auto UI, 자막 미리보기, FFmpeg 순차·병렬 렌더링 스모크 테스트.
