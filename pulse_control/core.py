"""Instrument communication and sweep logic for Agilent 81180A AWG."""

from __future__ import annotations

import math
import time
from logging import getLogger
from typing import Callable

import numpy as np
import pyvisa

from config import BaseConfig, DelaySweepConfig, SweepConfig

logger = getLogger(__name__)


def _calc_arb_params(
    frequency: float, widths: list[float], *, resolution_n: int = 1,
) -> tuple[float, int]:
    """Compute optimal sample rate and points-per-period for arbitrary mode.

    Algorithm:
    1. Compute GCD of period and all widths at picosecond precision.
    2. Divide GCD by K to get time_per_point.
    3. Increase K until points_per_period >= 320 and is a multiple of 32.
       (81180A: min segment = 320 points, increment = 32 points)
    4. Multiply by resolution_n for finer delay resolution.
    5. Verify sample_rate = 1/time_per_point is within 10 MSa/s – 4.2 GSa/s.
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

    # Scale up K so that points_per_period >= 320 and is a multiple of 32
    # (81180A minimum segment length = 320, increment = 32)
    k = 1
    while base_points * k < 320:
        k += 1
    # Ensure multiple of 32
    pts = base_points * k
    while pts % 32 != 0:
        k += 1
        pts = base_points * k

    # Apply resolution multiplier (base × k is already a multiple of 32,
    # so base × k × n is also a multiple of 32)
    pts *= resolution_n

    points_per_period = pts
    time_per_point = period / points_per_period
    sample_rate = 1.0 / time_per_point

    return sample_rate, points_per_period


def _generate_pulse_waveform(
    points_per_period: int, duty_cycle: float, *, inverted: bool = False,
) -> np.ndarray:
    """Generate one period of pulse waveform as DAC values (centered).

    The ON region is always centered within the period.

    When inverted=False (V_ON >= V_OFF, HIGH = V_ON):
        ON region = DAC 4095 (HIGH), OFF region = DAC 0 (LOW).
    When inverted=True (V_ON < V_OFF, HIGH = V_OFF):
        ON region = DAC 0 (LOW = V_ON), OFF region = DAC 4095 (HIGH = V_OFF).
    """
    on_points = round(points_per_period * duty_cycle / 100)
    start = (points_per_period - on_points) // 2
    if inverted:
        waveform = np.full(points_per_period, 4095, dtype=np.uint16)
        waveform[start:start + on_points] = 0
    else:
        waveform = np.zeros(points_per_period, dtype=np.uint16)
        waveform[start:start + on_points] = 4095
    return waveform


class PulseInstrument:
    """Controller for Agilent 81180A Arbitrary Waveform Generator."""

    def __init__(self, visa_address: str) -> None:
        rm = pyvisa.ResourceManager("@py")
        instr = rm.open_resource(visa_address)
        instr.read_termination = "\n"
        instr.write_termination = "\n"
        instr.timeout = 5000
        try:
            self.idn = instr.query("*IDN?")
        except Exception:
            instr.close()
            raise
        self.instr = instr
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
        instr.timeout = 5000
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
    def setup(
        self, config: BaseConfig, initial_width: float, *, channel: int = 1,
    ) -> None:
        """Initial instrument setup (square mode, amplitude, offset, etc.)."""
        logger.info("Starting instrument setup (CH%d)", channel)
        w = self._write
        q = self._query

        w(f":INST CH{channel}")
        w(":FUNCtion:SHAPe SQUare")
        w(f":FREQuency {config.frequency}")

        # High-impedance load calculation (VBA UpdateSQR L183-184)
        ampl = abs(config.v_on - config.v_off) / 2
        offs = (config.v_on + config.v_off) / 4
        w(f":VOLT:AMPLitude {ampl}")
        w(f":VOLT:OFFSet {offs}")

        w(f":TRIGger:DELay {config.trigger_delay}")

        dcycle = initial_width * config.frequency * 100
        w(f":SQUare:DCYCle {dcycle}")

        # Phase offset to center the pulse at T/2
        phase = 180.0 - dcycle * 1.8
        logger.info(
            "Square setup: v_on=%.4f, v_off=%.4f, dcycle=%.2f%%, phase=%.1f",
            config.v_on, config.v_off, dcycle, phase,
        )
        w(f":PHASe {phase}")

        w(":OUTPut ON")
        q("*OPC?")
        logger.info("Instrument setup complete (CH%d)", channel)

    # ------------------------------------------------------------------ #
    #  Pulse width control
    # ------------------------------------------------------------------ #
    def set_pulse_width(
        self, width: float, frequency: float, *, channel: int = 1,
    ) -> None:
        """Convert pulse width to duty cycle and apply."""
        self._write(f":INST CH{channel}")
        dcycle = width * frequency * 100
        self._write(f":SQUare:DCYCle {dcycle}")
        phase = 180.0 - dcycle * 1.8
        self._write(f":PHASe {phase}")

    # ------------------------------------------------------------------ #
    #  Arbitrary waveform setup
    # ------------------------------------------------------------------ #
    def setup_arbitrary(
        self,
        config: BaseConfig,
        widths: list[float],
        *,
        channel: int = 1,
        callback: Callable[[int, int], None] | None = None,
    ) -> None:
        """Arbitrary Waveform mode: upload all segments up front."""
        logger.info("Starting arbitrary waveform setup (%d segments, CH%d)", len(widths), channel)
        w = self._write

        w(f":INST CH{channel}")
        # Switch to USER mode first (81180A requires this before trace operations)
        w(":FUNC:MODE USER")
        # Clear existing segments to avoid conflicts
        w(":TRAC:DEL:ALL")

        sample_rate, points_per_period = _calc_arb_params(
            config.frequency, widths, resolution_n=config.resolution_n,
        )
        logger.info(
            "ARB params: sample_rate=%.3e Sa/s, points_per_period=%d",
            sample_rate, points_per_period,
        )
        w(f":FREQ:RAST {sample_rate}")

        # Upload waveform segment for each pulse width
        inverted = config.v_on < config.v_off
        for i, width in enumerate(widths):
            seg = i + 1
            dcycle = width * config.frequency * 100
            waveform = _generate_pulse_waveform(
                points_per_period, dcycle, inverted=inverted,
            )
            w(f":TRACe:DEF {seg}, {points_per_period}")
            w(f":TRACe:SEL {seg}")
            # IEEE 488.2 binary block transfer (little-endian per 81180A spec)
            self.instr.write_binary_values(":TRACe:DATA", waveform, datatype="H")
            self._query("*OPC?")  # wait for instrument to finish processing
            logger.debug("Uploaded segment %d: duty=%.2f%%, %d points", seg, dcycle, points_per_period)
            if callback is not None:
                callback(i, len(widths))

        # Select first segment
        w(":TRACe:SEL 1")

        # Amplitude / offset (same calculation as square mode)
        ampl = abs(config.v_on - config.v_off) / 2
        offs = (config.v_on + config.v_off) / 4
        w(f":VOLT:AMPLitude {ampl}")
        w(f":VOLT:OFFSet {offs}")

        w(f":TRIGger:DELay {config.trigger_delay}")
        w(":OUTPut ON")
        self._query("*OPC?")
        logger.info("Arbitrary waveform setup complete")

    def select_segment(self, index: int, *, channel: int = 1) -> None:
        """Switch to a pre-uploaded segment (for arbitrary mode sweep)."""
        self._write(f":INST CH{channel}")
        self._write(f":TRACe:SEL {index + 1}")

    def set_trigger_delay(self, delay: int, *, channel: int = 1) -> None:
        """Set trigger delay on the specified channel."""
        self._write(f":INST CH{channel}")
        self._write(f":TRIGger:DELay {delay}")

    # ------------------------------------------------------------------ #
    #  DC 0V (safe state)
    # ------------------------------------------------------------------ #
    def set_dc_zero(self) -> None:
        """Set both channels to DC 0V (safe state with output ON)."""
        logger.info("Setting DC 0V")
        w = self._write
        w(":INST CH1")
        w(":OUTPut OFF")
        w(":PHASe 0")
        w(":FUNCtion:SHAPe DC")
        w(":DC:OFFSet 0")
        w(":INST CH2")
        w(":DC:OFFSet 0")
        w(":INST CH1")
        self._query("*OPC?")
        logger.info("DC 0V set complete")

    # ------------------------------------------------------------------ #
    #  Teardown (based on VBA WaveForm DC switch / SweepTau cleanup)
    # ------------------------------------------------------------------ #
    def teardown(self, *, channel: int = 1) -> None:
        """Teardown: return the specified channel to a safe state."""
        logger.info("Starting teardown (CH%d)", channel)
        w = self._write
        w(f":INST CH{channel}")
        w(":OUTPut OFF")
        w(":PHASe 0")
        w(":FUNCtion:SHAPe DC")
        w(":DC:OFFSet 0")
        logger.info("Teardown complete (CH%d)", channel)


# ================================================================== #
#  Sweep execution (based on VBA SweepTau pattern)
# ================================================================== #
def run_sweep(
    config: SweepConfig,
    instrument: PulseInstrument,
    callback: Callable[[int, int], None] | None = None,
    *,
    channels: list[int] | None = None,
) -> None:
    """Execute pulse width sweep.

    Parameters
    ----------
    config : SweepConfig
    instrument : PulseInstrument
    callback : (step_index, total_steps) -> None
        Called after each step for progress reporting.
    channels : list of channel numbers (1 and/or 2). Defaults to [1].
    """
    if channels is None:
        channels = [1]

    widths = _generate_widths(config.width_start, config.width_stop, config.width_step)
    total = len(widths)

    # Delay sweep parameters
    delay_start = config.trigger_delay
    delay_stop = config.trigger_delay_stop
    sweep_delay = delay_stop is not None and delay_stop != delay_start

    # Pre-compute coefficients for delay interpolation:
    #   delay(pw) = a * pw^n + b  (n = delay_exponent)
    #   delay(width_start) = delay_start, delay(width_stop) = delay_stop
    _coeff_a = _coeff_b = 0.0
    _exp = config.delay_exponent
    if sweep_delay:
        f_start = config.width_start ** _exp
        f_stop = config.width_stop ** _exp
        if f_start != f_stop:
            _coeff_a = (delay_start - delay_stop) / (f_start - f_stop)
            _coeff_b = delay_start - _coeff_a * f_start

    def _apply_delay(i: int) -> None:
        """Interpolate and apply trigger delay for step *i*."""
        if not sweep_delay:
            return
        raw = _coeff_a * widths[i] ** _exp + _coeff_b
        delay = round(raw / 8) * 8
        for ch in channels:
            instrument.set_trigger_delay(delay, channel=ch)

    # --- Arbitrary mode: switch pre-uploaded segments ---
    if config.waveform_mode == "arbitrary":
        for i in range(total):
            logger.info("[%d/%d] segment=%d", i + 1, total, i + 1)
            time.sleep(config.wait_time)
            _apply_delay(i)
            for ch in channels:
                instrument.select_segment(i, channel=ch)
            if callback is not None:
                callback(i, total)
        time.sleep(config.wait_time)
        return

    # --- Square mode: conventional duty cycle changes ---
    for i, width in enumerate(widths):
        dcycle = width * config.frequency * 100
        logger.info("[%d/%d] width=%.6f s, duty=%.2f%%", i + 1, total, width, dcycle)

        time.sleep(config.wait_time)
        _apply_delay(i)
        for ch in channels:
            instrument.set_pulse_width(width, config.frequency, channel=ch)

        if callback is not None:
            callback(i, total)

    # Final wait
    time.sleep(config.wait_time)


def _generate_widths(start: float, stop: float, step: float) -> list[float]:
    """Generate a list of widths from start to stop with the given step."""
    n = int(round((stop - start) / step)) + 1
    return [round(start + i * step, 10) for i in range(n)]


def _generate_delays(start: int, stop: int, step: int) -> list[int]:
    """Generate a list of trigger delays from start to stop with the given step."""
    n = (stop - start) // step + 1
    return [start + i * step for i in range(n)]


# ================================================================== #
#  Delay sweep execution
# ================================================================== #
def run_delay_sweep(
    config: DelaySweepConfig,
    instrument: PulseInstrument,
    callback: Callable[[int, int], None] | None = None,
    *,
    channels: list[int] | None = None,
) -> None:
    """Execute trigger delay sweep.

    Parameters
    ----------
    config : DelaySweepConfig
    instrument : PulseInstrument
    callback : (step_index, total_steps) -> None
    channels : list of channel numbers (1 and/or 2). Defaults to [1].
    """
    if channels is None:
        channels = [1]

    delays = _generate_delays(config.delay_start, config.delay_stop, config.delay_step)
    total = len(delays)

    for i, delay in enumerate(delays):
        logger.info("[%d/%d] delay=%d points", i + 1, total, delay)
        time.sleep(config.wait_time)
        for ch in channels:
            instrument.set_trigger_delay(delay, channel=ch)
        if callback is not None:
            callback(i, total)

    # Final wait
    time.sleep(config.wait_time)
