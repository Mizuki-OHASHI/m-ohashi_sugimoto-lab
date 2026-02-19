"""Instrument communication for Agilent/Keysight 34401A Digital Multimeter.

Hardware
--------
- Prolific PL2303GT USB-Serial アダプタ経由で RS-232 接続 (COM3)
- 34401A 本体のシリアル設定は工場出荷時のまま使用すること:
  9600 baud / 7 data bits / even parity / 2 stop bits
- 本体側の設定変更: Shift > I/O Menu > BAUD RATE / PARITY で確認可能

Dependencies
------------
- pyvisa, pyvisa-py, pyserial (ASRL シリアルバックエンドに必要)

Notes
-----
- **リモートモード**: 接続時に ``SYST:REM`` を送信するため、接続中は
  フロントパネルがロックされる。``close()`` で ``SYST:LOC`` を送り解放する。
- **COM ポート排他**: COM3 は同時に1プロセスしか使えない。
  Tera Term 等を閉じてから使うこと。
- **繰り返し測定**: ``read_dc_voltage()`` は毎回オートレンジ設定が走るため遅い。
  1 秒周期等で連続測定する場合は ``configure_dc_voltage()`` を1回呼んでから
  ``read()`` を繰り返すほうが高速。
- **エラー安全**: ``with`` 文を使えば例外発生時も確実に ``close()`` される。
"""

from __future__ import annotations

from logging import getLogger

import pyvisa
from pyvisa import constants

logger = getLogger(__name__)

DEFAULT_34401A_ADDRESS = "ASRL3::INSTR"


class Multimeter:
    """Controller for Agilent 34401A Digital Multimeter (RS-232 via USB-serial).

    Usage::

        with Multimeter() as dmm:
            dmm.configure_dc_voltage()
            for _ in range(10):
                print(dmm.read())
    """

    def __init__(self, visa_address: str = DEFAULT_34401A_ADDRESS) -> None:
        rm = pyvisa.ResourceManager("@py")
        instr = rm.open_resource(visa_address)

        # RS-232 settings (34401A defaults: 9600 baud, 7 data bits, even parity, 2 stop bits)
        instr.baud_rate = 9600
        instr.data_bits = 7
        instr.stop_bits = constants.StopBits.two
        instr.parity = constants.Parity.even
        instr.flow_control = constants.VI_ASRL_FLOW_DTR_DSR

        instr.read_termination = "\n"
        instr.write_termination = "\n"
        instr.timeout = 10000

        try:
            self.idn = instr.query("*IDN?")
        except Exception:
            instr.close()
            raise
        # RS-232 requires explicit remote mode (unlike GPIB)
        instr.write("SYST:REM")
        self.instr = instr
        logger.info("Connected: %s", self.idn)

    # ------------------------------------------------------------------ #
    #  Context manager
    # ------------------------------------------------------------------ #
    def __enter__(self) -> Multimeter:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self.close()

    # ------------------------------------------------------------------ #
    #  SCPI wrappers
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
        try:
            self.instr.write("SYST:LOC")
        except Exception:
            pass
        try:
            self.instr.close()
        except Exception:
            pass

    @staticmethod
    def check_connection(visa_address: str = DEFAULT_34401A_ADDRESS) -> str:
        """Check connection. Returns *IDN? response on success, raises on failure."""
        logger.info("Checking connection: %s", visa_address)
        rm = pyvisa.ResourceManager("@py")
        instr = rm.open_resource(visa_address)
        instr.baud_rate = 9600
        instr.data_bits = 7
        instr.stop_bits = constants.StopBits.two
        instr.parity = constants.Parity.even
        instr.flow_control = constants.VI_ASRL_FLOW_DTR_DSR
        instr.read_termination = "\n"
        instr.write_termination = "\n"
        instr.timeout = 10000
        try:
            idn = instr.query("*IDN?")
        except Exception:
            logger.exception("Connection check failed: %s", visa_address)
            raise
        finally:
            instr.close()
        logger.info("Connection check OK: %s", idn)
        return idn

    # ------------------------------------------------------------------ #
    #  Measurement
    # ------------------------------------------------------------------ #
    def configure_dc_voltage(self) -> None:
        """Configure for DC voltage measurement.

        Call once before repeated read() calls.
        """
        self._write("CONF:VOLT:DC")

    def read(self) -> float:
        """Trigger one measurement and return the value.

        Requires configure_dc_voltage() (or similar) to have been called first.
        """
        resp = self._query("READ?")
        return float(resp)

    def read_dc_voltage(self) -> float:
        """Take a single DC voltage measurement and return the value [V].

        Convenience method that auto-configures range and resolution.
        Slower than configure_dc_voltage() + read() for repeated use.
        """
        resp = self._query("MEAS:VOLT:DC?")
        return float(resp)
