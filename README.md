# Video Subtitle Translator

한국어 강의 영상에서 음성을 받아쓰고 영어로 번역해 **SRT 자막과 자막이 합성된 MP4**를 만드는 Windows 데스크톱 앱입니다. 강의별 용어장을 적용하고, 영상 재생과 텍스트북 편집을 지원합니다.

## Windows 앱 사용

빌드된 ZIP 전체를 압축 해제하고 `VideoSubtitleTranslator.exe`를 실행합니다.

1. `secrets/openai_api_key.txt`에 OpenAI API 키를 한 줄로 저장합니다.
2. **영상 선택 → 텍스트북 불러오기 → 과목 선택 → 파이프라인 실행** 순서로 진행합니다.
3. **결과 폴더 열기**에서 SRT와 MP4를 확인합니다. 기본 저장 위치는 `output_runs/`입니다.

기본 텍스트북은 `secrets/textbook.txt`이며, **Tools → 텍스트북 편집기**에서 강의 용어와 규칙을 수정할 수 있습니다. 전사·번역에는 인터넷 연결과 유료 OpenAI API가 필요합니다. 원본 영상은 보존됩니다.

## 소스에서 실행

Miniconda의 `translator` 환경을 준비한 뒤 프로젝트 루트에서 실행합니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' -m pip install -r requirements.txt
New-Item -ItemType Directory -Force secrets
Copy-Item packaging/textbook.example.txt secrets/textbook.txt
# secrets/openai_api_key.txt에 API 키 저장
& 'D:\Miniconda3\envs\translator\python.exe' -m qtTest.app
```

명령줄에서도 실행할 수 있습니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py 'D:\videos\lecture.mp4' --course '회로'
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py --help
```

Windows EXE·ZIP 생성 방법은 [packaging/README.md](packaging/README.md), 내부 동작과 상세 옵션은 [개발 문서](docs/development.md)를 참고하세요.
