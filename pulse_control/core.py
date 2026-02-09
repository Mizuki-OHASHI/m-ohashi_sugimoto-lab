"""Instrument communication and sweep logic for Agilent 81180A AWG."""

from __future__ import annotations

import math
import time
from logging import getLogger
from typing import Callable

import numpy as np
import pyvisa

from config import SweepConfig

logger = getLogger(__name__)


def _calc_arb_params(frequency: float, widths: list[float]) -> tuple[float, int]:
    """Compute optimal sample rate and points-per-period for arbitrary mode.

    Algorithm:
    1. Compute GCD of period and all widths at picosecond precision.
    2. Divide GCD by K to get time_per_point.
    3. Increase K until points_per_period >= 64 and is a multiple of 8.
    4. Verify sample_rate = 1/time_per_point is within 10 MSa/s – 4.2 GSa/s.
    """
    period = 1.0 / frequency
    # Convert to picoseconds (integer) for exact GCD
    ps_period = round(period * 1e12)
    ps_widths = [round(w * 1e12) for w in widths]

    g = ps_period
    for pw in ps_widths:
        g = math.gcd(g, pw)
    if g == 0:
        raise ValueError("GCD is zero – check frequency and widths")

    base_points = ps_period // g  # minimum points per period

    # Scale up K so that points_per_period >= 64 and is a multiple of 8
    k = 1
    while base_points * k < 64:
        k += 1
    # Ensure multiple of 8
    pts = base_points * k
    while pts % 8 != 0:
        k += 1
        pts = base_points * k

    points_per_period = pts
    time_per_point = period / points_per_period
    sample_rate = 1.0 / time_per_point

    return sample_rate, points_per_period


def _generate_pulse_waveform(
    points_per_period: int, duty_cycle: float,
) -> np.ndarray:
    """Generate one period of pulse waveform as DAC values.

    ON region = DAC max (4095), OFF region = DAC min (0).
    Actual output voltage is controlled by :VOLT:AMPLitude / :VOLT:OFFSet.
    """
    on_points = round(points_per_period * duty_cycle / 100)
    waveform = np.zeros(points_per_period, dtype=np.uint16)
    start = (points_per_period - on_points) // 2
    waveform[start:start + on_points] = 4095
    return waveform


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

        # Phase offset to center the pulse at T/2
        phase = 180.0 - dcycle * 1.8
        w(f":PHASe {phase}")

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
        # Phase offset to keep pulse centered at T/2
        phase = 180.0 - dcycle * 1.8
        self._write(f":PHASe {phase}")

    # ------------------------------------------------------------------ #
    #  Arbitrary waveform setup
    # ------------------------------------------------------------------ #
    def setup_arbitrary(self, config: SweepConfig, widths: list[float]) -> None:
        """Arbitrary Waveform mode: upload all segments up front."""
        logger.info("Starting arbitrary waveform setup (%d segments)", len(widths))
        w = self._write

        # CH2 DC mode (same as square mode)
        w(":INST CH2")
        w(":FUNCtion:SHAPe DC")

        # CH1 arbitrary mode
        w(":INST CH1")

        sample_rate, points_per_period = _calc_arb_params(config.frequency, widths)
        logger.info(
            "ARB params: sample_rate=%.3e Sa/s, points_per_period=%d",
            sample_rate, points_per_period,
        )
        w(f":FREQ:RAST {sample_rate}")

        # Upload waveform segment for each pulse width
        for i, width in enumerate(widths):
            seg = i + 1
            dcycle = width * config.frequency * 100
            waveform = _generate_pulse_waveform(points_per_period, dcycle)
            w(f":TRACe:DEF {seg}, {points_per_period}")
            w(f":TRACe:SEL {seg}")
            # IEEE 488.2 binary block transfer
            self.instr.write_binary_values(":TRACe:DATA", waveform, datatype="H")
            logger.debug("Uploaded segment %d: duty=%.2f%%, %d points", seg, dcycle, points_per_period)

        # Select first segment and switch to ARB mode
        w(":TRACe:SEL 1")
        w(":FUNC:MODE ARB")

        # Amplitude / offset (same calculation as square mode)
        ampl = (config.v_on - config.v_off) / 2
        offs = (config.v_on + config.v_off) / 4
        w(f":VOLT:AMPLitude {ampl}")
        w(f":VOLT:OFFSet {offs}")

        w(f":TRIGger:DELay {config.trigger_delay}")
        w(":OUTPut ON")
        self._query("*OPC?")
        logger.info("Arbitrary waveform setup complete")

    def select_segment(self, index: int) -> None:
        """Switch to a pre-uploaded segment (for arbitrary mode sweep)."""
        self._write(f":TRACe:SEL {index + 1}")

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
        w(":PHASe 0")
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

    # --- Arbitrary mode: switch pre-uploaded segments ---
    if config.waveform_mode == "arbitrary":
        for i in range(total):
            logger.info("[%d/%d] segment=%d", i + 1, total, i + 1)
            time.sleep(config.wait_time)
            instrument.select_segment(i)
            if callback is not None:
                callback(i, total)
        time.sleep(config.wait_time)
        return

    # --- Square mode: conventional duty cycle changes ---
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
