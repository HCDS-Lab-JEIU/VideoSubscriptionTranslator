# 영상 자막 전체 파이프라인

영상 경로 하나만 입력하면 **MP3 추출 → 한국어 전사 → 영어 번역 → SRT → 영어 자막 MP4**를 순서대로 생성합니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py "D:\videos\example.mp4"
```

먼저 `secrets/openai_api_key.txt`와 `secrets/textbook.txt`를 준비하세요 (아래 설정 참고).
전사와 번역은 유료 OpenAI API를 호출합니다. `--pipeline`을 붙여도 같은 동작입니다.
콘솔에 1~5단계 진행 상황과 최종 MP4 경로를 표시합니다.

결과는 `output_runs/example-고유문자열/`에 모입니다.

- `audio/example.mp3`: 추출 음성
- `transcripts/example.txt`, `example.json`: 한국어 전사와 원본 응답
- `transcripts/example_en.txt`, `example_en.translation.json`: 영어 번역과 진행 기록
- `example_en.srt`, `example_en.mp4`: 최종 자막과 자막 합성 영상

입력 이름이 `_kr` 또는 `_ko`로 끝나면 영어 결과에서는 `_en`으로 바꿉니다.
`--pipeline-output-dir "D:\results"`로 결과 상위 폴더를 지정할 수 있습니다.
실행마다 새 폴더를 만들므로 기존 결과와 원본 영상을 보존합니다.
실패하면 해당 단계에서 중단하고 완료된 중간 파일을 남깁니다.
전체 명령을 다시 실행하면 처음부터 처리하며 API 비용이 다시 발생합니다.
중간 결과부터 진행하려면 아래 단계별 명령을 사용하세요. 번역은 같은 출력 경로로 실행하면 저장된 진행 기록을 사용합니다.
추출한 MP3가 25MB 이상이면 전사 전에 중단하며 자동 분할은 지원하지 않습니다.

## 비디오 오디오 추출만 실행

이 프로젝트는 Miniconda의 `translator` 환경을 사용합니다.
인터프리터는 `D:\Miniconda3\envs\translator\python.exe`이며, 프로젝트 내부 가상환경은 만들지 않습니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' -m pip install -r requirements.txt
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py "D:\videos\example.mp4" --extract
```

프로젝트의 `output_audios/example.mp3`에 첫 번째 오디오 트랙을 저장합니다.
음성 전송용 기본 설정은 MP3, 모노, 16kHz, 32kbps입니다. 예상 용량은 1시간당 약 14.4MB입니다.
손실 압축과 모노 변환으로 음질과 채널 정보가 줄어듭니다.
상대 입력 경로는 명령을 실행한 폴더를 기준으로 해석합니다.
동일한 출력 파일이 있으면 오류를 반환하므로 기존 결과를 이동하거나 이름을 변경한 후 실행하세요.
오디오가 없는 영상이나 손상된 파일도 오류를 반환합니다.

시스템 FFmpeg가 있으면 사용하고, 없으면 `imageio-ffmpeg`가 제공하는 실행 파일을 사용합니다.

기존 WAV도 원본을 보존하면서 MP3로 변환할 수 있습니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py "output_audios\직렬저항회로 1.wav" --extract
```

[OpenAI 공식 문서](https://developers.openai.com/api/docs/guides/speech-to-text)에 따르면
음성 전사 입력은 MP3를 지원하며 파일당 최대 25MB입니다. 출력이 25MB 이상이면 안내를 표시합니다.
자동 분할은 현재 구현하지 않았습니다.

## 한국어 전사

`secrets/openai_api_key.txt`에 API 키만 한 줄로 입력한 뒤 실행합니다.
`key = "키"`, `api_key = "키"` 또는 `OPENAI_API_KEY=키` 형식도 지원합니다.
키는 로그나 결과 파일에 기록하지 않습니다. `--transcribe`를 지정하면 유료 OpenAI API 요청을 수행합니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py "output_audios\serial_circuits_01_kr.mp3" --transcribe
```

MP3는 재압축 없이 전달합니다. 비디오나 WAV를 지정하면 MP3 추출 후 전사합니다.
`--api-key-file "경로"`로 키 파일을 지정할 수도 있습니다.

- 모델: `whisper-1`
- 언어: `ko` (한국어; 파일명에 쓰는 `kr`과 다름)
- 응답: `verbose_json`
- 타임스탬프: `timestamp_granularities=["segment"]`

[OpenAI Docs](https://developers.openai.com/api/reference/python/resources/audio/subresources/transcriptions/methods/create)에
따라 구간 단위 시작·종료 시간을 받습니다. 이 설정은 단어별 자막이 아닌 음성 구간별 자막에 사용합니다.
시간은 모델의 추정치이며 정밀 동기화가 필요한 경우 검수가 필요합니다.

결과는 `output_txts/serial_circuits_01_kr.txt`에 UTF-8로 저장합니다. 아래는 형식 예시입니다.

```text
[00:00:01.200, 00:00:04.560] 한국어로 인식된 텍스트
```

원본 응답은 같은 이름의 `.json`에 보관합니다. 기존 TXT 또는 JSON이 있으면 요청 전에 중단합니다.
TXT 저장에 실패해도 JSON이 있으면 해당 응답을 재가공할 수 있습니다.
25MB 이상 파일은 요청 전에 거부합니다. API 연결 실패 시 자동으로 재요청하지 않습니다.

## 영어 자막 번역

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py "output_txts\serial_circuits_01_kr.txt" --translate
```

`gpt-4.1`에 한국어 자막을 보내고 `serial_circuits_01_en.txt`에 영어 자막을 저장합니다.
`secrets/openai_api_key.txt`에서 키를 읽고, `secrets/textbook.txt`의 강의명·한영 용어·번역 지시문을 적용합니다.
이 작업은 유료 API 요청입니다. 테스트 실행과는 별개의 실제 번역 작업입니다.

원본 `[시작시간, 종료시간]`은 프로그램이 그대로 복사합니다. 번역 응답의 구간 번호·개수와 빈 텍스트를 확인한 뒤 저장합니다.
요청할 구간 번호를 JSON 응답 스키마의 필수 속성으로 지정하고 추가 번호는 금지합니다.
응답 속성의 순서와 관계없이 원본 번호 순서로 영어 자막을 결합합니다.
50구간씩 요청하며 앞뒤 3구간을 문맥으로 제공합니다. 응답 대기 중에는 5초마다 콘솔 메시지가 표시됩니다.
각 묶음의 결과를 `*_en.translation.json`에 저장하므로 중단 후 같은 명령으로 완료한 묶음 다음부터 이어갈 수 있습니다.
빈 번역이 있으면 해당 구간만 앞뒤 문맥과 함께 최대 2회 개별 재요청합니다 (추가 API 요청).
정상 번역은 `pending`에 즉시 보관하여 재실행 시 재사용합니다.
계속 실패하면 구간 번호·시간·한국어 원문을 표시하고 중단합니다. 빈 자막을 완성 파일로 저장하지 않습니다.
원본·단어장·번역 설정이 달라지면 기존 진행 파일을 재사용하지 않습니다.

기존 영어 TXT는 덮어쓰지 않습니다. 새 결과가 필요하면 `--translation-output "output_txts\새이름_en.txt"`를 지정하세요.
`--transcribe`와 `--translate`는 한 번에 하나만 사용합니다. 번역 단계에서 한국어 원본은 수정하지 않습니다.

## 파일 구성

### SRT 및 자막 MP4 생성

두 작업은 로컬에서 처리하며 OpenAI API 키나 토큰이 필요하지 않습니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py "output_txts\serial_circuits_01_en.txt" --make-srt
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py "D:\videos\serial_circuits_01_kr.mp4" --render --subtitle-file "output_txts\serial_circuits_01_en.txt"
```

- SRT: `output_subtitles/serial_circuits_01_en.srt`
- MP4: `output_videos/serial_circuits_01_en.mp4`

`--render`는 SRT도 함께 생성합니다. 내용이 같은 기존 SRT는 재사용합니다.
자막은 영상 화면에 합성되므로 항상 표시됩니다. 원본 영상은 보존합니다.
출력은 H.264 영상과 AAC 음성으로 다시 인코딩하며 첫 번째 영상·오디오 트랙을 사용합니다.
영상 처리 위치를 콘솔에 표시합니다. 자막 시각은 원본 영상과 같은 시간 기준이어야 합니다.
SRT는 UTF-8로 저장하고 시간·번호·본문 형식으로 변환합니다.
`--srt-output`과 `--video-output`으로 다른 출력 경로를 지정할 수 있습니다.
이미 존재하는 다른 내용의 SRT나 MP4는 덮어쓰지 않습니다.
FFmpeg의 `subtitles` 필터(libass 지원)가 필요합니다.
[FFmpeg 문서](https://ffmpeg.org/ffmpeg-filters.html#subtitles-1)

### 텍스트북 규칙과 과목별 단어장

`secrets/textbook.txt`를 UTF-8로 편집하면 다음 전사 요청부터 반영됩니다.
`secrets/`는 Git 추적에서 제외되어 있으므로 새 환경에는 단어장도 직접 준비해야 합니다.

```text
[Common Rules]
Do not summarize or omit technical meaning.
Preserve technical terminology.

[Whisper Rules]
한국어 대학 강의. 전문용어의 정확한 표기.

[Translation Rules]
Translate Korean lecture speech into natural English subtitles.
Output only the English translation. Do not add explanations.

[Course]
반도체 회로 (Semiconductor Circuits)

[Terminology]
전압 = voltage
전류 = current
직렬저항회로 = series resistor circuit

[Course]
프로그래밍 (Programming)

[Terminology]
조건문 = conditional statement
반복문 = loop
```

규칙 섹션은 파일 전체에 적용하며 각 섹션을 한 번만 작성합니다. 섹션 이름의 대소문자는 구분하지 않습니다.

- `[Common Rules]`: 전사와 번역에 모두 적용하는 규칙.
- `[Whisper Rules]`: 한국어 전사에만 추가하는 힌트.
- `[Translation Rules]`: 영어 번역에만 추가하는 지시문. 번역 실행 시 필수입니다.
- `[Course]`와 `[Terminology]`: 과목별로 반복하는 묶음. 각 과목명과 한 개 이상의 `한국어 용어 = English term`이 필수입니다.

`[Terminology]`는 바로 앞 과목에 속합니다. 과목명이 중복되거나 같은 과목 안에 중복 용어가 있으면 오류를 표시합니다.
서로 다른 과목에는 같은 한국어 용어를 다른 영어 뜻으로 등록할 수 있으며, 프롬프트에서도 과목별로 구분됩니다.
`#`으로 시작하는 행과 빈 행은 무시합니다. 공통 규칙과 Whisper 규칙은 생략할 수 있습니다.
기존 단일 과목 형식과 `[Translation instructions]`도 계속 지원합니다 (새 `[Translation Rules]`와 함께 중복 사용하지 마세요).

전사 프롬프트에는 공통 규칙, Whisper 규칙, 과목별 강의명과 한국어 용어를 넣습니다.
번역 프롬프트에는 공통 규칙, Translation 규칙, 과목별 강의명과 한영 용어를 넣습니다.
현재는 지정한 파일의 모든 과목을 포함합니다. 실행에 필요한 과목만 파일에 넣으세요.
다른 텍스트북 파일은 `--textbook-file "경로"`로 지정합니다.

추후 작업: 저장된 텍스트북 라이브러리에서 사용할 텍스트북을 선택하는 기능.

Whisper는 일반 텍스트 모델처럼 지시문을 따르지 않고 prompt 한도는 224토큰입니다.
단어장은 이번 강의의 핵심 용어 위주로 짧게 유지하세요. 코드에서 토큰 수를 계산하거나 자동으로 자르지는 않습니다.
용어 힌트는 정확도를 보장하지 않으므로 실제 음성과 대조하여 검수하세요.
[OpenAI Docs](https://developers.openai.com/api/docs/guides/speech-to-text/#prompting)

기존 결과를 보존하면서 단어장을 적용해 다시 전사하려면 새 출력 폴더를 지정합니다 (유료 API 재호출).

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' __main__.py "output_audios\serial_circuits_01_kr.mp3" --transcribe --transcript-output-dir "output_txts\with_textbook"
```

### Qt 단어장 편집기

메인 앱에서 `Tools → 텍스트북 편집기` 또는 `Ctrl+Shift+T`로 편집창을 엽니다.
이미 열린 편집창은 재사용합니다. 영상 재생창을 유지하면서 별도 창에서 편집하며,
메인 앱을 닫을 때에도 미저장 내용을 확인합니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' -m qtTest.app
# 파일 경로 직접 실행도 지원합니다.
& 'D:\Miniconda3\envs\translator\python.exe' qtTest/app.py
```

편집기만 독립 실행할 수도 있습니다. 앱의 `Open` 버튼 또는 `Ctrl+O`로 텍스트북 파일을 선택합니다.

```powershell
& 'D:\Miniconda3\envs\translator\python.exe' -m qtTest.textbook_editor
# 선택 사항: 시작할 때 특정 파일 열기
& 'D:\Miniconda3\envs\translator\python.exe' -m qtTest.textbook_editor --textbook-file "secrets\my_textbook.txt"
```

`qtTest/textbook_editor/app.py` 직접 실행과 기존 `qtTest/textbook_app.py` 실행 경로도 지원합니다.

화면은 위에서부터 **공통 룰 → Whisper 룰 → Translation 룰 → 단어장** 순서입니다.
각 룰은 여러 줄의 텍스트 블록에서 직접 확인·수정합니다. 영역 사이 경계를 드래그해 높이를 조절할 수 있고,
긴 내용은 각 영역 안에서 스크롤합니다. 룰 본문에 파일 섹션 표기(`[Course]` 등)나 `#`으로 시작하는 주석 행은 넣지 마세요.

단어장 목록에서 과목을 선택하고 `+`로 과목을 추가합니다. 테이블의 **한글명 / 영어명** 셀을 더블클릭하여 수정합니다.
`단어 추가`와 `선택 단어 삭제`로 행을 관리하고, `Save` 또는 `Ctrl+S`로 규칙과 전체 과목을 함께 저장합니다.
파일을 열지 않고 새 내용을 작성했다면 첫 저장 시 저장 위치를 선택합니다. 현재 파일 경로는 상단에 표시됩니다.
행이 많아져도 창 크기는 유지하며 테이블 안에서 스크롤합니다. 열 너비도 조절할 수 있습니다.
과목 전환 시 미저장 편집 내용을 유지하며, 다른 파일을 열거나 창을 닫을 때 저장 여부를 확인합니다.
파일 선택 취소나 잘못된 파일 열기는 현재 편집 내용을 유지합니다.
빈 셀이나 같은 과목의 중복 한글명은 저장할 수 없습니다. 새 과목에도 단어를 한 개 이상 입력하세요.
저장 시 파일을 표준 섹션 형식으로 다시 쓰므로 주석과 원래 공백 배치는 유지하지 않습니다.

책임 분리:

- `qtTest/textbook_editor/data.py`: Qt와 독립적인 편집 데이터, 검증, 파일 읽기/원자적 저장.
- `qtTest/textbook_editor/model.py`: 과목별 데이터를 연결하는 Qt 테이블 모델.
- `qtTest/textbook_editor/editor.py`: 재사용 가능한 편집 위젯과 창.
- `qtTest/textbook_editor/app.py`, `__main__.py`: 독립 실행 진입점.
- `qtTest/MyApp.py`: 편집창 열기·재사용·메인 앱 종료 연결.

추후에는 현재 별도 편집창을 오른쪽 `QDockWidget`에도 배치하는 방안을 검토합니다.
과목 선택 및 편집 상태는 플레이어와 분리하여 관리합니다.
저장된 텍스트북 라이브러리 선택과 영상별 과목 연결은 추후 작업입니다.

### 모듈

- `__main__.py`: 경로 인자 처리와 작업 실행
- `pipeline.py`: 영상 입력부터 영어 자막 MP4까지 전체 단계 연결
- `audio_extractor.py`: `AudioExtractor`의 오디오 추출 및 저장
- `media_file.py`: 공통 `MediaFile`과 `VideoFile`, `AudioFile`, `SubscriptFile`
- `subtitle.py`: 기존 자막 모델 `TimeStamp`, `SubscriptLine`
- `api_config.py`: 키 파일 읽기
- `audio_transcriber.py`: Whisper API 요청 및 구간 모델 생성
- `transcript_writer.py`: `[시작시간, 종료시간] 텍스트` 저장
- `textbook.py`: 공통·단계별 규칙과 여러 과목 파싱, 전사·번역 prompt 구성
- `transcript_reader.py`: 타임스탬프가 포함된 한국어 TXT 읽기
- `subtitle_translator.py`: 영어 번역 요청, 구간 대응 확인, 진행 상태 보관
- `console_status.py`: API 응답 대기 메시지
- `srt_writer.py`: 타임스탬프 TXT를 SRT로 변환
- `video_subtitler.py`: 자막 합성 및 MP4 인코딩
- `ffmpeg_tools.py`: 공통 FFmpeg 실행 파일 탐색

작업 옵션을 생략하면 전체 파이프라인을 수행합니다. 오디오 추출만 필요하면 `--extract`를 지정하세요.

## 추출 결과 데이터

`AudioExtractor.extract()`는 `AudioFile` 데이터 클래스를 반환합니다.
실제 음성 샘플은 MP3 파일에 저장하고, 객체에는 다음 정보를 담습니다.

| 속성 | 내용 |
| --- | --- |
| `file_path` | 저장한 음성의 절대 경로 (`Path`) |
| `sample_rate` | 샘플레이트 (Hz) |
| `channels` | 채널 수 |
| `sample_width`, `frame_count` | PCM 전용 정보, MP3에서는 `None` |
| `duration_seconds` | MP3 메타데이터에서 읽은 재생 시간 (초) |
| `bitrate` | 비트레이트 (bps) |
| `file_size_bytes`, `file_size_mb` | 파일 크기 (바이트 / MB) |
| `format` | 파일 형식 (`mp3`) |
| `subscript_lines` | 연결된 자막 목록 |

```python
audio = extractor.extract(VideoFile("example.mp4"))
print(audio.file_path, audio.duration_seconds, audio.sample_rate)
```
