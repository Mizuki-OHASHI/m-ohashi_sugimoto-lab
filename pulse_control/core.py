"""Instrument communication and sweep logic for Agilent 81180A AWG."""

from __future__ import annotations

import time
from logging import getLogger
from typing import Callable

import pyvisa

from config import SweepConfig

logger = getLogger(__name__)


class PulseInstrument:
    """Controller for Agilent 81180A Arbitrary Waveform Generator."""

    def __init__(self, visa_address: str) -> None:
        rm = pyvisa.ResourceManager("@py")
        self.instr = rm.open_resource(visa_address)
        self.instr.read_termination = "\n"
        self.instr.write_termination = "\n"
        self.idn = self.instr.query("*IDN?")
        logger.info("Connected: %s", self.idn)

    # ------------------------------------------------------------------ #
    #  SCPI wrappers (with debug logging)
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
        """Check connection. Returns *IDN? response on success, raises on failure."""
        logger.info("Checking connection: %s", visa_address)
        rm = pyvisa.ResourceManager("@py")
        instr = rm.open_resource(visa_address)
        instr.read_termination = "\n"
        instr.write_termination = "\n"
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
    #  Instrument setup (based on VBA UpdateSQR / SweepTau)
    # ------------------------------------------------------------------ #
    def setup(self, config: SweepConfig) -> None:
        """Initial instrument setup (square mode, amplitude, offset, etc.)."""
        logger.info("Starting instrument setup")
        w = self._write
        q = self._query

        # Set CH2 to DC mode (VBA SweepTau L63-66)
        w(":INST CH2")
        w(":FUNCtion:SHAPe DC")

        # CH1 configuration (VBA UpdateSQR L154,196-200)
        w(":INST CH1")
        w(":FUNCtion:SHAPe SQUare")
        w(f":FREQuency {config.frequency}")

        # High-impedance load calculation (VBA UpdateSQR L183-184)
        ampl = (config.v_on - config.v_off) / 2
        offs = (config.v_on + config.v_off) / 4
        w(f":VOLT:AMPLitude {ampl}")
        w(f":VOLT:OFFSet {offs}")

        w(f":TRIGger:DELay {config.trigger_delay}")

        # Initial duty cycle from width_start
        dcycle = config.width_start * config.frequency * 100
        w(f":SQUare:DCYCle {dcycle}")

        w(":OUTPut ON")
        q("*OPC?")
        logger.info("Instrument setup complete")

    # ------------------------------------------------------------------ #
    #  Pulse width control
    # ------------------------------------------------------------------ #
    def set_pulse_width(self, width: float, frequency: float) -> None:
        """Convert pulse width to duty cycle and apply.

        CH1 is already selected by setup(), so channel selection is skipped
        to minimise commands and reduce glitch duration.
        """
        dcycle = width * frequency * 100
        self._write(f":SQUare:DCYCle {dcycle}")

    # ------------------------------------------------------------------ #
    #  Teardown (based on VBA WaveForm DC switch / SweepTau cleanup)
    # ------------------------------------------------------------------ #
    def teardown(self) -> None:
        """Teardown: return outputs to a safe state."""
        logger.info("Starting teardown")
        w = self._write
        # CH1 off (VBA WaveForm L542-543)
        w(":INST CH1")
        w(":OUTPut OFF")
        w(":FUNCtion:SHAPe DC")
        w(":DC:OFFSet 0")
        # CH2 off (VBA SweepTau L126-128)
        w(":INST CH2")
        w(":DC:OFFSet 0")
        # Switch back to CH1 (VBA SweepTau L130)
        w(":INST CH1")
        logger.info("Teardown complete")


# ================================================================== #
#  Sweep execution (based on VBA SweepTau pattern)
# ================================================================== #
def run_sweep(
    config: SweepConfig,
    instrument: PulseInstrument,
    callback: Callable[[int, int], None] | None = None,
) -> None:
    """Execute pulse width sweep.

    Follows the same pattern as VBA SweepTau: Sleep → channel select → update params.

    Parameters
    ----------
    config : SweepConfig
    instrument : PulseInstrument
    callback : (step_index, total_steps) -> None
        Called after each step for progress reporting.
    """
    widths = _generate_widths(config.width_start, config.width_stop, config.width_step)
    total = len(widths)

    for i, width in enumerate(widths):
        dcycle = width * config.frequency * 100
        logger.info("[%d/%d] width=%.6f s, duty=%.2f%%", i + 1, total, width, dcycle)

        # Same order as VBA: Sleep → update params (SweepTau L94-96)
        time.sleep(config.wait_time)
        instrument.set_pulse_width(width, config.frequency)

        if callback is not None:
            callback(i, total)

    # Final wait (VBA SweepTau L114: Sleep(wait))
    time.sleep(config.wait_time)


def _generate_widths(start: float, stop: float, step: float) -> list[float]:
    """Generate a list of widths from start to stop with the given step."""
    n = int(round((stop - start) / step)) + 1
    return [round(start + i * step, 10) for i in range(n)]
