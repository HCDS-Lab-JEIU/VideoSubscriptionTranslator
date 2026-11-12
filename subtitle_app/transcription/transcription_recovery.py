"""의심스러운 전사 구간을 원음에서 재전사하고 원래 시간축에 병합합니다."""

import math
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

from subtitle_app.media.ffmpeg_tools import get_ffmpeg_executable


def prompt_echo(text: str, prompt: str) -> bool:
    normalize = lambda s: re.sub(r"[\W_]+", "", s).casefold()
    value, context = normalize(text), normalize(prompt)
    if not context or len(value) < 8:
        return False
    if value in context:
        return True
    match = SequenceMatcher(None, value, context, autojunk=False).find_longest_match()
    return match.size >= 60 and match.size / len(value) >= 0.6


def suspect_ranges(segments: list[dict]) -> list[tuple[int, int]]:
    """반복 전체를 찾습니다. 반환값은 양 끝을 포함한 구간 인덱스입니다."""
    bad = set()
    run = []
    previous = ""

    def finish():
        if (len(run) >= 5 and len(previous) >= 12
                and segments[run[-1]]["end"] - segments[run[0]]["start"] >= 15):
            bad.update(run)

    for i, segment in enumerate(segments):
        text = re.sub(r"[\W_]+", "", segment["text"]).casefold()
        if not (text and text == previous and run
                and 0 <= segment["start"] - segments[run[-1]]["end"] <= 1):
            finish()
            run = []
        run.append(i)
        previous = text
        # 짧게 나눈 응답에서도 한 구간 내부의 반복을 놓치지 않습니다.
        if (segment.get("compression_ratio") or 0) >= 4:
            bad.add(i)
        if re.search(r"(.{6,}?)\1{2,}", text):
            bad.add(i)
    finish()
    ranges = []
    for i in sorted(bad):
        if ranges and i == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], i)
        else:
            ranges.append((i, i))
    return ranges


def valid_segments(segments, duration=None) -> bool:
    if not isinstance(segments, list) or not segments:
        return False
    previous = -1.0
    for segment in segments:
        try:
            start, end = segment["start"], segment["end"]
            if (not math.isfinite(start) or not math.isfinite(end)
                    or start < 0 or end <= start or start < previous
                    or (duration is not None and end > duration + 0.5)
                    or not isinstance(segment["text"], str)):
                return False
            previous = start
        except (KeyError, TypeError):
            return False
    return any(s["text"].strip() for s in segments)


def extract_clip(source: Path, target: Path, start: float, end: float) -> None:
    duration = end - start
    # 짧은 소리도 보존하되 API가 거부할 수 있는 초단기 파일은 무음으로 채웁니다.
    # 먼저 잘라낸 뒤 패딩하므로 다음 발화가 입력에 섞이지 않습니다.
    result = subprocess.run([
        get_ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-nostdin",
        "-n", "-ss", str(start), "-i", str(source), "-t", str(max(duration, 0.5)),
        "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
        "-af", f"atrim=duration={duration},apad=whole_dur=0.5",
        str(target),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if result.returncode:
        raise RuntimeError("복구 음성 추출 실패: " + result.stderr[-1000:])


class TranscriptionRecovery:
    def __init__(self, source, folder, request, save_report, *, activity=None, prompt="", max_requests=12):
        self.source = source
        self.folder = folder
        self.request = request
        self.save_report = save_report
        self.events = []
        self.activity = activity
        self.prompt = prompt
        self.max_requests = max_requests
        self.requests = 0

    def _omit(self, start, end, reason, status="needs_review"):
        self.events.append({"start": start, "end": end, "status": status, "reason": reason})
        self.save_report(self.events)
        return []

    def filter_segments(self, segments):
        result = []
        for segment in segments:
            start, end = segment["start"], segment["end"]
            if self.activity is not None and not self.activity.has_sound(start, end):
                self._omit(start, end, "silence", "skipped")
            else:
                item = dict(segment)
                if self.activity is not None:
                    item["start"], item["end"] = self.activity.sound_bounds(start, end)
                if prompt_echo(item["text"], self.prompt):
                    item["compression_ratio"] = 4  # 원음에서 힌트 없이 재확인할 대상
                result.append(item)
        return result

    def transcribe_chunks(self, duration, *, chunk_seconds=60, save_progress=None):
        """각 구간의 첫 전사는 복구 예산과 무관하게 실행합니다."""
        if chunk_seconds <= 0:
            raise ValueError("전사 구간 길이는 양수여야 합니다.")
        count = math.ceil(duration / chunk_seconds)
        active = sum(self.activity is None or self.activity.has_sound(i * chunk_seconds,
                     min(duration, (i + 1) * chunk_seconds)) for i in range(count))
        print(f"분할 전사: {count}구간, 무음 제외 첫 요청 최대 {active}회, "
              f"추가 복구 최대 {self.max_requests}회", flush=True)
        result = []
        for index in range(count):
            start, end = index * chunk_seconds, min(duration, (index + 1) * chunk_seconds)
            print(f"전사 [{index + 1}/{count}]: {start:.1f} ~ {end:.1f}초", flush=True)
            result.extend(self._recover_clip(start, end, duration, 0, primary=True))
            if save_progress is not None:
                save_progress(result, end)
        return result

    def transcribe_utterances(self, *, model="gpt-transcribe", max_seconds=20, save_progress=None):
        """무음 경계로 자른 구간의 텍스트와 로컬 시간을 결합합니다."""
        ranges = self.activity.utterance_ranges(max_seconds=max_seconds)
        audio_seconds = sum(end - start for start, end in ranges)
        print(f"무음 경계 전사 ({model}): 첫 요청 최대 {len(ranges)}회, "
              f"추가 복구 최대 {self.max_requests}회", flush=True)
        print(f"첫 전사 음성 합계: {audio_seconds / 60:.2f}분 "
              "(각 구간을 한 번씩 전송하며, 전체 영상을 반복 전송하지 않습니다.)", flush=True)
        result = []
        for index, (start, end) in enumerate(ranges):
            print(f"전사 [{index + 1}/{len(ranges)}]: {start:.3f} ~ {end:.3f}초", flush=True)
            name = f"{round(start * 1000):010d}-{round(end * 1000):010d}"
            self.folder.mkdir(parents=True, exist_ok=True)
            clip = self.folder / f"{name}.mp3"
            try:
                # 타임스탬프 없는 텍스트 응답이므로 인접 발화를 중복 포함하지 않습니다.
                extract_clip(self.source, clip, start, end)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                self._omit(start, end, "audio_extraction_failed")
            else:
                for attempt in range(2):
                    if attempt and self.requests >= self.max_requests:
                        self._omit(start, end, "recovery_request_limit")
                        break
                    if attempt:
                        self.requests += 1
                        print(f"추가 복구 [{self.requests}/{self.max_requests}]: "
                              f"{start:.3f} ~ {end:.3f}초 (이 구간만 재전송)", flush=True)
                    response_name = f"{name}-{'retry' if attempt else 'initial'}.json"
                    raw = self.request(clip, self.folder / response_name, model,
                                       prompt_override="" if attempt else None)
                    text = raw.get("text")
                    text = " ".join(text.split()) if isinstance(text, str) else ""
                    item = {"start": start, "end": end, "text": text}
                    good = (bool(text) and not raw.get("error")
                            and not prompt_echo(text, self.prompt) and not suspect_ranges([item]))
                    self.events.append({"start": start, "end": end, "model": model,
                                        "attempt": "recovery" if attempt else "initial",
                                        "status": "recovered" if good else "retry",
                                        "timing": "audio_boundaries", "response": response_name})
                    self.save_report(self.events)
                    if good:
                        result.append(item)
                        break
                    if attempt:
                        self._omit(start, end, "unreliable_transcription")
            if save_progress is not None:
                save_progress(result, end)
        # 구간 각각은 정상 형태여도 긴 반복으로 이어지는 응답은 내보내지 않습니다.
        bad = suspect_ranges(result)
        for first, last in reversed(bad):
            self._omit(result[first]["start"], result[last]["end"], "repetition_after_merge")
            del result[first:last + 1]
        if save_progress is not None:
            save_progress(result, self.activity.duration)
        return result

    def recover(self, segments, duration):
        if valid_segments(segments):
            segments = self.filter_segments(segments)
            if not segments:
                return []
        # 일부 응답은 파일 끝을 넘는 반복 타임스탬프를 만듭니다.
        # 이 경우 정상 앞부분까지 재요청하지 않고 실제 음성 범위만 복구합니다.
        if valid_segments(segments):
            bounded = []
            for original in segments:
                if original["start"] >= duration:
                    continue
                item = dict(original)
                if item["end"] > duration:
                    item["end"] = duration
                    item["compression_ratio"] = max(item.get("compression_ratio") or 0, 4)
                bounded.append(item)
            segments = bounded
        ranges = suspect_ranges(segments) if valid_segments(segments, duration) else []
        if not valid_segments(segments, duration):
            segments = [{"start": 0, "end": duration, "text": ""}]
            ranges = [(0, 0)]
        result = []
        cursor = 0
        for first, last in ranges:
            result.extend(segments[cursor:first])
            start, end = segments[first]["start"], segments[last]["end"]
            # 반복 응답은 마지막 실제 발화를 아예 누락하기도 합니다.
            if first == 0:
                start = 0
            if last == len(segments) - 1:
                end = duration
            print(f"전사 자동 복구: {start:.1f} ~ {end:.1f}초", flush=True)
            while start < end:
                stop = min(start + 30, end)
                # 기존 전체 응답을 복구할 때도 뒤쪽 조각의 첫 재전사는 보장합니다.
                result.extend(self._recover_clip(start, stop, duration, depth=0, primary=True))
                start = stop
            cursor = last + 1
        result.extend(segments[cursor:])
        # 조각별로는 짧은 반복이라도 합친 뒤 긴 반복이 되는 경우를 성공으로 내보내지 않습니다.
        remaining = suspect_ranges(result)
        if not remaining:
            return result
        checked = []
        cursor = 0
        for first, last in remaining:
            checked.extend(result[cursor:first])
            start, end = result[first]["start"], result[last]["end"]
            self.events.append({"start": start, "end": end, "status": "needs_review",
                                "reason": "repetition_after_merge"})
            cursor = last + 1
        checked.extend(result[cursor:])
        self.save_report(self.events)
        print("복구 결과에 남은 반복 구간은 확인 필요로 표시합니다. 후속 처리를 계속합니다.", flush=True)
        return checked

    def _recover_clip(self, start, end, duration, depth, *, primary=False):
        if self.activity is not None and not self.activity.has_sound(start, end):
            return self._omit(start, end, "silence", "skipped")
        if not primary and self.requests >= self.max_requests:
            return self._omit(start, end, "recovery_request_limit")
        # 문장 경계 앞뒤를 함께 듣되, 각 조각의 중심 시각으로 소유권을 결정합니다.
        padding = 1.5 if depth < 2 else 0
        clip_start, clip_end = max(0, start - padding), min(duration, end + padding)
        name = f"{round(start * 1000):010d}-{round(end * 1000):010d}-{depth}"
        if primary:
            name += "-initial"
        self.folder.mkdir(parents=True, exist_ok=True)
        clip = self.folder / f"{name}.mp3"
        try:
            extract_clip(self.source, clip, clip_start, clip_end)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            self.events.append({"start": start, "end": end, "status": "needs_review",
                                "reason": "audio_extraction_failed"})
            self.save_report(self.events)
            print(f"복구 음성 추출 실패: {start:.1f} ~ {end:.1f}초 (후속 처리 계속)", flush=True)
            return []
        model = "whisper-1" if depth < 2 else "gpt-4o-transcribe"
        # 힌트 자체가 반복되는 실패도 있으므로 짧은 Whisper 재시도는 힌트를 비웁니다.
        if not primary:
            self.requests += 1
        raw = self.request(clip, self.folder / f"{name}.json", model,
                           prompt_override=None if primary else "")
        local = raw.get("segments")
        if depth == 2:
            text = (raw.get("text") or "").strip()
            local = [{"start": 0, "end": clip_end - clip_start, "text": text}] if text else []
        good = valid_segments(local, clip_end - clip_start) and not suspect_ranges(local)
        if good:
            good = not any(prompt_echo(s["text"], self.prompt) for s in local)
        mapped = []
        if good:
            for segment in local:
                middle = clip_start + (segment["start"] + segment["end"]) / 2
                if depth == 2 or start <= middle < end:
                    item = dict(segment)
                    item.update(start=max(start, clip_start + segment["start"]),
                                end=min(end, clip_start + segment["end"]))
                    if (item["end"] > item["start"] and item["text"].strip()
                            and (self.activity is None or self.activity.has_sound(item["start"], item["end"]))):
                        if self.activity is not None:
                            item["start"], item["end"] = self.activity.sound_bounds(item["start"], item["end"])
                        mapped.append(item)
            good = bool(mapped)
        event = {"start": start, "end": end, "model": model,
                 "status": "recovered" if good else "retry", "response": f"{name}.json",
                 "attempt": "initial" if primary else "recovery"}
        if depth == 2:
            event["timing"] = "whole_clip"
        self.events.append(event)
        self.save_report(self.events)
        if good:
            return mapped
        if depth == 0:
            middle = (start + end) / 2
            return (self._recover_clip(start, middle, duration, 1)
                    + self._recover_clip(middle, end, duration, 1))
        if depth == 1:
            return self._recover_clip(start, end, duration, 2)
        event["status"] = "needs_review"
        self.save_report(self.events)
        print(f"전사 확인 필요: {start:.1f} ~ {end:.1f}초 (후속 처리 계속)", flush=True)
        return []
