"""パルス幅掃引の設定管理モジュール（Agilent 81180A AWG 用）."""

from __future__ import annotations

from dataclasses import dataclass, fields
from logging import getLogger
from pathlib import Path

import toml

logger = getLogger(__name__)


DEFAULT_VISA_ADDRESS = "TCPIP0::192.168.0.251::5025::SOCKET"
# NOTE: TCPIP0::[IPアドレス]::5025::SOCKET の形式で指定
# - IPアドレスは装置の Utility > Remote Interface > LAN で確認
# - LAN が繋がっているかを確認したい場合には PowerShell で ping [IPアドレス] を実行


@dataclass
class SweepConfig:
    """パルス幅掃引の設定（Agilent 81180A AWG 用）."""

    # 接続
    visa_address: str = DEFAULT_VISA_ADDRESS

    # パルス形状
    v_on: float = 0.5  # パルスON時の電圧 [V]
    v_off: float = 0.0  # パルスOFF時の電圧（ベース） [V]

    # 掃引パラメータ
    width_start: float = 0.001  # パルス幅の開始値 [s]
    width_stop: float = 0.005  # パルス幅の終了値 [s]
    width_step: float = 0.001  # パルス幅のステップ [s]

    # AWG パラメータ
    frequency: float = 1000.0  # 周波数 [Hz]（固定。duty で幅を制御）
    trigger_delay: int = 0  # トリガー遅延 [サンプルポイント数]（8 の倍数）
    wait_time: float = 1.0  # 掃引ステップ間の待ち時間 [s]

    # 表示
    time_unit: str = "s"  # 時間の表示単位（s / ms / μs / ns）

    @property
    def period(self) -> float:
        """周期 [s] = 1 / frequency."""
        return 1.0 / self.frequency

    @classmethod
    def from_toml(cls, path: str | Path) -> SweepConfig:
        """TOML ファイルから設定を読み込む.

        [awg] セクションに frequency または period のどちらかを記載可能。
        両方ある場合は frequency が優先される。
        """
        logger.info("TOML 読み込み: %s", path)
        data = toml.load(path)
        # フラットに展開（セクション付き TOML に対応）
        flat: dict = {}
        for value in data.values():
            if isinstance(value, dict):
                flat.update(value)
            else:
                flat[str(value)] = value
        # period → frequency 変換
        if "period" in flat and "frequency" not in flat:
            flat["frequency"] = 1.0 / flat.pop("period")
        elif "period" in flat:
            flat.pop("period")  # frequency が優先
        # dataclass のフィールド名のみ取り出す
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in flat.items() if k in valid_keys}
        return cls(**filtered)

    def to_toml(self, path: str | Path) -> None:
        """TOML ファイルへ書き出す（frequency と period の両方を記載）."""
        logger.info("TOML 書き出し: %s", path)
        data = {
            "connection": {
                "visa_address": self.visa_address,
            },
            "pulse": {
                "v_on": self.v_on,
                "v_off": self.v_off,
            },
            "sweep": {
                "width_start": self.width_start,
                "width_stop": self.width_stop,
                "width_step": self.width_step,
                "wait_time": self.wait_time,
            },
            "awg": {
                "frequency": self.frequency,
                "period": self.period,
                "trigger_delay": self.trigger_delay,
            },
            "display": {
                "time_unit": self.time_unit,
            },
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            toml.dump(data, f)

    def validate(self) -> list[str]:
        """パラメータの整合性チェック. エラーメッセージのリストを返す（空なら OK）."""
        logger.info("バリデーション実行")
        errors: list[str] = []

        if self.width_start <= 0:
            errors.append("width_start は正の値でなければなりません")
        if self.width_stop <= 0:
            errors.append("width_stop は正の値でなければなりません")
        if self.width_step <= 0:
            errors.append("width_step は正の値でなければなりません")

        if self.frequency <= 0:
            errors.append("frequency は正の値でなければなりません")

        if self.trigger_delay < 0:
            errors.append("trigger_delay は 0 以上でなければなりません")
        if self.trigger_delay % 8 != 0:
            errors.append("trigger_delay は 8 の倍数でなければなりません")

        if self.wait_time < 0:
            errors.append("wait_time は 0 以上でなければなりません")

        # duty cycle の範囲チェック（VBA UpdateSQR: 0.1〜99.9%）
        for width in [self.width_start, self.width_stop]:
            dcycle = width * self.frequency * 100
            if dcycle < 0.1 or dcycle > 99.9:
                errors.append(
                    f"パルス幅 {width:.6f} s での duty cycle = {dcycle:.2f}% "
                    "が範囲外です（0.1〜99.9%）"
                )

        # 振幅・オフセットの範囲チェック（VBA UpdateSQR と同じ制限値）
        ampl = (self.v_on - self.v_off) / 2
        if ampl < 0.05 or ampl > 2:
            errors.append(
                f"振幅 = {ampl:.4f} V が範囲外です（0.05〜2.0 V）"
            )
        offs = (self.v_on + self.v_off) / 4
        if abs(offs) > 1.5:
            errors.append(
                f"オフセット = {offs:.4f} V が範囲外です（-1.5〜1.5 V）"
            )

        for e in errors:
            logger.warning("バリデーションエラー: %s", e)

        return errors
