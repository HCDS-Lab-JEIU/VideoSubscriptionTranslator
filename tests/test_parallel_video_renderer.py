"""Subtitle-count partitioning and physical core discovery checks."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from subtitle_app.rendering.parallel_video_renderer import physical_core_count, subtitle_segments


class SubtitlePartitionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "captions.srt"

    def partition(self, starts, cores, duration=200):
        def stamp(seconds):
            milliseconds = round(seconds * 1000)
            minutes, remainder = divmod(milliseconds, 60000)
            seconds, milliseconds = divmod(remainder, 1000)
            return f"00:{minutes:02}:{seconds:02},{milliseconds:03}"

        self.path.write_text("\n\n".join(
            f"{i}\n{stamp(start)} --> {stamp(start + 2)}\nCaption {i}"
            for i, start in enumerate(starts, 1)), encoding="utf-8")
        return subtitle_segments(self.path, duration, cores)

    def test_more_than_four_workers_get_contiguous_balanced_subtitle_ranges(self):
        pieces = self.partition(range(100), 8)
        self.assertEqual([(p.first, p.last) for p in pieces],
                         [(1, 13), (14, 26), (27, 39), (40, 52),
                          (53, 64), (65, 76), (77, 88), (89, 100)])
        self.assertEqual(pieces[0].start, 0)
        self.assertEqual(pieces[-1].end, 200)
        for previous, following in zip(pieces, pieces[1:]):
            self.assertEqual(previous.end, following.start)
            self.assertEqual(previous.last + 1, following.first)

    def test_uneven_timing_splits_by_count_and_preserves_gaps(self):
        pieces = self.partition([10, 11, 12, 100, 110, 111], 3)
        self.assertEqual([(p.first, p.last, p.start, p.end) for p in pieces],
                         [(1, 2, 0, 12), (3, 4, 12, 110), (5, 6, 110, 200)])

    def test_worker_count_is_limited_by_subtitle_count(self):
        self.assertEqual(len(self.partition([10, 20], 32)), 2)
        self.assertEqual(len(self.partition([10, 20], 1)), 1)

    def test_simultaneous_starts_stay_together(self):
        pieces = self.partition([1, 1, 1, 10], 4)
        self.assertEqual([(p.first, p.last) for p in pieces], [(1, 3), (4, 4)])
        self.assertTrue(all(p.start < p.end for p in pieces))

    def test_subtitles_beyond_duration_do_not_create_empty_intervals(self):
        pieces = self.partition([1, 10, 20], 3, duration=5)
        self.assertEqual([(p.first, p.last, p.start, p.end) for p in pieces],
                         [(1, 3, 0, 5)])

    def test_empty_and_invalid_subtitles_fail_before_rendering(self):
        for content in ("", "invalid", "1\n00:00:02,000 --> 00:00:01,000\nCaption"):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    subtitle_segments(self.path, 10, 4)

    def test_physical_core_detection_returns_positive_integer(self):
        count = physical_core_count()
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 1)

    def test_unknown_core_count_uses_one_without_logical_estimate(self):
        with patch("subtitle_app.rendering.parallel_video_renderer.os.name", "posix"), \
             patch("subtitle_app.rendering.parallel_video_renderer.Path") as path, \
             patch("subtitle_app.rendering.parallel_video_renderer.subprocess.run", side_effect=OSError), \
             patch("subtitle_app.rendering.parallel_video_renderer.os.cpu_count") as logical:
            path.return_value.is_dir.return_value = False
            self.assertEqual(physical_core_count(), 1)
            logical.assert_not_called()
