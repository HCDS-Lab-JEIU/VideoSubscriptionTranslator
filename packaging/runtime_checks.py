"""Offline checks executed inside the frozen runtime, with no developer PATH."""


def check_runtime():
    import ctypes
    import importlib.util
    import json
    from pathlib import Path
    import tempfile
    from zipfile import ZipFile

    import ctranslate2
    import numpy as np
    import tokenizers
    from faster_whisper.vad import get_vad_model
    from subtitle_app.transcription.local_transcriber import configure_cuda_libraries
    from subtitle_app.textbook.presentation_text import read_presentation
    from PyQt6.QtWidgets import QApplication
    from subtitle_app.ui.main_window import MyApp
    from subtitle_app.ui.textbook_editor.auto_dialog import AutoTextbookDialog
    from subtitle_app.ui.textbook_editor.data import TextbookDocument
    from subtitle_app.textbook.document import Textbook

    assert "int8" in ctranslate2.get_supported_compute_types("cpu")
    assert tokenizers.__version__
    get_vad_model()(np.zeros(16384, dtype=np.float32))
    configure_cuda_libraries()
    for package, filename in (("nvidia.cublas", "cublas64_12.dll"),
                              ("nvidia.cudnn", "cudnn64_9.dll"),
                              ("nvidia.cuda_nvrtc", "nvrtc64_120_0.dll")):
        spec = importlib.util.find_spec(package)
        locations = list(spec.submodule_search_locations)
        candidates = [path for location in locations for path in Path(location).rglob(filename)]
        assert candidates, f"Missing CUDA runtime: {filename}"
        ctypes.WinDLL(str(candidates[0]))
    app = QApplication([])
    window = MyApp()
    assert window.STYLESHEET_PATH.is_file(), "Missing bundled UI stylesheet"
    assert window.styleSheet(), "UI stylesheet was not loaded"
    window.open_textbook_editor()
    dialog = AutoTextbookDialog(TextbookDocument(Textbook([])), parent=window)
    dialog.show()
    with tempfile.TemporaryDirectory(prefix="frozen-features-") as folder:
        root = Path(folder)
        pptx = root / "example.pptx"
        with ZipFile(pptx, "w") as archive:
            archive.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="urn:p" xmlns:r="urn:r"><p:sldId r:id="r1"/></p:presentation>')
            archive.writestr("ppt/_rels/presentation.xml.rels", '<Relationships><Relationship Id="r1" Type="urn/slide" Target="slides/slide1.xml"/></Relationships>')
            archive.writestr("ppt/slides/slide1.xml", '<a:p xmlns:a="urn:a"><a:r><a:t>Voltage</a:t></a:r></a:p>')
        assert read_presentation(pptx)[0].text == "Voltage"
        dialog.add_files([pptx])
        assert dialog.files.count() == 1
        srt = root / "preview.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nPreview\n\n", encoding="utf-8")
        player = window.video_player
        player.current_path = root / "video.mp4"
        assert player.load_subtitles(player.current_path, srt)
        player._update_position(1000)
        assert player.video_widget.caption.toPlainText() == "Preview"
        app.processEvents()
    dialog.close()
    window.close()
    print(json.dumps({"local_cpu": True, "vad": True, "cuda_dlls": True,
                      "pptx": True, "auto_dialog": True, "subtitle_preview": True}))
