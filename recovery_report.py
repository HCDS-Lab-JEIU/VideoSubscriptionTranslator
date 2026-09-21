"""파일 교체가 잠시 차단되어도 완성된 복구 기록을 보존합니다."""

import json
from pathlib import Path
import tempfile
import time


class RecoveryReportWriter:
    def __init__(self, path: Path):
        self.path = path
        self.latest_path = path
        self.snapshot_mode = False

    def __call__(self, events):
        return self.write_data({"events": events})

    def write_data(self, data):
        content = json.dumps(data, ensure_ascii=False, indent=2)
        # 매 저장마다 별도 파일을 사용하므로 이전 실패의 tmp를 덮어쓰지 않습니다.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                         prefix=self.path.stem + ".snapshot-", suffix=".json",
                                         delete=False) as output:
            snapshot = Path(output.name)
            output.write(content)
        self.latest_path = snapshot
        if not self.snapshot_mode:
            for attempt in range(4):
                try:
                    snapshot.replace(self.path)
                    self.latest_path = self.path
                    return self.path
                except PermissionError:
                    if attempt < 3:
                        time.sleep((0.05, 0.15, 0.3)[attempt])
            # 원본을 지우거나 직접 덮어쓰지 않습니다. 저장된 스냅샷을 정식 대체 기록으로 사용합니다.
            self.snapshot_mode = True
            print("복구 기록 파일을 교체할 수 없어 별도 JSON으로 보관합니다. 전사를 계속합니다.", flush=True)
        print(f"최신 복구 기록: {snapshot}", flush=True)
        return snapshot
