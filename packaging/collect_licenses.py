"""Include the installed redistributable wheels' license files in the bundle."""

from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys


def collect_licenses(bundle):
    root = Path(bundle) / "THIRD_PARTY_LICENSES"
    packages = ("nvidia-cublas-cu12", "nvidia-cudnn-cu12", "nvidia-cuda-nvrtc-cu12",
                "faster-whisper", "ctranslate2", "onnxruntime", "av", "tokenizers",
                "huggingface-hub", "numpy", "PyQt6", "PyQt6-Qt6", "openai", "imageio-ffmpeg")
    versions = []
    for name in packages:
        package = distribution(name)
        versions.append(f"{name}=={package.version}")
        for entry in package.files or []:
            if (any(word in entry.name.casefold() for word in ("license", "copying", "notice"))
                    and package.locate_file(entry).is_file()):
                folder = root / name
                folder.mkdir(parents=True, exist_ok=True)
                shutil.copy2(package.locate_file(entry), folder / entry.name)
    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSIONS.txt").write_text("\n".join(versions) + "\n", encoding="utf-8")


if __name__ == "__main__":
    collect_licenses(sys.argv[1])
