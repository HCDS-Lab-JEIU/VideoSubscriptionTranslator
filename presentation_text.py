"""Read slide text locally; legacy PPT is converted by installed PowerPoint."""

from dataclasses import dataclass
import base64
import os
from pathlib import Path, PurePosixPath
import posixpath
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


@dataclass(frozen=True)
class SlideText:
    file: str
    number: int
    text: str


def _xml(archive, name):
    info = archive.getinfo(name)
    if info.file_size > 8_000_000:
        raise ValueError("슬라이드 XML이 너무 큽니다. PPT를 나누어 추가하세요.")
    data = archive.read(info)
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("지원하지 않는 XML 선언이 포함된 PPT입니다.")
    return ET.fromstring(data)


def _target(base, target):
    name = posixpath.normpath(posixpath.join(base, target)) if not target.startswith("/") else target[1:]
    if ".." in PurePosixPath(name).parts or not name.startswith("ppt/"):
        raise ValueError("PPT 내부 슬라이드 경로가 올바르지 않습니다.")
    return name


def _read_pptx(path, source_name):
    with ZipFile(path) as archive:
        if len(archive.infolist()) > 20000:
            raise ValueError("PPT 내부 항목이 너무 많습니다. 파일을 나누어 추가하세요.")
        presentation = _xml(archive, "ppt/presentation.xml")
        rels = _xml(archive, "ppt/_rels/presentation.xml.rels")
        targets = {rel.attrib["Id"]: _target("ppt", rel.attrib["Target"])
                   for rel in rels if rel.attrib.get("Type", "").endswith("/slide")
                   and rel.attrib.get("TargetMode") != "External"}
        slides = []
        # Presentation order can differ from slide1.xml, slide2.xml order.
        for node in presentation.iter():
            if node.tag.rsplit("}", 1)[-1] != "sldId":
                continue
            rel_id = next((value for key, value in node.attrib.items() if key.endswith("}id")), None)
            root = _xml(archive, targets[rel_id])
            paragraphs = []
            for paragraph in root.iter():
                if paragraph.tag.rsplit("}", 1)[-1] == "p":
                    text = "".join(element.text or "" for element in paragraph.iter()
                                   if element.tag.rsplit("}", 1)[-1] == "t").strip()
                    if text:
                        paragraphs.append(text)
            slides.append(SlideText(source_name, len(slides) + 1, "\n".join(paragraphs)))
        if not slides:
            raise ValueError("슬라이드가 없는 PPT입니다.")
        return slides


def _convert_ppt(source, destination):
    if os.name != "nt":
        raise ValueError("구형 .ppt는 Windows PowerPoint가 필요합니다. .pptx로 저장해 추가하세요.")
    # Pass paths through environment, never interpolate them into PowerShell code.
    script = r'''
$ErrorActionPreference = 'Stop'
$app = $null; $deck = $null; $security = $null
try {
    $app = New-Object -ComObject PowerPoint.Application
    $security = $app.AutomationSecurity
    $app.AutomationSecurity = 3
    $deck = $app.Presentations.Open($env:TEXTBOOK_PPT_SOURCE, -1, 0, 0)
    $deck.SaveAs($env:TEXTBOOK_PPT_DESTINATION, 24)
} finally {
    if ($null -ne $deck) { $deck.Close(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($deck) }
    if ($null -ne $app) {
        if ($null -ne $security) { $app.AutomationSecurity = $security }
        if ($app.Presentations.Count -eq 0) { $app.Quit() }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)
    }
}
'''
    env = os.environ.copy()
    env.update(TEXTBOOK_PPT_SOURCE=str(source), TEXTBOOK_PPT_DESTINATION=str(destination))
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(script.encode("utf-16-le")).decode("ascii")],
            env=env, capture_output=True, timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("PPT 변환을 완료하지 못했습니다. PowerPoint에서 .pptx로 저장한 뒤 추가하세요.") from None
    if result.returncode or not destination.is_file():
        raise ValueError("구형 .ppt 변환에는 설치된 PowerPoint가 필요합니다. 암호·보호된 파일은 .pptx로 저장해 추가하세요.")


def read_presentation(path):
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in {".ppt", ".pptx"}:
        raise ValueError("존재하는 .ppt 또는 .pptx 파일을 선택하세요.")
    try:
        if source.suffix.lower() == ".ppt":
            with tempfile.TemporaryDirectory(prefix="textbook-ppt-") as folder:
                converted = Path(folder) / "slides.pptx"
                _convert_ppt(source, converted)
                return _read_pptx(converted, source.name)
        return _read_pptx(source, source.name)
    except (BadZipFile, KeyError, ET.ParseError, RuntimeError):
        raise ValueError(f"PPT를 읽지 못했습니다: {source.name}. 손상·암호화 여부를 확인하세요.") from None
