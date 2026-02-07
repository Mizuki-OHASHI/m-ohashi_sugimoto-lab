"""ロギング初期化モジュール.

Usage:
    from log_setup import setup_logging
    setup_logging()

    from logging import getLogger
    logger = getLogger(__name__)
"""

from __future__ import annotations

from datetime import datetime
from logging import DEBUG, FileHandler, Formatter, StreamHandler, getLogger
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s %(message)s"


def setup_logging() -> None:
    """ルートロガーに FileHandler + StreamHandler を設定する.

    呼び出すたびに新しいタイムスタンプ付きログファイルが作成される。
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = LOG_DIR / f"{timestamp}.log"

    formatter = Formatter(LOG_FORMAT)

    file_handler = FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(DEBUG)
    file_handler.setFormatter(formatter)

    stream_handler = StreamHandler()
    stream_handler.setLevel(DEBUG)
    stream_handler.setFormatter(formatter)

    root = getLogger()
    root.setLevel(DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    getLogger(__name__).info("Logging started: %s", log_file)
