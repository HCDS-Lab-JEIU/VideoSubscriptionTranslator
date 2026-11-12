"""Preview timing, seeking, overlay layout and nonblocking player handoff."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from qtTest.subtitle_preview import SubtitleTrack
from qtTest.videoPlayer import QVideoPlayer
from qtTest.MyApp import MyApp


SRT = ("1\n00:00:01,000 --> 00:00:03,000\nVoltage < current\nsecond line\n\n"
       "2\n00:00:02,000 --> 00:00:02,500\n겹치는 자막\n\n"
       "3\n00:00:04,000 --> 00:00:05,000\nResistance\n\n")


class SubtitlePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.srt = self.root / "영어 자막.srt"
        self.srt.write_text(SRT, encoding="utf-8-sig", newline="\r\n")
        self.video = self.root / "video.mp4"

    def test_boundaries_gaps_overlaps_and_backward_seeks(self):
        track = SubtitleTrack.load(self.srt)
        for position, expected in (
            (999, ""), (1000, "Voltage < current\nsecond line"),
            (2000, "Voltage < current\nsecond line\n겹치는 자막"),
            (2500, "Voltage < current\nsecond line"), (3000, ""),
            (4000, "Resistance"), (5000, ""), (1000, "Voltage < current\nsecond line"),
        ):
            self.assertEqual(track.text_at(position), expected)

    def test_invalid_srt_is_rejected(self):
        for content in ("bad", "1\n00:00:02,000 --> 00:00:01,000\nBackwards\n",
                        "1\n00:61:00,000 --> 00:62:00,000\nBad minutes\n"):
            self.srt.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                SubtitleTrack.load(self.srt)

    def make_player(self):
        player = QVideoPlayer()
        player.current_path = self.video.resolve()
        self.addCleanup(player.deleteLater)
        return player

    def test_load_while_paused_preserves_playback_and_toggle_updates_immediately(self):
        player = self.make_player()
        with patch.object(player.media_player, "position", return_value=1500), \
             patch.object(player.media_player, "setPosition") as seek, \
             patch.object(player.media_player, "play") as play, \
             patch.object(player.media_player, "setSource") as source:
            self.assertTrue(player.load_subtitles(self.video, self.srt))
            self.assertEqual(player.video_widget.caption.toPlainText(), "Voltage < current\nsecond line")
            player.subtitle_checkbox.setChecked(False)
            self.assertFalse(player.video_widget.caption.isVisible())
            player.subtitle_checkbox.setChecked(True)
            self.assertTrue(player.video_widget.caption.isVisible())
            seek.assert_not_called()
            play.assert_not_called()
            source.assert_not_called()
        player._update_position(4100)
        self.assertEqual(player.video_widget.caption.toPlainText(), "Resistance")
        player._update_position(3500)
        self.assertFalse(player.video_widget.caption.isVisible())

    def test_unrelated_video_is_ignored_and_new_video_clears_old_subtitles(self):
        player = self.make_player()
        player.load_subtitles(self.video, self.srt)
        self.assertFalse(player.load_subtitles(self.root / "other.mp4", self.root / "missing.srt"))
        self.assertTrue(player.subtitle_checkbox.isEnabled())
        self.video.write_bytes(b"placeholder")
        with patch.object(player.media_player, "setSource"), patch.object(player.media_player, "play"), \
             patch.object(player.wave_visualizer, "load_media"):
            player.load_video(self.video)
        self.assertFalse(player.subtitle_checkbox.isEnabled())
        self.assertFalse(player.video_widget.caption.isVisible())
        self.assertEqual(player.subtitle_track.text_at(1500), "")

    def test_overlay_remains_inside_video_view_after_resize(self):
        player = self.make_player()
        player.show()
        self.addCleanup(player.close)
        player.load_subtitles(self.video, self.srt)
        player._update_position(1500)
        for width, height in ((1000, 650), (600, 350)):
            player.resize(width, height)
            self.app.processEvents()
            view = player.video_widget
            self.assertTrue(view.sceneRect().contains(view.caption.sceneBoundingRect()))
            self.assertGreater(view.caption.zValue(), view.video_item.zValue())

    def test_main_window_handoff_and_preview_error_do_not_stop_encoding(self):
        window = MyApp()
        self.addCleanup(window.deleteLater)
        player, panel = window.video_player, window.pipeline_panel
        player.current_path = self.video.resolve()
        panel._set_busy(True)
        panel.subtitles_ready.emit(str(self.video), str(self.srt))
        self.assertTrue(player.subtitle_checkbox.isEnabled())
        panel.subtitles_ready.emit(str(self.video), str(self.root / "missing.srt"))
        self.assertTrue(panel.busy)
        self.assertIn("인코딩은 계속", window.statusBar().currentMessage())
        panel.preview_reset.emit()
        self.assertFalse(player.subtitle_checkbox.isEnabled())
        panel._set_busy(False)
