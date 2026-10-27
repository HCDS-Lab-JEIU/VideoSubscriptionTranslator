"""Real FFmpeg checks for chunk boundaries, audio and safe failures; no API calls."""

import contextlib
import io
from pathlib import Path
import subprocess
import re
import tempfile
import unittest
from unittest.mock import patch

from ffmpeg_tools import get_ffmpeg_executable
from video_subtitler import VideoSubtitler, VideoSubtitleError


class VideoSubtitlerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="병렬 자막 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ffmpeg = get_ffmpeg_executable()
        self.video = self.root / "강의.mp4"
        self.srt = self.root / "자막.srt"
        self.srt.write_text(
            "1\n00:00:01,500 --> 00:00:02,600\nBoundary caption\n\n"
            "2\n00:00:04,300 --> 00:00:05,300\nLater caption\n\n", encoding="utf-8")

    def ff(self, *arguments):
        result = subprocess.run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                                 *map(str, arguments)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        return result.stdout

    def make_video(self, *, audio=True, rate="10", duration="6"):
        args = ["-f", "lavfi", "-i", f"color=black:s=160x120:r={rate}:d={duration}"]
        if audio:
            args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", "-c:a", "aac"]
        self.ff(*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", self.video)

    def render_pair(self, segment_seconds=2):
        serial = self.root / "serial.mp4"
        parallel = self.root / "parallel.mp4"
        with contextlib.redirect_stdout(io.StringIO()):
            VideoSubtitler().render(self.video, self.srt, serial)
            with patch("parallel_video_renderer.SEGMENT_SECONDS", segment_seconds):
                VideoSubtitler().render(self.video, self.srt, parallel, parallel=True)
        return serial, parallel

    def frames(self, video):
        return self.ff("-i", video, "-map", "0:v:0", "-fps_mode", "passthrough",
                       "-pix_fmt", "gray", "-f", "rawvideo", "-")

    def test_parallel_preserves_frames_boundary_captions_and_audio(self):
        self.make_video()
        original = self.video.read_bytes()
        serial, parallel = self.render_pair()
        first, second = self.frames(serial), self.frames(parallel)
        size = 160 * 120
        self.assertEqual(len(first), 60 * size)
        self.assertEqual(len(first), len(second))
        for frame in (18, 22, 30, 46, 56):
            a = first[frame * size:(frame + 1) * size]
            b = second[frame * size:(frame + 1) * size]
            self.assertLess(sum(abs(x - y) for x, y in zip(a, b)) / size, 1)
            if frame in (18, 22, 46):
                self.assertGreater(sum(b), 1000, f"Missing caption at frame {frame}")
            else:
                self.assertLess(sum(b), 1000, f"Unexpected caption at frame {frame}")
        a = self.ff("-i", serial, "-map", "0:a:0", "-ar", "8000", "-f", "s16le", "-")
        b = self.ff("-i", parallel, "-map", "0:a:0", "-ar", "8000", "-f", "s16le", "-")
        self.assertEqual(a, b)  # One audio encode, no added gaps at chunk boundaries.
        self.assertEqual(self.video.read_bytes(), original)
        self.assertFalse(list(self.root.glob(".render-*")))

    def test_fractional_frame_rate_and_cuts_without_audio(self):
        self.make_video(audio=False, rate="30000/1001", duration="6.2")
        serial, parallel = self.render_pair(segment_seconds=2.03)
        self.assertEqual(len(self.frames(serial)), len(self.frames(parallel)))
        for point in ("1.8", "2.2", "3.5", "4.5", "5.6"):
            a = self.ff("-ss", point, "-i", serial, "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", "-")
            b = self.ff("-ss", point, "-i", parallel, "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", "-")
            self.assertEqual(len(a), len(b))
            self.assertLess(sum(abs(x - y) for x, y in zip(a, b)) / len(a), 1)

    def test_variable_frame_rate_preserves_timeline(self):
        self.ff("-f", "lavfi", "-i", "color=black:s=160x120:r=10:d=6",
                "-vf", "select='if(lt(t,3),1,not(mod(n,2)))'", "-fps_mode", "vfr",
                "-c:v", "libx264", self.video)
        parallel = self.root / "parallel.mp4"
        with patch("parallel_video_renderer.SEGMENT_SECONDS", 2.03), \
             contextlib.redirect_stdout(io.StringIO()):
            VideoSubtitler().render(self.video, self.srt, parallel, parallel=True)

        def timestamps(video):
            result = subprocess.run([self.ffmpeg, "-hide_banner", "-i", str(video),
                                     "-vf", "showinfo", "-fps_mode", "passthrough", "-f", "null", "-"],
                                    capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return [float(value) for value in re.findall(r"pts_time:([\d.]+)", result.stderr)]

        before, after = timestamps(self.video), timestamps(parallel)
        self.assertEqual(len(before), len(after))
        for a, b in zip(before, after):
            self.assertAlmostEqual(a, b, delta=0.02)

    def test_audio_longer_than_video_does_not_join_empty_tail(self):
        self.ff("-f", "lavfi", "-i", "color=black:s=160x120:r=10:d=2",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=4.1",
                "-c:v", "libx264", "-c:a", "aac", self.video)
        serial, parallel = self.render_pair(segment_seconds=2)
        self.assertEqual(len(self.frames(serial)), len(self.frames(parallel)))

    def test_parallel_failure_leaves_no_output_and_cleans_temporary_files(self):
        self.make_video()
        output = self.root / "result.mp4"
        self.srt.write_text("invalid subtitle", encoding="utf-8")
        with patch("parallel_video_renderer.SEGMENT_SECONDS", 2), \
             contextlib.redirect_stdout(io.StringIO()), self.assertRaises(VideoSubtitleError):
            VideoSubtitler().render(self.video, self.srt, output, parallel=True)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob(".render-*")))

    def test_existing_destination_is_preserved(self):
        self.make_video(audio=False)
        output = self.root / "result.mp4"
        output.write_bytes(b"existing output")
        with self.assertRaises(FileExistsError):
            VideoSubtitler().render(self.video, self.srt, output, parallel=True)
        self.assertEqual(output.read_bytes(), b"existing output")
