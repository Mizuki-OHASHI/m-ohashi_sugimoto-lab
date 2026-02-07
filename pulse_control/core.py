"""パルス幅掃引の装置通信・掃引ロジック・データ保存."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pyvisa

from config import SweepConfig


class PulseInstrument:
    """Keysight M96 PXI SMU のパルス測定制御."""

    def __init__(self, visa_address: str) -> None:
        rm = pyvisa.ResourceManager("@py")
        self.instr = rm.open_resource(visa_address)
        self.instr.read_termination = "\n"
        self.instr.write_termination = "\n"
        self.idn = self.instr.query("*IDN?")
        print(f"接続: {self.idn}")

    def close(self) -> None:
        self.instr.close()

    @staticmethod
    def check_connection(visa_address: str) -> str:
        """接続チェック. 成功時は *IDN? の応答を返す. 失敗時は例外を送出."""
        rm = pyvisa.ResourceManager("@py")
        instr = rm.open_resource(visa_address)
        instr.read_termination = "\n"
        instr.write_termination = "\n"
        try:
            idn = instr.query("*IDN?")
        finally:
            instr.close()
        return idn

    # ------------------------------------------------------------------ #
    #  装置初期設定
    # ------------------------------------------------------------------ #
    def setup(self, config: SweepConfig) -> None:
        """装置の初期設定（パルスモード、測定レンジ、サンプリングモード等）."""
        w = self.instr.write
        q = self.instr.query

        q("SYST:ERR:COUN?")
        w("*CLS")

        # 待機・レンジ
        w("SOUR1:WAIT:AUTO ON")
        w("SENS1:WAIT:AUTO ON")
        w("SOUR1:SWE:RANG BEST")
        w("SOUR1:VOLT:RANG:AUTO ON")

        # パルスモード設定
        w("SOUR1:FUNC PULS")
        w(f"SOUR1:VOLT {config.v_off}")
        w(f"SOUR1:VOLT:TRIG {config.v_on}")
        w("SOUR1:FUNC:MODE VOLT")
        w("SOUR1:VOLT:MODE FIX")

        # コンプライアンス
        w(f"SENS1:CURR:PROT {config.compliance_current}")

        # トリガー遅延
        w("TRIG1:TRAN:DEL 0")

        # データフォーマット
        w("FORM REAL,64")
        w("FORM:BORD NORM")
        w("FORM:ELEM:SENS VOLT,CURR,TIME,SOUR")

        # 測定関数
        w("SENS1:FUNC:OFF:ALL")
        w('SENS1:FUNC:ON "VOLT"')
        w("SENS1:VOLT:APER:AUTO OFF")
        w(f"SENS1:VOLT:APER {config.aperture_time}")
        w(f"SENS1:VOLT:RANG:UPP {abs(config.v_on)}")
        w("SENS1:VOLT:RANG:AUTO:LLIM MIN")

        w('SENS1:FUNC:ON "CURR"')
        w("SENS1:CURR:APER:AUTO OFF")
        w(f"SENS1:CURR:APER {config.aperture_time}")
        w(f"SENS1:CURR:RANG:UPP {abs(config.v_on) / 50}")
        w("SENS1:CURR:RANG:AUTO:LLIM 1e-3")

        # サンプリング（デジタイザ）モード
        w("SENS1:FUNC:MODE SAMPling")
        w(f"SENS1:SAMP:POINts {config.sampling_points}")

        # トリガー設定
        w("SOUR1:FUNC:TRIG:CONT OFF")
        w("ARM1:ALL:COUN 1")
        w("ARM1:ALL:DEL 0")
        w("ARM1:ALL:SOUR AINT")
        w("ARM1:ALL:TIM MIN")
        w(f"TRIG1:ALL:COUN {config.trigger_count}")
        w("TRIG1:ALL:SOUR TIM")
        w(f"TRIG1:ALL:TIM {config.trigger_time}")

        # オフセット計算用
        w("SOUR1:WAIT OFF")
        w("SENS1:WAIT OFF")

        # 出力 ON
        w("OUTP1:STAT ON")

        # ステータスレジスタ
        w("STAT:OPER:PTR 7020")
        w("STAT:OPER:NTR 7020")
        w("STAT:OPER:ENAB 7020")
        w("*SRE 128")

        # タイムカウンタ自動リセット
        w("SYST:TIME:TIM:COUN:RES:AUTO ON")

        q("*OPC?")

    # ------------------------------------------------------------------ #
    #  単一パルス幅での測定
    # ------------------------------------------------------------------ #
    def measure_single(
        self,
        pulse_width: float,
        pulse_delay: float,
        config: SweepConfig,
    ) -> dict[str, Any]:
        """単一パルス幅での測定を実行し結果を返す."""
        w = self.instr.write
        q = self.instr.query

        # パルス幅・遅延を設定
        w(f"SOUR1:PULS:WIDT {pulse_width}")
        w(f"SOUR1:PULS:DEL {pulse_delay}")

        # ベース電圧・ピーク電圧を再設定
        w(f"SOUR1:VOLT {config.v_off}")
        w(f"SOUR1:VOLT:TRIG {config.v_on}")

        q("*OPC?")
        w("INIT")
        q("*OPC?")

        # データ取得
        values = self.instr.query_binary_values(
            "SENS1:DATA?", datatype="d", is_big_endian=True
        )
        q("*OPC?")

        # パース: VOLT, CURR, TIME, SOUR の 4 要素ずつ
        n_points = config.sampling_points * config.trigger_count
        arr = np.array(values, dtype=float)

        timestamps = np.array([arr[4 * i + 2] for i in range(n_points)])
        voltage = np.array([arr[4 * i] for i in range(n_points)])
        current = np.array([arr[4 * i + 1] for i in range(n_points)])
        source_voltage = np.array([arr[4 * i + 3] for i in range(n_points)])

        return {
            "pulse_width": pulse_width,
            "pulse_delay": pulse_delay,
            "timestamps": timestamps,
            "voltage": voltage,
            "current": current,
            "source_voltage": source_voltage,
        }

    # ------------------------------------------------------------------ #
    #  後処理
    # ------------------------------------------------------------------ #
    def teardown(self) -> None:
        """測定終了処理（出力を安全な状態に戻す）."""
        w = self.instr.write
        w("SOUR1:VOLT 0.0")
        w("SOUR1:CURR 0.0")
        w("SENS1:VOLT:PROT 100e-6")
        w("OUTP1:STAT OFF")


# ================================================================== #
#  掃引実行
# ================================================================== #
def run_sweep(
    config: SweepConfig,
    instrument: PulseInstrument,
    callback: Callable[[int, int, dict], None] | None = None,
) -> list[dict]:
    """パルス幅掃引を実行する.

    Parameters
    ----------
    config : SweepConfig
    instrument : PulseInstrument
    callback : (step_index, total_steps, result_dict) -> None
        各ステップ完了後に呼ばれるコールバック（進捗通知用）

    Returns
    -------
    list[dict] : 各パルス幅での測定結果
    """
    widths = _generate_widths(config.width_start, config.width_stop, config.width_step)
    total = len(widths)
    results: list[dict] = []

    for i, width in enumerate(widths):
        pulse_delay = config.center_delay - width / 2
        print(f"  [{i + 1}/{total}] width={width:.6f} s, delay={pulse_delay:.6f} s")

        result = instrument.measure_single(width, pulse_delay, config)
        results.append(result)

        if callback is not None:
            callback(i, total, result)

    return results


def _generate_widths(start: float, stop: float, step: float) -> list[float]:
    """start から stop まで step 刻みのリストを生成."""
    n = int(round((stop - start) / step)) + 1
    return [round(start + i * step, 10) for i in range(n)]


# ================================================================== #
#  結果保存
# ================================================================== #
def save_results(
    results: list[dict],
    config: SweepConfig,
    output_dir: str | Path,
) -> None:
    """各パルス幅の測定結果を CSV に保存し、設定も TOML として保存する."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for result in results:
        width = result["pulse_width"]
        filename = f"width_{width:.6f}s.csv"
        filepath = out / filename

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "voltage", "current", "source_voltage"])
            for t, v, c, sv in zip(
                result["timestamps"],
                result["voltage"],
                result["current"],
                result["source_voltage"],
            ):
                writer.writerow([t, v, c, sv])

        print(f"  保存: {filepath}")

    # 設定も保存
    config.to_toml(out / "config.toml")
    print(f"  設定保存: {out / 'config.toml'}")
