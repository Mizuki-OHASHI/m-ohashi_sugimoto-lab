"""パルス幅掃引の設定管理モジュール."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import toml


DEFAULT_VISA_ADDRESS = "TCPIP0::192.168.0.251::5025::SOCKET"
# NOTE: TCPIP0::[IPアドレス]::5025::SOCKET の形式で指定
# - IPアドレスは装置の Utility > Remote Interface > LAN で確認
# - LAN が繋がっているかを確認したい場合には PowerShell で ping [IPアドレス] を実行


@dataclass
class SweepConfig:
    """パルス幅掃引の設定."""

    # 接続
    visa_address: str = DEFAULT_VISA_ADDRESS

    # パルス形状
    v_on: float = 0.5  # パルスON時の電圧 [V]
    v_off: float = 0.0  # パルスOFF時の電圧（ベース） [V]

    # 掃引パラメータ
    center_delay: float = 0.005  # パルス中心のトリガーからの遅延 [s]
    width_start: float = 0.001  # パルス幅の開始値 [s]
    width_stop: float = 0.005  # パルス幅の終了値 [s]
    width_step: float = 0.001  # パルス幅のステップ [s]

    # 測定パラメータ
    trigger_count: int = 2  # トリガー回数（各幅での繰り返し数）
    trigger_time: float = 0.01  # トリガー間隔 [s]
    aperture_time: float = 0.0001  # アパーチャ時間 [s]
    sampling_points: int = 20  # サンプリング点数
    compliance_current: float = 0.1  # コンプライアンス電流 [A]

    # 出力
    output_dir: str = "results"

    @classmethod
    def from_toml(cls, path: str | Path) -> SweepConfig:
        """TOML ファイルから設定を読み込む."""
        data = toml.load(path)
        # フラットに展開（セクション付き TOML に対応）
        flat: dict = {}
        for value in data.values():
            if isinstance(value, dict):
                flat.update(value)
            else:
                flat[str(value)] = value
        # dataclass のフィールド名のみ取り出す
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in flat.items() if k in valid_keys}
        return cls(**filtered)

    def to_toml(self, path: str | Path) -> None:
        """TOML ファイルへ書き出す."""
        data = {
            "connection": {
                "visa_address": self.visa_address,
            },
            "pulse": {
                "v_on": self.v_on,
                "v_off": self.v_off,
            },
            "sweep": {
                "center_delay": self.center_delay,
                "width_start": self.width_start,
                "width_stop": self.width_stop,
                "width_step": self.width_step,
            },
            "measurement": {
                "trigger_count": self.trigger_count,
                "trigger_time": self.trigger_time,
                "aperture_time": self.aperture_time,
                "sampling_points": self.sampling_points,
                "compliance_current": self.compliance_current,
            },
            "output": {
                "output_dir": self.output_dir,
            },
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            toml.dump(data, f)

    def validate(self) -> list[str]:
        """パラメータの整合性チェック. エラーメッセージのリストを返す（空なら OK）."""
        errors: list[str] = []

        width_max = max(self.width_start, self.width_stop)

        if self.width_start <= 0:
            errors.append("width_start は正の値でなければなりません")
        if self.width_stop <= 0:
            errors.append("width_stop は正の値でなければなりません")
        if self.width_step <= 0:
            errors.append("width_step は正の値でなければなりません")

        min_delay = self.center_delay - width_max / 2
        if min_delay < 0:
            errors.append(
                f"center_delay - width_max/2 = {min_delay:.6f} s < 0: "
                "パルス遅延が負になります"
            )

        max_end = self.center_delay + width_max / 2
        if max_end > self.trigger_time:
            errors.append(
                f"center_delay + width_max/2 = {max_end:.6f} s > "
                f"trigger_time = {self.trigger_time:.6f} s: "
                "パルスがトリガー間隔を超えます"
            )

        if self.trigger_count < 1:
            errors.append("trigger_count は 1 以上でなければなりません")
        if self.sampling_points < 1:
            errors.append("sampling_points は 1 以上でなければなりません")
        if self.compliance_current <= 0:
            errors.append("compliance_current は正の値でなければなりません")

        return errors
