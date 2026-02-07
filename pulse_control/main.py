"""パルス幅掃引 CLI エントリポイント.

Usage:
    python -m pulse_control.main [config.toml]
"""

from __future__ import annotations

import sys
from logging import getLogger
from pathlib import Path

from config import SweepConfig
from core import PulseInstrument, run_sweep, save_results
from log_setup import setup_logging

logger = getLogger(__name__)


def main(config_path: str | None = None) -> None:
    setup_logging()

    # 設定ファイルのパス
    if config_path is None:
        if len(sys.argv) > 1:
            config_path = sys.argv[1]
        else:
            config_path = str(Path(__file__).parent / "sweep_config.toml")

    logger.info("設定ファイル: %s", config_path)
    config = SweepConfig.from_toml(config_path)

    # バリデーション
    errors = config.validate()
    if errors:
        logger.error("設定エラー:")
        for e in errors:
            logger.error("  - %s", e)
        sys.exit(1)

    logger.info("設定OK.")
    logger.info("  VISA: %s", config.visa_address)
    logger.info("  V_on=%s V, V_off=%s V", config.v_on, config.v_off)
    logger.info(
        "  幅: %s → %s (step %s) s",
        config.width_start, config.width_stop, config.width_step,
    )
    logger.info("  center_delay=%s s", config.center_delay)

    # 接続チェック
    logger.info("接続チェック中...")
    try:
        idn = PulseInstrument.check_connection(config.visa_address)
        logger.info("  OK: %s", idn)
    except Exception as exc:
        logger.exception("接続失敗: %s", exc)
        sys.exit(1)

    # 装置接続・実行
    logger.info("掃引を開始します...")
    instrument = PulseInstrument(config.visa_address)
    try:
        instrument.setup(config)
        results = run_sweep(config, instrument)
        instrument.teardown()
    finally:
        instrument.close()

    # 結果保存
    save_results(results, config, config.output_dir)
    logger.info("完了. 結果は %s/ に保存されました.", config.output_dir)


if __name__ == "__main__":
    main()
