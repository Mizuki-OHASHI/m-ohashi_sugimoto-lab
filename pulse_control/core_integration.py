"""Integrated sweep controller: synchronizes AWG sweep with external voltage ramp.

Monitors DC voltage via Agilent 34401A multimeter and detects the start of a
linear voltage ramp (-10 V -> 10 V).  Uses early ramp data to predict
the sweep start time via linear regression, then runs a pulse width sweep
while the ramp is still in progress.

Usage::

    python -m pulse_control integration configs/config_integration.toml
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from logging import getLogger
from typing import Callable

import numpy as np

from config import SweepConfig
from core import PulseInstrument, _generate_widths, run_sweep
from core_34401A import Multimeter

logger = getLogger(__name__)


@dataclass
class RampPrediction:
    """Result of linear ramp fitting."""

    sweep_start_time: float  # Absolute epoch time to start sweep
    slope: float             # Ramp rate [V/s]
    intercept: float         # V at t=0 of fit data (relative)
    r_squared: float         # Fit quality (1.0 = perfect)
    n_points: int            # Number of data points used for fit


@dataclass
class IntegrationConfig:
    """Configuration for voltage-triggered integrated sweep."""

    dmm_visa_address: str

    trigger_start_voltage: float = -9.8   # Start collecting fit data [V]
    trigger_end_voltage: float = -9.2     # Stop collecting, do fit [V]
    sweep_start_voltage: float = -9.0     # Predict when to start sweep [V]

    poll_interval: float = 1.0            # Interval between DMM reads [s]
    num_cycles: int = 0                   # 0 = infinite (Ctrl+C to stop)

    def validate(self) -> list[str]:
        """Validate parameter consistency. Returns list of error messages."""
        errors: list[str] = []

        if self.trigger_start_voltage >= self.trigger_end_voltage:
            errors.append(
                f"trigger_start_voltage ({self.trigger_start_voltage}) must be "
                f"< trigger_end_voltage ({self.trigger_end_voltage})"
            )
        if self.trigger_end_voltage >= self.sweep_start_voltage:
            errors.append(
                f"trigger_end_voltage ({self.trigger_end_voltage}) must be "
                f"< sweep_start_voltage ({self.sweep_start_voltage})"
            )
        if self.poll_interval <= 0:
            errors.append("poll_interval must be positive")
        if self.num_cycles < 0:
            errors.append("num_cycles must be >= 0 (0 = infinite)")

        for e in errors:
            logger.warning("Validation error: %s", e)
        return errors


# ================================================================== #
#  Ramp start detection
# ================================================================== #

def detect_ramp_start(
    dmm: Multimeter,
    config: IntegrationConfig,
    *,
    callback: Callable[[float, str], None] | None = None,
) -> RampPrediction:
    """Detect the start of a voltage ramp and predict sweep start time.

    Algorithm
    ---------
    1. **waiting_low**: Wait until voltage drops below ``trigger_start_voltage``.
       This ensures we don't trigger on a ramp already in progress.
    2. **waiting_trigger**: Wait until voltage crosses ``trigger_start_voltage``
       upward — this is the beginning of a new ramp.
    3. **collecting**: Accumulate ``(time, voltage)`` pairs until voltage
       reaches ``trigger_end_voltage``.
    4. **fitting**: Linear regression on collected data, predict when voltage
       reaches ``sweep_start_voltage``.

    Parameters
    ----------
    dmm : Multimeter
        Must have ``configure_dc_voltage()`` already called.
    config : IntegrationConfig
    callback : (voltage, phase) -> None
        ``phase`` is ``"waiting_low"``, ``"waiting_trigger"``, or
        ``"collecting"``.

    Returns
    -------
    RampPrediction
        Contains ``sweep_start_time`` (absolute epoch) and fit diagnostics.
    """
    # Phase 1: Wait for voltage below trigger_start (skip current ramp if any)
    logger.info(
        "Waiting for voltage < %.2f V (ensuring we are before a new ramp)...",
        config.trigger_start_voltage,
    )
    while True:
        voltage = dmm.read()
        logger.debug("Voltage: %.4f V (waiting for < %.2f V)",
                      voltage, config.trigger_start_voltage)
        if callback is not None:
            callback(voltage, "waiting_low")
        if voltage < config.trigger_start_voltage:
            logger.info("Voltage is below %.2f V (%.4f V). Ready for trigger.",
                        config.trigger_start_voltage, voltage)
            break
        time.sleep(config.poll_interval)

    # Phase 2: Wait for upward crossing of trigger_start
    logger.info(
        "Waiting for voltage >= %.2f V (ramp start)...",
        config.trigger_start_voltage,
    )
    times: list[float] = []
    voltages: list[float] = []

    while True:
        voltage = dmm.read()
        logger.debug("Voltage: %.4f V (waiting for >= %.2f V)",
                      voltage, config.trigger_start_voltage)
        if callback is not None:
            callback(voltage, "waiting_trigger")
        if voltage >= config.trigger_start_voltage:
            times.append(time.time())
            voltages.append(voltage)
            logger.info("Ramp start detected at %.4f V", voltage)
            break
        time.sleep(config.poll_interval)

    # Phase 3: Collect data until trigger_end
    logger.info(
        "Collecting ramp data (%.2f V -> %.2f V)...",
        config.trigger_start_voltage,
        config.trigger_end_voltage,
    )
    while True:
        time.sleep(config.poll_interval)
        voltage = dmm.read()
        times.append(time.time())
        voltages.append(voltage)
        logger.debug("Voltage: %.4f V (%d points collected)",
                      voltage, len(times))
        if callback is not None:
            callback(voltage, "collecting")
        if voltage >= config.trigger_end_voltage:
            break

    # Phase 4: Linear regression
    t_arr = np.array(times)
    v_arr = np.array(voltages)
    t_rel = t_arr - t_arr[0]  # relative times for numerical stability

    slope, intercept = np.polyfit(t_rel, v_arr, 1)

    # R² calculation
    v_pred = slope * t_rel + intercept
    ss_res = float(np.sum((v_arr - v_pred) ** 2))
    ss_tot = float(np.sum((v_arr - np.mean(v_arr)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    logger.info(
        "Linear fit: slope=%.6f V/s, intercept=%.4f V, R²=%.6f (%d points)",
        slope, intercept, r_squared, len(times),
    )

    if r_squared < 0.99:
        logger.warning("R² = %.4f — ramp may not be linear", r_squared)

    if slope <= 0:
        logger.warning(
            "Slope = %.6f V/s is non-positive — unexpected ramp direction",
            slope,
        )

    # Predict sweep start time
    t_sweep_rel = (config.sweep_start_voltage - intercept) / slope
    sweep_start_time = t_arr[0] + t_sweep_rel

    now = time.time()
    wait_seconds = max(0.0, sweep_start_time - now)
    logger.info(
        "Predicted sweep start: %.1f s from now (at %.2f V)",
        wait_seconds,
        config.sweep_start_voltage,
    )

    return RampPrediction(
        sweep_start_time=sweep_start_time,
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        n_points=len(times),
    )


# ================================================================== #
#  Main orchestration
# ================================================================== #

def run_integrated_sweep(
    sweep_config: SweepConfig,
    integration_config: IntegrationConfig,
    *,
    channels: list[int] | None = None,
    upload_callback: Callable[[int, int], None] | None = None,
    sweep_callback: Callable[[int, int], None] | None = None,
    ramp_callback: Callable[[float, str], None] | None = None,
) -> None:
    """Orchestrate voltage-triggered sweep cycles.

    Flow
    ----
    1. Connect to AWG and DMM.
    2. Upload all waveform segments to AWG (once).
    3. For each cycle:
       a. ``detect_ramp_start()`` — block until ramp is detected.
       b. Sleep until predicted sweep start time.
       c. ``run_sweep()``
    4. Teardown and close (always, via ``finally``).

    Ctrl+C interrupts gracefully at any point.
    """
    channels = channels or [1]

    instrument = PulseInstrument(sweep_config.visa_address)
    dmm = Multimeter(integration_config.dmm_visa_address)
    dmm.configure_dc_voltage()

    try:
        # --- Phase 1: Upload waveforms (once) ---
        widths = _generate_widths(
            sweep_config.width_start,
            sweep_config.width_stop,
            sweep_config.width_step,
            step_zones=sweep_config.step_zones,
        )
        logger.info("Uploading %d waveform segments...", len(widths))
        for ch in channels:
            instrument.setup_arbitrary(
                sweep_config, widths, channel=ch, callback=upload_callback,
            )
        logger.info("Waveform upload complete.")

        # --- Phase 2: Cycle loop ---
        cycle = 0
        max_cycles = integration_config.num_cycles

        while max_cycles == 0 or cycle < max_cycles:
            cycle += 1
            label = f"{cycle}/{max_cycles}" if max_cycles > 0 else f"{cycle}/inf"
            logger.info("=== Cycle %s ===", label)

            prediction = detect_ramp_start(
                dmm, integration_config, callback=ramp_callback,
            )
            logger.info(
                "Ramp detected (slope=%.6f V/s, R²=%.6f, %d pts). "
                "Waiting %.1f s before sweep...",
                prediction.slope,
                prediction.r_squared,
                prediction.n_points,
                max(0.0, prediction.sweep_start_time - time.time()),
            )

            # Wait until predicted sweep start time
            now = time.time()
            if prediction.sweep_start_time > now:
                time.sleep(prediction.sweep_start_time - now)

            # Restore USER mode before sweep (2nd cycle onward)
            if cycle > 1:
                for ch in channels:
                    instrument.restore_user_mode(sweep_config, channel=ch)

            # Run sweep
            logger.info("Starting sweep (cycle %s)...", label)
            run_sweep(
                sweep_config,
                instrument,
                callback=sweep_callback,
                channels=channels,
            )
            logger.info("Sweep cycle %s complete.", label)

            # Set DC 0V during wait (no pulses between cycles)
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
