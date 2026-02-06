"""パルス幅掃引 CLI エントリポイント.

Usage:
    python -m pulse_control.main [config.toml]
"""

from __future__ import annotations

import sys
from pathlib import Path

from config import SweepConfig
from core import PulseInstrument, run_sweep, save_results


def main(config_path: str | None = None) -> None:
    # 設定ファイルのパス
    if config_path is None:
        if len(sys.argv) > 1:
            config_path = sys.argv[1]
        else:
            config_path = str(Path(__file__).parent / "sweep_config.toml")

    print(f"設定ファイル: {config_path}")
    config = SweepConfig.from_toml(config_path)

    # バリデーション
    errors = config.validate()
    if errors:
        print("設定エラー:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("設定OK.")
    print(f"  VISA: {config.visa_address}")
    print(f"  V_on={config.v_on} V, V_off={config.v_off} V")
    print(
        f"  幅: {config.width_start} → {config.width_stop} (step {config.width_step}) s"
    )
    print(f"  center_delay={config.center_delay} s")

    # 接続チェック
    print("接続チェック中...")
    try:
        idn = PulseInstrument.check_connection(config.visa_address)
        print(f"  OK: {idn}")
    except Exception as exc:
        print(f"  接続失敗: {exc}")
        sys.exit(1)

    # 装置接続・実行
    print("掃引を開始します...")
    instrument = PulseInstrument(config.visa_address)
    try:
        instrument.setup(config)
        results = run_sweep(config, instrument)
        instrument.teardown()
    finally:
        instrument.close()

    # 結果保存
    save_results(results, config, config.output_dir)
    print(f"完了. 結果は {config.output_dir}/ に保存されました.")


if __name__ == "__main__":
    main()
