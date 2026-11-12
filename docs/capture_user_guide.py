"""Capture the actual Qt windows with synthetic data for the usage guide."""

import json
import math
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QPoint, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPen
from PyQt6.QtMultimedia import QVideoFrame
from PyQt6.QtWidgets import QApplication, QListWidgetItem
from subtitle_app.ui.main_window import MyApp
from subtitle_app.ui.textbook_editor.editor import TextbookEditorWindow
from subtitle_app.ui.textbook_editor.auto_dialog import AutoTextbookDialog
from subtitle_app.ui.textbook_editor.data import TextbookDocument, TextbookRepository
from subtitle_app.textbook.document import Textbook
from subtitle_app.textbook.auto import TermCandidate

OUT = ROOT / "docs" / "user-guide"
(OUT / "raw").mkdir(parents=True, exist_ok=True)
BOOK = ("[Common Rules]\n전기 회로의 전문 용어와 단위를 일관되게 표기하세요.\n\n"
        "[Whisper Rules]\n전압, 전류, 저항 등 전문 용어의 표기를 확인하세요.\n\n"
        "[Translation Rules]\n한국어 강의를 자연스러운 영어로 번역하세요.\n수식·단위·전문 용어는 정확하게 유지하세요.\n\n"
        "[Course]\n전기 회로\n\n[Terminology]\n전압 = voltage\n전류 = current\n저항 = resistance\n옴의 법칙 = Ohm's law\n")
(OUT / "example-textbook.txt").write_text(BOOK, encoding="utf-8")
MODELS = [{"model": "gpt-6.1-sol", "displayName": "GPT-6.1-Sol", "isDefault": True,
           "defaultReasoningEffort": "low", "supportedReasoningEfforts": [
               {"reasoningEffort": effort} for effort in ["low", "medium", "high", "xhigh", "max", "ultra"]]}]


def rect(window, widget):
    point = widget.mapTo(window, QPoint(0, 0))
    return [point.x(), point.y(), widget.width(), widget.height()]


def capture(name, window, targets):
    app.processEvents()
    window.grab().save(str(OUT / "raw" / f"{name}.png"))
    return {"size": [window.width(), window.height()],
            "targets": {label: rect(window, widget) for label, widget in targets.items()}}


def lecture_frame():
    frame = QImage(1280, 720, QImage.Format.Format_ARGB32)
    frame.fill(QColor("#f5f7fa"))
    painter = QPainter(frame)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(0, 0, 1280, 95, QColor("#20334d"))
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Malgun Gothic", 25, QFont.Weight.Bold))
    painter.drawText(55, 62, "예제 강의 01  |  전기 회로")
    painter.setPen(QColor("#20334d"))
    painter.setFont(QFont("Malgun Gothic", 34, QFont.Weight.Bold))
    painter.drawText(QRectF(0, 125, 1280, 90), Qt.AlignmentFlag.AlignCenter, "옴의 법칙 · Ohm’s law")
    painter.setFont(QFont("Arial", 80, QFont.Weight.Bold))
    painter.drawText(QRectF(0, 260, 1280, 130), Qt.AlignmentFlag.AlignCenter, "V = I × R")
    painter.setFont(QFont("Malgun Gothic", 22))
    painter.drawText(QRectF(0, 440, 1280, 80), Qt.AlignmentFlag.AlignCenter,
                     "전압 (V)   =   전류 (A)   ×   저항 (Ω)")
    painter.setPen(QColor("#667388"))
    painter.setFont(QFont("Malgun Gothic", 13))
    painter.drawText(55, 665, "사용법 안내를 위한 예시 화면")
    painter.end()
    return QVideoFrame(frame)


app = QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/malgun.ttf")
app.setFont(QFont("Malgun Gothic", 9))
main = MyApp()
main.resize(1560, 1200)
main.workspace_splitter.setSizes([1110, 450])
main.preview_splitter.setSizes([910, 210])
main.show()
panel = main.pipeline_panel
panel.load_textbook(OUT / "example-textbook.txt")
panel.video_path = OUT / "example-lecture.mp4"
panel.video_field.setText("예제 강의.mp4")
panel.textbook_field.setText("example-textbook.txt")
panel._apply_codex_models(MODELS)
panel.transcription_backend_combo.setCurrentIndex(1)
panel.translation_backend_combo.setCurrentIndex(1)
panel.key_field.setText("secrets/openai_api_key.txt")
panel.output_field.setText("output_runs/")
panel._update_ready()
panel.folder_button.setEnabled(True)
panel.progress.setValue(4)
panel.status.setText("[5/5] 자막 영상 생성 — 예시")
panel.log.setPlainText("[1/5] 오디오 추출 완료\n[2/5] 한국어 전사 완료\n[3/5] 영어 번역 완료\n[4/5] SRT 생성 완료\n미리보기 자막을 불러왔습니다.\n[5/5] 자막 MP4 생성 중… (예시)")
player = main.video_player
player.video_widget.video_item.videoSink().setVideoFrame(lecture_frame())
player.video_widget.set_caption("Voltage is the product of current and resistance.")
player.play_button.setEnabled(True)
player.subtitle_checkbox.setEnabled(True)
player.time_label.setText("03:05 / 12:30")
player.wave_visualizer.set_duration(750000)
player.wave_visualizer.set_waveform([0.15 + 0.65 * abs(math.sin(i * 0.19) * math.cos(i * 0.043)) for i in range(700)])
player.wave_visualizer.set_position(185000)
app.processEvents()
metadata = {"01-main": capture("01-main", main, {
    "영상 미리보기": player.video_widget,
    "재생 / 일시정지": player.play_button,
    "구간 이동": player.wave_visualizer,
    "소프트 자막 켜기 / 끄기": player.subtitle_checkbox,
    "영상 선택": panel.video_button,
    "텍스트북 불러오기": panel.textbook_button,
    "과목 선택": panel.course_combo,
    "전사 방식 및 로컬 모델": panel.local_model_combo,
    "번역 방식": panel.translation_backend_combo,
    "Codex 모델 / 추론 수준": panel.codex_model_combo,
    "파이프라인 실행": panel.run_button,
    "결과 폴더 열기": panel.folder_button,
    "진행 상태 / 로그": panel.console,
})}

editor_window = TextbookEditorWindow(TextbookRepository(OUT / "example-textbook.txt"))
editor_window.setStyleSheet(main.styleSheet())
editor_window.resize(980, 900)
editor_window.show()
editor = editor_window.editor
editor.path_display.setText("example-textbook.txt")
editor.status.setText("셀을 더블클릭하여 수정하세요. 변경한 내용은 Save로 저장합니다.")
metadata["02-textbook"] = capture("02-textbook", editor_window, {
    "텍스트북 열기": editor.open_button,
    "PPT 자동 생성": editor.auto_button,
    "파일 저장": editor.save_button,
    "공통 규칙": editor.rule_editors["common_rules"],
    "전사 규칙": editor.rule_editors["whisper_rules"],
    "번역 규칙": editor.rule_editors["translation_rules"],
    "과목 선택": editor.course_selector,
    "과목 추가": editor.add_course_button,
    "단어 편집": editor.table,
    "단어 추가": editor.add_term_button,
    "선택 단어 삭제": editor.remove_term_button,
})

document = TextbookDocument(Textbook.parse(BOOK))
dialog = AutoTextbookDialog(document, 0)
dialog.setStyleSheet(main.styleSheet())
dialog.resize(1020, 960)
dialog._models_loaded(MODELS)
dialog.backend_combo.setCurrentIndex(1)
dialog.key_field.setText("secrets/openai_api_key.txt")
for name in ["01_회로의_기초.pptx", "02_저항과_옴의_법칙.ppt"]:
    dialog.files.addItem(QListWidgetItem(name))
dialog.target_course = "전기 회로"
dialog._show_candidates([
    TermCandidate("직렬 회로", "series circuit", "01_회로의_기초.pptx · 3번 슬라이드"),
    TermCandidate("병렬 회로", "parallel circuit", "01_회로의_기초.pptx · 5번 슬라이드"),
    TermCandidate("전압", "voltage", "02_저항과_옴의_법칙.ppt · 2번 슬라이드"),
    TermCandidate("전력", "electric power", "02_저항과_옴의_법칙.ppt · 6번 슬라이드"),
])
dialog.apply_button.setEnabled(True)
dialog.log.setPlainText("예시 결과입니다. 실제 요청을 실행하지 않았습니다.\nPPT 읽기 → 단어장 생성 → 후보 검토 → 편집기에 추가")
dialog.show()
metadata["03-auto"] = capture("03-auto", dialog, {
    "PPT 드래그 / 복수 파일 목록": dialog.files,
    "PPT 파일 열기": dialog.open_button,
    "선택 파일 제거": dialog.remove_button,
    "기존 과목 / 새 과목명": dialog.course_combo,
    "OpenAI API / Codex CLI": dialog.backend_combo,
    "API 키 파일": dialog.key_field,
    "Codex 모델 / 추론 수준": dialog.model_combo,
    "단어장 생성": dialog.generate_button,
    "후보 선택 / 용어 수정 / 출처": dialog.table,
    "진행 로그": dialog.log,
    "편집기에 추가 (저장은 Save)": dialog.apply_button,
})
(OUT / "capture-targets.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(metadata, ensure_ascii=False))
dialog.close()
editor_window.close()
main.close()
