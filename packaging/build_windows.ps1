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
    & $PythonExe -c "import sys; from pathlib import Path; assert Path(sys.prefix).name == 'translator', 'Use the translator environment'; import PyInstaller, PyQt6, openai, imageio_ffmpeg, mutagen"
    if ($LASTEXITCODE -ne 0) { throw 'Install packaging/requirements-build.txt in translator first.' }
    & $PythonExe -m PyInstaller --clean --noconfirm --distpath "$PSScriptRoot/dist" --workpath "$PSScriptRoot/build" "$PSScriptRoot/windows.spec"
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    $Bundle = Join-Path $PSScriptRoot 'dist/VideoSubtitleTranslator'
    New-Item -ItemType Directory -Force -Path "$Bundle/secrets" | Out-Null
    Copy-Item -LiteralPath "$PSScriptRoot/textbook.example.txt" -Destination "$Bundle/secrets/textbook.txt"
    Copy-Item -LiteralPath "$PSScriptRoot/USAGE.txt" -Destination "$Bundle/USAGE.txt"
    & $PythonExe "$PSScriptRoot/smoke_test.py" $Bundle
    if ($LASTEXITCODE -ne 0) { throw 'Packaged application smoke test failed.' }
    Compress-Archive -Path $Bundle -DestinationPath "$PSScriptRoot/VideoSubtitleTranslator-windows-x64.zip" -Force
    Write-Host "Built: $PSScriptRoot/VideoSubtitleTranslator-windows-x64.zip"
} finally {
    $env:PATH = $PreviousPath
    Pop-Location
}
