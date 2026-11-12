"""오래 걸리는 요청의 콘솔 대기 상태 표시."""

from contextlib import contextmanager
from threading import Event, Thread
from time import monotonic


@contextmanager
def waiting_for_response(provider="OpenAI"):
    stopped = Event()
    started_at = monotonic()
    print(f"{provider} 응답을 기다리는 중...", flush=True)

    def report():
        while not stopped.wait(5):
            elapsed = int(monotonic() - started_at)
            print(f"{provider} 응답을 기다리는 중... ({elapsed}초 경과)", flush=True)

    reporter = Thread(target=report, daemon=True)
    reporter.start()
    try:
        yield
    finally:
        # 성공, 오류, 사용자 중단 모두에서 대기 메시지를 종료합니다.
        stopped.set()
        reporter.join()
