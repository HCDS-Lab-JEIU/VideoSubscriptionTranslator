import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from subtitle_app.media.audio_activity import AudioActivity


class AudioActivityTests(unittest.TestCase):
    def test_utterances_use_pauses_and_exclude_leading_trailing_silence(self):
        activity = AudioActivity(12, [(0, 1), (4, 5), (8, 10), (11, 12)])
        self.assertEqual(activity.utterance_ranges(), [(1, 4), (5, 8), (10, 11)])

    def test_short_hesitation_does_not_split_sentence(self):
        activity = AudioActivity(5, [(2, 2.4)])
        self.assertEqual(activity.utterance_ranges(), [(0, 5)])

    def test_pause_threshold_never_discards_quiet_speech(self):
        activity = AudioActivity(8, [], [(2, 6)])
        self.assertEqual(activity.utterance_ranges(), [(0, 4), (4, 8)])

    def test_quiet_voice_does_not_hide_internal_true_silence(self):
        activity = AudioActivity(60, [(5, 55)], [(0, 60)])
        self.assertEqual(activity.utterance_ranges(), [(0, 5), (55, 60)])

    def test_long_speech_is_bounded_without_gaps_or_overlap(self):
        activity = AudioActivity(47, [])
        self.assertEqual(activity.utterance_ranges(), [(0, 20), (20, 40), (40, 47)])
        self.assertEqual(AudioActivity(47, [(0, 47)]).utterance_ranges(), [])

    def test_named_ffmpeg_detectors_are_kept_separate(self):
        log = ("[silencedetect@quiet @ x] silence_start: 0\n"
               "[silencedetect@pause @ y] silence_start: 0\n"
               "[silencedetect@quiet @ x] silence_end: 1 | silence_duration: 1\n"
               "[silencedetect@pause @ y] silence_end: 2 | silence_duration: 2\n")
        with patch("mutagen.mp3.MP3", return_value=SimpleNamespace(info=SimpleNamespace(length=5))), \
             patch("subtitle_app.media.audio_activity.get_ffmpeg_executable", return_value="ffmpeg"), \
             patch("subtitle_app.media.audio_activity.subprocess.run", return_value=SimpleNamespace(returncode=0, stderr=log)):
            activity = AudioActivity.analyze(Path("fake.mp3"))
        self.assertEqual(activity.silence, [(0, 1)])
        self.assertEqual(activity.pauses, [(0, 2)])

    def test_real_ffmpeg_boundaries(self):
        import subprocess
        import tempfile
        from subtitle_app.media.ffmpeg_tools import get_ffmpeg_executable
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bursts.mp3"
            subprocess.run([get_ffmpeg_executable(), "-hide_banner", "-loglevel", "error",
                            "-f", "lavfi", "-i",
                            "aevalsrc=if(between(t\\,0.5\\,1.5)+between(t\\,2.5\\,3.5)\\,0.2*sin(2*PI*440*t)\\,0):s=16000:d=4",
                            "-b:a", "64k", str(source)], check=True, capture_output=True, timeout=30)
            activity = AudioActivity.analyze(source)
        ranges = activity.utterance_ranges()
        self.assertEqual(len(ranges), 2)
        for actual, expected in zip(ranges, [(0.5, 1.5), (2.5, 3.5)]):
            for value, target in zip(actual, expected):
                self.assertAlmostEqual(value, target, delta=0.05)

    def test_silence_boundaries_preserve_quiet_sound_and_real_gaps(self):
        activity = AudioActivity(30, [(0, 5), (10, 20), (25, 30)])
        self.assertFalse(activity.has_sound(12, 18))
        self.assertTrue(activity.has_sound(4, 6))
        self.assertEqual(activity.sound_bounds(0, 30), (5, 25))
        self.assertEqual(activity.sound_bounds(10, 22), (20, 22))
        self.assertIsNone(activity.sound_bounds(25, 30))

    def test_short_clip_is_padded_without_including_next_sound(self):
        import array
        import subprocess
        import tempfile
        from subtitle_app.media.ffmpeg_tools import get_ffmpeg_executable
        from subtitle_app.transcription.transcription_recovery import extract_clip
        executable = get_ffmpeg_executable()
        with tempfile.TemporaryDirectory() as folder:
            source, clip = Path(folder) / "source.wav", Path(folder) / "clip.mp3"
            subprocess.run([executable, "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=1",
                str(source)], check=True, capture_output=True, timeout=30)
            extract_clip(source, clip, 0, 0.062)
            decoded = subprocess.run([executable, "-hide_banner", "-loglevel", "error",
                "-i", str(clip), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                check=True, capture_output=True, timeout=30)
        samples = array.array("h", decoded.stdout)
        self.assertGreaterEqual(len(samples), 8000)
        self.assertGreater(max(abs(s) for s in samples[:800]), 100)
        self.assertLess(max(abs(s) for s in samples[3200:]), 10)

    def test_ffmpeg_scan_handles_trailing_silence(self):
        with patch("mutagen.mp3.MP3", return_value=SimpleNamespace(info=SimpleNamespace(length=30))), \
             patch("subtitle_app.media.audio_activity.get_ffmpeg_executable", return_value="ffmpeg"), \
             patch("subtitle_app.media.audio_activity.subprocess.run", return_value=SimpleNamespace(returncode=0,
                 stderr="silence_start: 0\nsilence_end: 10 | silence_duration: 10\nsilence_start: 20\n")):
            activity = AudioActivity.analyze(Path("fake.mp3"))
        self.assertEqual(activity.silence, [(0, 10), (20, 30)])

    def test_failed_scan_does_not_guess_silence(self):
        with patch("mutagen.mp3.MP3", return_value=SimpleNamespace(info=SimpleNamespace(length=30))), \
             patch("subtitle_app.media.audio_activity.get_ffmpeg_executable", return_value="ffmpeg"), \
             patch("subtitle_app.media.audio_activity.subprocess.run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(RuntimeError):
                AudioActivity.analyze(Path("fake.mp3"))

    def test_mp3_padding_is_not_mistaken_for_sound(self):
        with patch("mutagen.mp3.MP3", return_value=SimpleNamespace(info=SimpleNamespace(length=3167.1))), \
             patch("subtitle_app.media.audio_activity.get_ffmpeg_executable", return_value="ffmpeg"), \
             patch("subtitle_app.media.audio_activity.subprocess.run", return_value=SimpleNamespace(returncode=0,
                 stderr="silence_start: 0\ntime=00:52:47.01\nsilence_end: 3167.016062\n")):
            activity = AudioActivity.analyze(Path("fake.mp3"))
        self.assertFalse(activity.has_sound(0, activity.duration))
