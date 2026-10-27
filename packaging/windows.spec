# Build with the translator environment; see build_windows.ps1.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "__main__.py"), "."),
        (str(root / "qtTest" / "github_dark_replica.qss"), "qtTest"),
    ] + collect_data_files("imageio_ffmpeg"),
    hiddenimports=["pipeline"],
    excludes=["PyQt5", "PySide2", "PySide6", "IPython", "matplotlib", "scipy", "pandas"],
)
# The CLI is bundled as cli.py to avoid colliding with the bootloader entry.
a.datas = [("cli.py" if dest == "__main__.py" else dest, src, kind)
           for dest, src, kind in a.datas]
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="VideoSubtitleTranslator", console=False, upx=False)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="VideoSubtitleTranslator-CLI", console=True, upx=False)
bundle = COLLECT(gui, cli, a.binaries, a.datas,
                 name="VideoSubtitleTranslator", upx=False)
