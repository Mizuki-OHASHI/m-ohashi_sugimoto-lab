"""Step-synced sweep controller: synchronizes AWG sweep with external step function.

Monitors DC voltage via Agilent 34401A multimeter and detects discrete voltage
step transitions from an external step-function source (-10 V -> 10 V, N levels).
Each sweep step is triggered by the corresponding voltage transition, providing
closed-loop synchronization with zero drift.

The first ``sweep_start_step`` steps are monitoring-only (signal verification).
The AWG sweep begins at step ``sweep_start_step`` and runs for M segments.

Usage::

    python -m pulse_control stepsync configs/config_step_sync.toml
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from logging import getLogger
from typing import Callable

import numpy as np

from config import IntervalSweepConfig, SweepConfig
from core import (
    PulseInstrument,
    _generate_intervals,
    _generate_widths,
)
from core_34401A import Multimeter

logger = getLogger(__name__)


# ================================================================== #
#  Configuration
# ================================================================== #

@dataclass
class StepSyncConfig:
    """Configuration for step-function-synced sweep."""

    dmm_visa_address: str

    # Step function parameters
    total_steps: int              # N: total discrete voltage levels
    sweep_start_step: int         # 0-based index where AWG sweep begins

    # Voltage range of the external step function
    v_start: float = -10.0        # Voltage at step 0 [V]
    v_stop: float = 10.0          # Voltage at step N-1 [V]

    # Detection tuning
    poll_interval: float = 0.1    # Interval between DMM reads [s]
    confirm_reads: int = 2        # Consecutive reads above threshold to confirm
    step_timeout: float = 10.0    # Max seconds to wait per step transition [s]

    # Cycle control
    num_cycles: int = 0           # 0 = infinite (Ctrl+C to stop)

    # Sequence restart detection
    restart_voltage: float = -9.5  # Below this = new sequence start [V]
    restart_timeout: float = 60.0  # Max wait for restart [s]

    def validate(self) -> list[str]:
        """Validate parameter consistency. Returns list of error messages."""
        errors: list[str] = []

        if self.total_steps < 2:
            errors.append("total_steps must be >= 2")
        if self.sweep_start_step < 0:
            errors.append("sweep_start_step must be >= 0")
        if self.sweep_start_step >= self.total_steps:
            errors.append(
                f"sweep_start_step ({self.sweep_start_step}) must be "
                f"< total_steps ({self.total_steps})"
            )
        if self.v_start >= self.v_stop:
            errors.append(
                f"v_start ({self.v_start}) must be < v_stop ({self.v_stop})"
            )
        if self.poll_interval < 0:
            errors.append("poll_interval must be >= 0")
        if self.confirm_reads < 1:
            errors.append("confirm_reads must be >= 1")
        if self.step_timeout <= 0:
            errors.append("step_timeout must be positive")
        if self.num_cycles < 0:
            errors.append("num_cycles must be >= 0 (0 = infinite)")
        if self.restart_timeout <= 0:
            errors.append("restart_timeout must be positive")

        for e in errors:
            logger.warning("Validation error: %s", e)
        return errors


# ================================================================== #
#  Step detection helpers
# ================================================================== #

def _compute_step_levels_and_thresholds(
    config: StepSyncConfig,
) -> tuple[list[float], list[float]]:
    """Pre-compute expected voltage levels and midpoint thresholds.

    Returns
    -------
    levels : list[float]
        N voltage levels from v_start to v_stop, evenly spaced.
    thresholds : list[float]
        N-1 midpoint thresholds between adjacent levels.
        When voltage crosses threshold[n], step n+1 has begun.
    """
    n = config.total_steps
    step_size = (config.v_stop - config.v_start) / (n - 1)
    levels = [config.v_start + i * step_size for i in range(n)]
    thresholds = [(levels[i] + levels[i + 1]) / 2.0 for i in range(n - 1)]
    return levels, thresholds


def detect_step_transition(
    dmm: Multimeter,
    current_step: int,
    thresholds: list[float],
    confirm_reads: int,
    timeout: float,
    poll_interval: float = 0.1,
    *,
    callback: Callable[[float, int, str], None] | None = None,
) -> tuple[bool, float]:
    """Wait for voltage to cross the next step threshold.

    Parameters
    ----------
    dmm : Multimeter
    current_step : int
        The step we are currently on (0-based).
    thresholds : list[float]
        Midpoint thresholds from ``_compute_step_levels_and_thresholds()``.
    confirm_reads : int
        Number of consecutive readings above threshold to confirm transition.
    timeout : float
        Maximum seconds to wait.
    poll_interval : float
        Seconds to sleep between DMM reads.
    callback : (voltage, step_index, phase) -> None

    Returns
    -------
    (success, last_voltage) : (bool, float)
        success is True if the transition was confirmed before timeout.
    """
    threshold = thresholds[current_step]
    confirm_count = 0
    t_start = time.time()
    last_voltage = 0.0

    while True:
        last_voltage = dmm.read()

        if callback is not None:
            callback(last_voltage, current_step, "detecting")

        if last_voltage >= threshold:
            confirm_count += 1
            if confirm_count >= confirm_reads:
                return (True, last_voltage)
        else:
            confirm_count = 0  # Reset: noise or not yet transitioned

        elapsed = time.time() - t_start
        if elapsed > timeout:
            logger.warning(
                "Step %d -> %d timeout (%.1f s). "
                "Last voltage: %.4f V, threshold: %.4f V",
                current_step, current_step + 1, timeout,
                last_voltage, threshold,
            )
            return (False, last_voltage)

        if poll_interval > 0:
            time.sleep(poll_interval)


def _wait_for_sequence_start(
    dmm: Multimeter,
    config: StepSyncConfig,
    *,
    callback: Callable[[float, int, str], None] | None = None,
) -> None:
    """Block until voltage drops below ``restart_voltage`` (sequence start).

    On the first cycle the voltage may already be low, in which case this
    returns immediately.  On subsequent cycles it waits for the external
    step function to reset.
    """
    logger.info(
        "Waiting for sequence start (voltage < %.2f V)...",
        config.restart_voltage,
    )
    t_start = time.time()

    while True:
        voltage = dmm.read()
        if callback is not None:
            callback(voltage, -1, "waiting_restart")

        if voltage < config.restart_voltage:
            logger.info(
                "Voltage below restart threshold (%.4f V < %.2f V). "
                "Sequence start detected.",
                voltage, config.restart_voltage,
            )
            return

        elapsed = time.time() - t_start
        if elapsed > config.restart_timeout:
            logger.warning(
                "Sequence restart timeout (%.1f s). "
                "Proceeding with voltage %.4f V.",
                config.restart_timeout, voltage,
            )
            return

        if config.poll_interval > 0:
            time.sleep(config.poll_interval)


# ================================================================== #
#  Inner sweep loop (shared by width and interval sweep)
# ================================================================== #

def _run_step_synced_loop(
    instrument: PulseInstrument,
    dmm: Multimeter,
    config: SweepConfig | IntervalSweepConfig,
    step_sync_config: StepSyncConfig,
    levels: list[float],
    thresholds: list[float],
    sweep_segments: int,
    apply_delay: Callable[[int], None],
    *,
    channels: list[int],
    sweep_callback: Callable[[int, int], None] | None = None,
    step_callback: Callable[[float, int, str], None] | None = None,
) -> None:
    """Execute one cycle: monitoring phase then sweep phase.

    Parameters
    ----------
    instrument : PulseInstrument
    dmm : Multimeter
    config : SweepConfig or IntervalSweepConfig
        Used only for ``restore_user_mode()`` call.
    step_sync_config : StepSyncConfig
    levels, thresholds : from ``_compute_step_levels_and_thresholds()``
    sweep_segments : int
        Number of AWG segments (M).
    apply_delay : (sweep_index) -> None
        Trigger delay interpolation function (same as run_sweep's _apply_delay).
    channels : list of channel numbers
    sweep_callback : (sweep_idx, total) -> None
    step_callback : (voltage, step_index, phase) -> None
    """
    confirm_reads = step_sync_config.confirm_reads
    step_timeout = step_sync_config.step_timeout
    poll_interval = step_sync_config.poll_interval

    # --- Monitoring phase: steps 0 .. sweep_start_step-1 ---
    if step_sync_config.sweep_start_step > 0:
        logger.info(
            "Monitoring phase: %d steps before sweep begins",
            step_sync_config.sweep_start_step,
        )

    for step_idx in range(step_sync_config.sweep_start_step):
        if step_idx == 0:
            # Step 0: just verify voltage is near first level
            voltage = dmm.read()
            logger.info(
                "Monitoring step 0/%d (V=%.4f V, expected ~%.2f V)",
                step_sync_config.total_steps, voltage, levels[0],
            )
            if step_callback is not None:
                step_callback(voltage, 0, "monitoring")
            continue

        # Wait for transition from step_idx-1 to step_idx
        success, voltage = detect_step_transition(
            dmm, step_idx - 1, thresholds,
            confirm_reads, step_timeout, poll_interval,
            callback=step_callback,
        )
        if success:
            logger.info(
                "Monitoring step %d/%d confirmed (V=%.4f V, expected ~%.2f V)",
                step_idx, step_sync_config.total_steps, voltage, levels[step_idx],
            )
        else:
            logger.warning(
                "Monitoring step %d/%d: timeout (V=%.4f V). Continuing.",
                step_idx, step_sync_config.total_steps, voltage,
            )

    # --- Restore USER mode before sweep ---
    for ch in channels:
        instrument.restore_user_mode(config, channel=ch)

    # --- Sweep phase: steps sweep_start_step .. sweep_start_step+M-1 ---
    logger.info("Sweep phase: %d segments", sweep_segments)

    for sweep_idx in range(sweep_segments):
        step_idx = step_sync_config.sweep_start_step + sweep_idx

        # Wait for step transition (except for step 0 with sweep_start_step=0)
        if step_idx > 0:
            success, voltage = detect_step_transition(
                dmm, step_idx - 1, thresholds,
                confirm_reads, step_timeout, poll_interval,
                callback=step_callback,
            )
            if not success:
                logger.warning(
                    "Sweep step %d/%d: timeout (V=%.4f V). "
                    "Advancing AWG segment anyway.",
                    sweep_idx + 1, sweep_segments, voltage,
                )
        else:
            voltage = dmm.read()

        # Apply trigger delay interpolation
        apply_delay(sweep_idx)

        # Select AWG segment
        logger.info(
            "[%d/%d] segment=%d, step=%d/%d, V=%.4f V",
            sweep_idx + 1, sweep_segments, sweep_idx + 1,
            step_idx, step_sync_config.total_steps, voltage,
        )
        for ch in channels:
            instrument.select_segment(sweep_idx, channel=ch)

        if sweep_callback is not None:
            sweep_callback(sweep_idx, sweep_segments)

    # --- Post-sweep dwell: wait for the next step so the last segment
    #     gets the same exposure time as all other segments. ---
    last_step_idx = step_sync_config.sweep_start_step + sweep_segments - 1
    if last_step_idx < len(thresholds):
        logger.info("Waiting for post-sweep step (dwell for last segment)...")
        detect_step_transition(
            dmm, last_step_idx, thresholds,
            confirm_reads, step_timeout, poll_interval,
            callback=step_callback,
        )
    else:
        # Last sweep step is the last step in the sequence — no next
        # threshold to wait for, so use a fixed dwell as fallback.
        logger.info("Last segment is final step — waiting step_timeout as dwell.")
        time.sleep(step_timeout)


# ================================================================== #
#  Delay interpolation builder (mirrors run_sweep / run_interval_sweep)
# ================================================================== #

def _build_delay_applier_width(
    config: SweepConfig,
    widths: list[float],
    channels: list[int],
    instrument: PulseInstrument,
) -> Callable[[int], None]:
    """Build _apply_delay function for width sweep (same logic as run_sweep)."""
    use_table = config.delay_mode == "table" and config.delay_table is not None

    _table_pw: np.ndarray | None = None
    _table_delay: np.ndarray | None = None
    if use_table:
        sorted_table = sorted(config.delay_table, key=lambda r: r[0])
        _table_pw = np.array([r[0] for r in sorted_table])
        _table_delay = np.array([r[1] for r in sorted_table], dtype=float)

    delay_start = config.trigger_delay
    delay_stop = config.trigger_delay_stop
    sweep_delay = delay_stop is not None and delay_stop != delay_start

    _coeff_a = _coeff_b = 0.0
    _exp = config.delay_exponent
    if not use_table and sweep_delay:
        f_start = config.width_start ** _exp
        f_stop = config.width_stop ** _exp
        if f_start != f_stop:
            _coeff_a = (delay_start - delay_stop) / (f_start - f_stop)
            _coeff_b = delay_start - _coeff_a * f_start

    def _apply_delay(i: int) -> None:
        if use_table:
            raw = float(np.interp(widths[i], _table_pw, _table_delay))
        elif sweep_delay:
            raw = _coeff_a * widths[i] ** _exp + _coeff_b
        else:
            return
        delay = round(raw / 8) * 8
        for ch in channels:
            instrument.set_trigger_delay(delay, channel=ch)

    return _apply_delay


def _build_delay_applier_interval(
    config: IntervalSweepConfig,
    intervals: list[float],
    channels: list[int],
    instrument: PulseInstrument,
) -> Callable[[int], None]:
    """Build _apply_delay function for interval sweep (same logic as run_interval_sweep)."""
    use_table = config.delay_mode == "table" and config.delay_table is not None

    _table_iv: np.ndarray | None = None
    _table_delay: np.ndarray | None = None
    if use_table:
        sorted_table = sorted(config.delay_table, key=lambda r: r[0])
        _table_iv = np.array([r[0] for r in sorted_table])
        _table_delay = np.array([r[1] for r in sorted_table], dtype=float)

    delay_start = config.trigger_delay
    delay_stop = config.trigger_delay_stop
    sweep_delay = delay_stop is not None and delay_stop != delay_start

    _coeff_a = _coeff_b = 0.0
    _exp = config.delay_exponent
    if not use_table and sweep_delay:
        f_start = config.interval_start ** _exp
        f_stop = config.interval_stop ** _exp
        if f_start != f_stop:
            _coeff_a = (delay_start - delay_stop) / (f_start - f_stop)
            _coeff_b = delay_start - _coeff_a * f_start

    def _apply_delay(i: int) -> None:
        if use_table:
            raw = float(np.interp(intervals[i], _table_iv, _table_delay))
        elif sweep_delay:
            raw = _coeff_a * intervals[i] ** _exp + _coeff_b
        else:
            return
        delay = round(raw / 8) * 8
        for ch in channels:
            instrument.set_trigger_delay(delay, channel=ch)

    return _apply_delay


# ================================================================== #
#  Main orchestration: Width Sweep
# ================================================================== #

def run_step_synced_sweep(
    sweep_config: SweepConfig,
    step_sync_config: StepSyncConfig,
    *,
    channels: list[int] | None = None,
    upload_callback: Callable[[int, int], None] | None = None,
    sweep_callback: Callable[[int, int], None] | None = None,
    step_callback: Callable[[float, int, str], None] | None = None,
) -> None:
    """Orchestrate step-function-synced width sweep cycles.

    Flow
    ----
    1. Connect to AWG and DMM.
    2. Validate that sweep segments fit within the step sequence.
    3. Upload all waveform segments to AWG (once).
    4. Set DC 0V (no pulses until sweep starts).
    5. For each cycle:
       a. ``_wait_for_sequence_start()`` — block until voltage is low.
       b. Monitoring phase (steps 0..sweep_start_step-1): verify signal.
       c. Sweep phase: for each step, detect transition → select segment.
       d. Set DC 0V between cycles.
    6. Teardown and close (always, via ``finally``).

    Ctrl+C interrupts gracefully at any point.
    """
    channels = channels or [1]

    # --- Generate widths and validate ---
    widths = _generate_widths(
        sweep_config.width_start,
        sweep_config.width_stop,
        sweep_config.width_step,
        step_zones=sweep_config.step_zones,
    )
    sweep_segments = len(widths)
    available_steps = step_sync_config.total_steps - step_sync_config.sweep_start_step

    if sweep_segments > available_steps:
        raise ValueError(
            f"Sweep has {sweep_segments} segments but only {available_steps} "
            f"steps available after sweep_start_step="
            f"{step_sync_config.sweep_start_step} "
            f"(total_steps={step_sync_config.total_steps})"
        )

    levels, thresholds = _compute_step_levels_and_thresholds(step_sync_config)

    instrument = PulseInstrument(sweep_config.visa_address)
    dmm = Multimeter(step_sync_config.dmm_visa_address)
    dmm.configure_dc_voltage()

    try:
        # --- Upload waveforms (once) ---
        logger.info("Uploading %d waveform segments...", sweep_segments)
        for ch in channels:
            instrument.setup_arbitrary(
                sweep_config, widths, channel=ch, callback=upload_callback,
            )
        logger.info("Waveform upload complete.")

        # Set DC 0V after upload
        for ch in channels:
            instrument.set_between_cycles_dc_zero(channel=ch)

        # Build delay applier
        apply_delay = _build_delay_applier_width(
            sweep_config, widths, channels, instrument,
        )

        # --- Cycle loop ---
        cycle = 0
        max_cycles = step_sync_config.num_cycles

        while max_cycles == 0 or cycle < max_cycles:
            cycle += 1
            label = f"{cycle}/{max_cycles}" if max_cycles > 0 else f"{cycle}/inf"
            logger.info("=== Cycle %s ===", label)

            _wait_for_sequence_start(
                dmm, step_sync_config, callback=step_callback,
            )

            _run_step_synced_loop(
                instrument, dmm,
                sweep_config, step_sync_config,
                levels, thresholds,
                sweep_segments, apply_delay,
                channels=channels,
                sweep_callback=sweep_callback,
                step_callback=step_callback,
            )

            logger.info("Sweep cycle %s complete.", label)

            # Set DC 0V between cycles
            for ch in channels:
                instrument.set_between_cycles_dc_zero(channel=ch)

    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C).")
    finally:
        for ch in channels:
            instrument.teardown(channel=ch)
        instrument.close()
        dmm.close()
        logger.info("All instruments closed.")


# ================================================================== #
#  Main orchestration: Interval Sweep (Pump-Probe)
# ================================================================== #

def run_step_synced_interval_sweep(
    interval_config: IntervalSweepConfig,
    step_sync_config: StepSyncConfig,
    *,
    channels: list[int] | None = None,
    upload_callback: Callable[[int, int], None] | None = None,
    sweep_callback: Callable[[int, int], None] | None = None,
    step_callback: Callable[[float, int, str], None] | None = None,
) -> None:
    """Orchestrate step-function-synced interval sweep cycles.

    Same flow as ``run_step_synced_sweep()`` but for pump-probe interval sweep.
    Uses ``setup_pump_probe_arbitrary()`` instead of ``setup_arbitrary()``.
    """
    channels = channels or [1]

    # --- Generate intervals and validate ---
    intervals = _generate_intervals(
        interval_config.interval_start,
        interval_config.interval_stop,
        interval_config.interval_step,
        step_zones=interval_config.step_zones,
    )
    sweep_segments = len(intervals)
    available_steps = step_sync_config.total_steps - step_sync_config.sweep_start_step

    if sweep_segments > available_steps:
        raise ValueError(
            f"Interval sweep has {sweep_segments} segments but only "
            f"{available_steps} steps available after sweep_start_step="
            f"{step_sync_config.sweep_start_step} "
            f"(total_steps={step_sync_config.total_steps})"
        )

    levels, thresholds = _compute_step_levels_and_thresholds(step_sync_config)

    instrument = PulseInstrument(interval_config.visa_address)
    dmm = Multimeter(step_sync_config.dmm_visa_address)
    dmm.configure_dc_voltage()

    try:
        # --- Upload pump-probe waveforms (once) ---
        logger.info("Uploading %d pump-probe segments...", sweep_segments)
        for ch in channels:
            instrument.setup_pump_probe_arbitrary(
                interval_config,
                interval_config.pulse_width,
                intervals,
                channel=ch,
                callback=upload_callback,
            )
        logger.info("Waveform upload complete.")

        # Set DC 0V after upload
        for ch in channels:
            instrument.set_between_cycles_dc_zero(channel=ch)

        # Build delay applier
        apply_delay = _build_delay_applier_interval(
            interval_config, intervals, channels, instrument,
        )

        # --- Cycle loop ---
        cycle = 0
        max_cycles = step_sync_config.num_cycles

        while max_cycles == 0 or cycle < max_cycles:
            cycle += 1
            label = f"{cycle}/{max_cycles}" if max_cycles > 0 else f"{cycle}/inf"
            logger.info("=== Cycle %s ===", label)

            _wait_for_sequence_start(
                dmm, step_sync_config, callback=step_callback,
            )

            _run_step_synced_loop(
                instrument, dmm,
                interval_config, step_sync_config,
                levels, thresholds,
                sweep_segments, apply_delay,
                channels=channels,
                sweep_callback=sweep_callback,
                step_callback=step_callback,
            )

            logger.info("Interval sweep cycle %s complete.", label)

            # Set DC 0V between cycles
            for ch in channels:
                instrument.set_between_cycles_dc_zero(channel=ch)

    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C).")
    finally:
        for ch in channels:
            instrument.teardown(channel=ch)
        instrument.close()
        dmm.close()
        logger.info("All instruments closed.")
