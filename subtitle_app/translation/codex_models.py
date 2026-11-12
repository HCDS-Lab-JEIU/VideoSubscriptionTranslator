"""Discover picker-visible models through the official Codex app-server protocol."""

import json
import subprocess
import tempfile
from threading import Event, Timer


def normalize_models(items):
    models = []
    for item in items:
        if not isinstance(item, dict) or item.get("hidden"):
            continue
        model = item.get("model")
        efforts = [option for option in item.get("supportedReasoningEfforts", [])
                   if isinstance(option, dict) and isinstance(option.get("reasoningEffort"), str)
                   and option["reasoningEffort"]]
        if not isinstance(model, str) or not model or not efforts:
            continue
        default = item.get("defaultReasoningEffort")
        if default not in [option["reasoningEffort"] for option in efforts]:
            default = efforts[0]["reasoningEffort"]
        models.append({"model": model, "displayName": item.get("displayName") or model,
                       "isDefault": bool(item.get("isDefault")), "defaultReasoningEffort": default,
                       "supportedReasoningEfforts": efforts})
    if not models:
        raise RuntimeError("선택 가능한 Codex 모델을 받지 못했습니다. CLI 로그인과 연결을 확인하세요.")
    return models


def select_model(models, model=None, effort=None):
    selected = next((entry for entry in models if entry["model"] == model), None) if model else next(
        (entry for entry in models if entry["isDefault"]), models[0])
    if selected is None:
        raise ValueError(f"Codex 모델 목록에 없는 모델입니다: {model}")
    effort = effort or selected["defaultReasoningEffort"]
    if effort not in [option["reasoningEffort"] for option in selected["supportedReasoningEfforts"]]:
        raise ValueError(f"{selected['model']}에서 지원하지 않는 추론 수준입니다: {effort}")
    return selected["model"], effort


def list_codex_models(executable=None, *, timeout=30):
    from subtitle_app.translation.codex_translator import codex_command, _codex_env

    with tempfile.TemporaryDirectory(prefix="subtitle-models-") as folder:
        process = subprocess.Popen(
            codex_command(executable) + ["app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=folder, env=_codex_env(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        expired = Event()
        def stop():
            expired.set()
            if process.poll() is None:
                process.kill()
        timer = Timer(timeout, stop)
        timer.daemon = True
        timer.start()
        def send(message):
            process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            process.stdin.flush()
        def response(request_id):
            while True:
                line = process.stdout.readline()
                if not line:
                    raise RuntimeError("Codex 모델 목록 조회 시간이 초과됐습니다." if expired.is_set()
                                       else "Codex 모델 목록을 불러오지 못했습니다. CLI 로그인·버전을 확인하세요.")
                message = json.loads(line)
                if message.get("id") == request_id:
                    if "error" in message or not isinstance(message.get("result"), dict):
                        raise RuntimeError("Codex가 모델 목록 요청을 처리하지 못했습니다.")
                    return message["result"]
        try:
            send({"id": 0, "method": "initialize", "params": {
                "clientInfo": {"name": "video_subtitle_translator", "version": "1.0.0"}}})
            response(0)
            send({"method": "initialized"})
            items, cursor, seen = [], None, set()
            for request_id in range(1, 101):
                send({"id": request_id, "method": "model/list", "params": {
                    "limit": 100, "includeHidden": False, "cursor": cursor}})
                page = response(request_id)
                if not isinstance(page.get("data"), list):
                    raise RuntimeError("Codex 모델 목록 형식이 올바르지 않습니다.")
                items.extend(page["data"])
                cursor = page.get("nextCursor")
                if not cursor:
                    return normalize_models(items)
                if cursor in seen:
                    break
                seen.add(cursor)
            raise RuntimeError("Codex 모델 목록 페이지를 모두 읽지 못했습니다.")
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise RuntimeError("Codex 모델 목록을 읽지 못했습니다. 연결과 CLI 버전을 확인하세요.") from None
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdin.close()
            process.stdout.close()
