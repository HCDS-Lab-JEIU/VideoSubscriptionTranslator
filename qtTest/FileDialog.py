"""영상 파일 선택 다이얼로그."""

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QWidget


class FileDialog:
    @staticmethod
    def select_video_file(parent: QWidget | None = None) -> Path | None:
        file_name, _ = QFileDialog.getOpenFileName(
            parent,
            "Open Video",
            "",
            "Video Files (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.wmv);;"
            "All Files (*)",
        )
        return Path(file_name) if file_name else None
