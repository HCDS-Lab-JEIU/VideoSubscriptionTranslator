param(
    [string]$PythonExe = 'D:\Miniconda3\envs\translator\python.exe'
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "translator interpreter not found: $PythonExe"
}
Push-Location $ProjectRoot
$PreviousPath = $env:PATH
try {
    # Conda native dependencies must be visible to PyInstaller's DLL discovery.
    $CondaLibraryBin = Join-Path (Split-Path -Parent $PythonExe) 'Library\bin'
    if (-not (Test-Path -LiteralPath $CondaLibraryBin)) {
        throw "Conda Library/bin not found: $CondaLibraryBin"
    }
    $env:PATH = "$CondaLibraryBin;$PreviousPath"
    & $PythonExe -c "import sys; from pathlib import Path; assert Path(sys.prefix).name == 'translator', 'Use the translator environment'; import PyInstaller, PyQt6, openai, imageio_ffmpeg, mutagen, faster_whisper, ctranslate2, nvidia.cublas, nvidia.cudnn, nvidia.cuda_nvrtc"
    if ($LASTEXITCODE -ne 0) { throw 'Install packaging/requirements-build.txt in translator first.' }
    & $PythonExe -m PyInstaller --clean --noconfirm --distpath "$PSScriptRoot/dist" --workpath "$PSScriptRoot/build" "$PSScriptRoot/windows.spec"
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    $Bundle = Join-Path $PSScriptRoot 'dist/VideoSubtitleTranslator'
    New-Item -ItemType Directory -Force -Path "$Bundle/secrets" | Out-Null
    Copy-Item -LiteralPath "$PSScriptRoot/textbook.example.txt" -Destination "$Bundle/secrets/textbook.txt"
    Copy-Item -LiteralPath "$PSScriptRoot/USAGE.txt" -Destination "$Bundle/USAGE.txt"
    Copy-Item -LiteralPath "$ProjectRoot/README.md" -Destination "$Bundle/README.md"
    New-Item -ItemType Directory -Force -Path "$Bundle/docs" | Out-Null
    Copy-Item -LiteralPath "$ProjectRoot/docs/user-guide" -Destination "$Bundle/docs/user-guide" -Recurse -Force
    Copy-Item -LiteralPath "$ProjectRoot/docs/user-guide.zip" -Destination "$Bundle/docs/user-guide.zip"
    $ReleaseVersion = & $PythonExe -c "from app_version import __version__; print(__version__)"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read release version.' }
    $ReleaseVersion | Set-Content -Encoding UTF8 -LiteralPath "$Bundle/VERSION.txt"
    & $PythonExe "$PSScriptRoot/collect_licenses.py" $Bundle
    if ($LASTEXITCODE -ne 0) { throw 'Cannot collect third-party licenses.' }
    & $PythonExe "$PSScriptRoot/smoke_test.py" $Bundle
    if ($LASTEXITCODE -ne 0) { throw 'Packaged application smoke test failed.' }
    $Archive = "$PSScriptRoot/VideoSubtitleTranslator-v$ReleaseVersion-windows-x64.zip"
    Compress-Archive -Path $Bundle -DestinationPath $Archive -Force
    $ArchiveHash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    "$ArchiveHash  $(Split-Path -Leaf $Archive)" | Set-Content -Encoding ASCII -LiteralPath "$PSScriptRoot/SHA256SUMS.txt"
    Write-Host "Built: $Archive"
} finally {
    $env:PATH = $PreviousPath
    Pop-Location
}
