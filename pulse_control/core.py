"""パルス幅掃引の装置通信・掃引ロジック（Agilent 81180A AWG 用）."""

from __future__ import annotations

import time
from logging import getLogger
from typing import Callable

import pyvisa

from config import SweepConfig

logger = getLogger(__name__)


class PulseInstrument:
    """Agilent 81180A Arbitrary Waveform Generator の制御."""

    def __init__(self, visa_address: str) -> None:
        rm = pyvisa.ResourceManager("@py")
        self.instr = rm.open_resource(visa_address)
        self.instr.read_termination = "\n"
        self.instr.write_termination = "\n"
        self.idn = self.instr.query("*IDN?")
        logger.info("接続: %s", self.idn)

    # ------------------------------------------------------------------ #
    #  SCPI ラッパー（debug ログ付き）
    # ------------------------------------------------------------------ #
    def _write(self, cmd: str) -> None:
        logger.debug("SCPI write: %s", cmd)
        self.instr.write(cmd)

    def _query(self, cmd: str) -> str:
        logger.debug("SCPI query: %s", cmd)
        resp = self.instr.query(cmd)
        logger.debug("SCPI response: %s", resp)
        return resp

    def close(self) -> None:
        self.instr.close()

    @staticmethod
    def check_connection(visa_address: str) -> str:
        """接続チェック. 成功時は *IDN? の応答を返す. 失敗時は例外を送出."""
        logger.info("接続チェック: %s", visa_address)
        rm = pyvisa.ResourceManager("@py")
        instr = rm.open_resource(visa_address)
        instr.read_termination = "\n"
        instr.write_termination = "\n"
        try:
            idn = instr.query("*IDN?")
        except Exception:
            logger.exception("接続チェック失敗: %s", visa_address)
            raise
        finally:
            instr.close()
        logger.info("接続チェック成功: %s", idn)
        return idn

    # ------------------------------------------------------------------ #
    #  装置初期設定（VBA UpdateSQR / SweepTau に準拠）
    # ------------------------------------------------------------------ #
    def setup(self, config: SweepConfig) -> None:
        """装置の初期設定（Square モード、振幅、オフセット等）."""
        logger.info("装置セットアップ開始")
        w = self._write
        q = self._query

        # CH2 を DC モードに設定（VBA SweepTau L63-66）
        w(":INST CH2")
        w(":FUNCtion:SHAPe DC")

        # CH1 設定（VBA UpdateSQR L154,196-200）
        w(":INST CH1")
        w(":FUNCtion:SHAPe SQUare")
        w(f":FREQuency {config.frequency}")

        # ハイインピーダンス負荷用の計算（VBA UpdateSQR L183-184）
        ampl = (config.v_on - config.v_off) / 2
        offs = (config.v_on + config.v_off) / 4
        w(f":VOLT:AMPLitude {ampl}")
        w(f":VOLT:OFFSet {offs}")

        w(f":TRIGger:DELay {config.trigger_delay}")

        # 初期 duty cycle を width_start から算出
        dcycle = config.width_start * config.frequency * 100
        w(f":SQUare:DCYCle {dcycle}")

        w(":OUTPut ON")
        q("*OPC?")
        logger.info("装置セットアップ完了")

    # ------------------------------------------------------------------ #
    #  パルス幅設定
    # ------------------------------------------------------------------ #
    def set_pulse_width(self, width: float, frequency: float) -> None:
        """パルス幅を duty cycle に変換して設定する.

        setup() で CH1 が選択済みのため、チャンネル選択は省略し
        コマンド数を最小限にしてグリッチを短縮する。
        """
        dcycle = width * frequency * 100
        self._write(f":SQUare:DCYCle {dcycle}")

    # ------------------------------------------------------------------ #
    #  後処理（VBA WaveForm DC切替 / SweepTau 終了処理に準拠）
    # ------------------------------------------------------------------ #
    def teardown(self) -> None:
        """終了処理（出力を安全な状態に戻す）."""
        logger.info("装置ティアダウン開始")
        w = self._write
        # CH1 終了（VBA WaveForm L542-543）
        w(":INST CH1")
        w(":OUTPut OFF")
        w(":FUNCtion:SHAPe DC")
        w(":DC:OFFSet 0")
        # CH2 終了（VBA SweepTau L126-128）
        w(":INST CH2")
        w(":DC:OFFSet 0")
        # CH1 に戻す（VBA SweepTau L130: 便宜上CH1に戻しておく）
        w(":INST CH1")
        logger.info("装置ティアダウン完了")


# ================================================================== #
#  掃引実行（VBA SweepTau のパターンに準拠）
# ================================================================== #
def run_sweep(
    config: SweepConfig,
    instrument: PulseInstrument,
    callback: Callable[[int, int], None] | None = None,
) -> None:
    """パルス幅掃引を実行する.

    VBA SweepTau と同じパターン: Sleep → チャンネル選択 → パラメータ変更。

    Parameters
    ----------
    config : SweepConfig
    instrument : PulseInstrument
    callback : (step_index, total_steps) -> None
        各ステップ完了後に呼ばれるコールバック（進捗通知用）
    """
    widths = _generate_widths(config.width_start, config.width_stop, config.width_step)
    total = len(widths)

    for i, width in enumerate(widths):
        dcycle = width * config.frequency * 100
        logger.info("[%d/%d] width=%.6f s, duty=%.2f%%", i + 1, total, width, dcycle)

        # VBA と同じ順序: Sleep → パラメータ変更（SweepTau L94-96）
        time.sleep(config.wait_time)
        instrument.set_pulse_width(width, config.frequency)

        if callback is not None:
            callback(i, total)

    # 終了後待機（VBA SweepTau L114: Sleep(wait)）
    time.sleep(config.wait_time)


def _generate_widths(start: float, stop: float, step: float) -> list[float]:
    """start から stop まで step 刻みのリストを生成."""
    n = int(round((stop - start) / step)) + 1
    return [round(start + i * step, 10) for i in range(n)]
