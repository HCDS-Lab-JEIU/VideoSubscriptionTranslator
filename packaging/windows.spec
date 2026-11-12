# Build with the translator environment; see build_windows.ps1.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

root = Path(SPECPATH).parent
cuda_packages = ["nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"]
a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root), str(root / "packaging")],
    binaries=collect_dynamic_libs("ctranslate2") + [
        entry for package in cuda_packages for entry in collect_dynamic_libs(package)
    ],
    datas=[
        (str(root / "subtitle_app" / "ui" / "resources" / "github_dark_replica.qss"), "subtitle_app/ui/resources"),
    ] + collect_data_files("imageio_ffmpeg") + collect_data_files("faster_whisper")
      + copy_metadata("faster-whisper") + copy_metadata("huggingface-hub"),
    hiddenimports=["faster_whisper", "tokenizers", "onnxruntime"] + cuda_packages,
    excludes=["PyQt5", "PySide2", "PySide6", "IPython", "matplotlib", "scipy", "pandas",
              "torch", "tensorflow", "transformers", "ctranslate2.converters", "ctranslate2.specs"],
)
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="VideoSubtitleTranslator", console=False, upx=False)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="VideoSubtitleTranslator-CLI", console=True, upx=False)
bundle = COLLECT(gui, cli, a.binaries, a.datas,
                 name="VideoSubtitleTranslator", upx=False)
