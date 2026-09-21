import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from transcription_recovery import TranscriptionRecovery, suspect_ranges, prompt_echo
from audio_activity import AudioActivity


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def recovery(self, request):
        return TranscriptionRecovery(self.folder / "source.mp3", self.folder, request, lambda e: None)

    @patch("transcription_recovery.extract_clip")
    def test_utterance_failure_budget_and_trailing_silence_completion(self, extract):
        calls, progress = [], []
        def request(clip, destination, model, **kwargs):
            calls.append((model, kwargs["prompt_override"]))
            return {"text": "" if len(calls) <= 2 else "후반부 실제 발화입니다."}
        recovery = self.recovery(request)
        recovery.activity = AudioActivity(30, [(5, 10), (15, 20), (25, 30)])
        recovery.max_requests = 1
        result = recovery.transcribe_utterances(save_progress=lambda s, t: progress.append(t))
        self.assertEqual(calls, [("gpt-transcribe", None), ("gpt-transcribe", ""),
                                 ("gpt-transcribe", None), ("gpt-transcribe", None)])
        self.assertEqual([(s["start"], s["end"]) for s in result], [(10, 15), (20, 25)])
        self.assertEqual(progress[-1], 30)
        self.assertEqual([call.args[2:] for call in extract.call_args_list], [(0, 5), (10, 15), (20, 25)])
        self.assertEqual(sum(e["status"] == "needs_review" for e in recovery.events), 1)

    @patch("transcription_recovery.extract_clip")
    def test_utterance_prompt_echo_and_internal_repetition_are_omitted(self, extract):
        phrase = "현재 음성 구간에서 실제로 들리는 발화만 한국어로 전사하세요."
        for text in (phrase, "충분히 긴 문장이 계속 반복됩니다." * 3, {"invalid": "text"}):
            with self.subTest(text=text):
                recovery = self.recovery(lambda *a, **kw: {"text": text})
                recovery.activity = AudioActivity(8, [])
                recovery.prompt = phrase
                self.assertEqual(recovery.transcribe_utterances(), [])
                self.assertEqual(recovery.requests, 1)
                self.assertEqual(recovery.events[-1]["status"], "needs_review")

    @patch("transcription_recovery.extract_clip")
    def test_utterance_repetition_after_merge_updates_final_checkpoint(self, extract):
        recovery = self.recovery(lambda *a, **kw: {"text": "같은 문장만 계속 반복되고 있습니다."})
        recovery.activity = AudioActivity(100, [])
        checkpoints = []
        self.assertEqual(recovery.transcribe_utterances(
            save_progress=lambda s, end: checkpoints.append((list(s), end))), [])
        self.assertEqual(checkpoints[-1], ([], 100))
        self.assertEqual(recovery.events[-1]["reason"], "repetition_after_merge")

    @patch("transcription_recovery.extract_clip")
    def test_utterance_extraction_failure_does_not_block_next(self, extract):
        extract.side_effect = [RuntimeError("bad audio"), None]
        recovery = self.recovery(lambda *a, **kw: {"text": "정상 발화"})
        recovery.activity = AudioActivity(10, [(4, 6)])
        self.assertEqual(recovery.transcribe_utterances(), [{"start": 6, "end": 10, "text": "정상 발화"}])


    @patch("transcription_recovery.extract_clip")
    def test_failed_early_chunk_cannot_use_later_chunks_initial_budget(self, extract):
        calls = []
        progress = []
        def request(clip, destination, model, **kwargs):
            calls.append(destination.name)
            if destination.name.startswith("0000000000-") or not destination.stem.endswith("initial"):
                return {"segments": [], "text": ""}
            return {"segments": [{"start": 1.5, "end": 2.5, "text": "후반부의 정상 발화"}]}
        recovery = self.recovery(request)
        recovery.max_requests = 2
        result = recovery.transcribe_chunks(180, save_progress=lambda s, end: progress.append(end))
        self.assertEqual(len(calls), 5)  # 각 구간 첫 시도 3회, 앞부분 복구 2회
        self.assertEqual([s["start"] for s in result], [60, 120])
        self.assertEqual(progress, [60, 120, 180])
        self.assertTrue(all(e["end"] <= 60 for e in recovery.events if e["status"] == "needs_review"))

    @patch("transcription_recovery.extract_clip")
    def test_silent_middle_chunk_does_not_hide_later_speech(self, extract):
        calls = []
        def request(clip, destination, model, **kwargs):
            calls.append(destination.name)
            return {"segments": [{"start": 1.5, "end": 2.5, "text": "정상 음성"}]}
        recovery = self.recovery(request)
        recovery.activity = AudioActivity(180, [(60, 120)])
        result = recovery.transcribe_chunks(180)
        self.assertEqual(len(calls), 2)
        self.assertEqual([s["start"] for s in result], [1.5, 120])
        self.assertTrue(any(e.get("reason") == "silence" for e in recovery.events))

    @patch("transcription_recovery.extract_clip")
    def test_old_whole_response_repair_still_attempts_late_chunks(self, extract):
        calls = []
        def request(clip, destination, model, **kwargs):
            calls.append(destination.name)
            if destination.name.startswith("0000060000-"):
                return {"segments": [{"start": 1.5, "end": 5, "text": "마지막 구간을 복구했습니다"}]}
            return {"segments": []}
        recovery = self.recovery(request)
        recovery.max_requests = 0
        result = recovery.recover(None, 90)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result[0]["start"], 60)

    def test_silence_skips_requests_and_fake_subtitles(self):
        recovery = self.recovery(lambda *a, **kw: self.fail("No API for silence"))
        recovery.activity = AudioActivity(60, [(0, 60)])
        self.assertEqual(recovery.recover(None, 60), [])
        self.assertEqual(recovery.recover([{"start": 0, "end": 30, "text": "End of lecture."}], 60), [])
        self.assertTrue(all(e["reason"] == "silence" for e in recovery.events))

    @patch("transcription_recovery.extract_clip")
    def test_prompt_echo_rejected_even_in_fallback(self, extract):
        phrase = "한국어 대학 강의. 전문용어의 정확한 표기."
        recovery = self.recovery(lambda *a, **kw: {"text": phrase})
        recovery.prompt = phrase
        self.assertEqual(recovery._recover_clip(0, 15, 15, 2), [])
        self.assertEqual(recovery.events[-1]["status"], "needs_review")
        self.assertFalse(prompt_echo("텐서의 shape을 확인합니다.", phrase))

    @patch("transcription_recovery.extract_clip")
    def test_empty_time_is_not_a_reason_to_retry(self, extract):
        calls = []
        def request(*args, **kwargs):
            calls.append(args)
            return {"segments": [{"start": 0, "end": 2, "text": "실제 발화"}]}
        result = self.recovery(request)._recover_clip(0, 30, 30, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result[0]["end"], 2)

    @patch("transcription_recovery.extract_clip")
    def test_request_budget_stops_paid_recovery(self, extract):
        calls = []
        def request(*args, **kwargs):
            calls.append(args)
            return {"segments": []}
        recovery = self.recovery(request)
        recovery.max_requests = 2
        self.assertEqual(recovery.recover(None, 150), [])
        self.assertEqual(len(calls), 7)  # 5개 조각의 첫 시도 + 추가 복구 2회
        self.assertTrue(any(e.get("reason") == "recovery_request_limit" for e in recovery.events))

    @patch("transcription_recovery.extract_clip")
    def test_exhausted_recovery_records_review_without_subtitles(self, extract):
        requests = []
        def request(clip, destination, model, **kwargs):
            requests.append(model)
            return {"segments": [], "text": ""}
        recovery = self.recovery(request)
        result = recovery.recover(None, 30)
        self.assertEqual(requests, ["whisper-1", "whisper-1", "gpt-4o-transcribe",
                                    "whisper-1", "gpt-4o-transcribe"])
        self.assertEqual(result, [])
        self.assertEqual(sum(e["status"] == "needs_review" for e in recovery.events), 2)

    @patch("transcription_recovery.extract_clip")
    def test_fallback_model_restores_audio_text_with_absolute_times(self, extract):
        def request(clip, destination, model, **kwargs):
            return {"text": "꽃잎의 너비입니다."} if model == "gpt-4o-transcribe" else {"segments": []}
        recovery = self.recovery(request)
        result = recovery._recover_clip(1800, 1815, 1900, 1)
        self.assertEqual(result, [{"start": 1800, "end": 1815, "text": "꽃잎의 너비입니다."}])
        self.assertEqual(extract.call_args.args[2:], (1800, 1815))

    @patch("transcription_recovery.extract_clip")
    def test_unaffected_segments_and_boundary_ownership(self, extract):
        before = {"start": 0, "end": 10, "text": "정상 앞 문장"}
        after = {"start": 40, "end": 45, "text": "정상 뒤 문장"}
        bad = [{"start": 10 + i * 3, "end": 13 + i * 3,
                "text": "반복되는 충분히 긴 문장입니다"} for i in range(10)]
        def request(*args, **kwargs):
            return {"segments": [
                {"start": 0, "end": 1, "text": "앞쪽 문맥"},
                {"start": 1.5, "end": 31.5, "text": "복구한 문장"},
                {"start": 32, "end": 33, "text": "뒤쪽 문맥"},
            ]}
        result = self.recovery(request).recover([before, *bad, after], 45)
        self.assertEqual(result, [before, {"start": 10, "end": 40, "text": "복구한 문장"}, after])

    def test_all_repeated_runs_and_internal_repetition_are_found(self):
        segments = [{"start": i * 3, "end": i * 3 + 3,
                     "text": "충분히 길고 반복되는 문장입니다" if i < 6 else "다른 내용도 계속 반복됩니다"}
                    for i in range(12)]
        self.assertEqual(suspect_ranges(segments), [(0, 11)])
        self.assertTrue(suspect_ranges([{"start": 0, "end": 5,
                                        "text": "충분히 길고 반복되는 문장입니다" * 3}]))
        self.assertTrue(suspect_ranges([{"start": 0, "end": 11,
                                        "text": "petal width, petal length, " + "petal width, " * 5}]))

    @patch("transcription_recovery.extract_clip")
    def test_failed_extraction_marks_interval_and_continues(self, extract):
        extract.side_effect = RuntimeError("ffmpeg failed")
        recovery = self.recovery(lambda *args, **kwargs: self.fail("unexpected request"))
        result = recovery.recover(None, 60)
        self.assertEqual(result, [])
        self.assertTrue(all(e["status"] == "needs_review" for e in recovery.events))

    @patch("transcription_recovery.extract_clip")
    def test_missing_tail_and_out_of_bounds_response_are_recovered(self, extract):
        def request(*args, **kwargs):
            return {"segments": [{"start": 0, "end": 30, "text": "원음으로 복구한 전체 내용"}]}
        recovery = self.recovery(request)
        result = recovery.recover([{"start": 0, "end": 22, "text": "petal width " * 5}], 30)
        self.assertEqual(result[-1]["end"], 30)
        result = recovery.recover([{"start": 0, "end": 35, "text": "petal width " * 5}], 30)
        self.assertEqual(result[-1]["end"], 30)

    @patch("transcription_recovery.extract_clip")
    def test_repetition_across_recovered_chunks_is_not_silently_accepted(self, extract):
        def request(*args, **kwargs):
            offset = 0 if args[1].stem.startswith("0000000000-") else 1.5
            return {"segments": [{"start": offset, "end": 30 + offset,
                                  "text": "복구했지만 계속 같은 문장입니다"}]}
        recovery = self.recovery(request)
        result = recovery.recover(None, 150)
        self.assertEqual(result, [])
        self.assertEqual(recovery.events[-1]["reason"], "repetition_after_merge")


if __name__ == "__main__":
    unittest.main()
