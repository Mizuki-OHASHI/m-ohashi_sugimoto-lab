"""Pulse control CLI entry point for the Agilent 81180A AWG.

Usage:
    python -m pulse_control pulse [config.toml]   # Simple pulse output
    python -m pulse_control sweep [config.toml]   # Pulse width sweep
    python -m pulse_control dc [visa_address]      # DC 0V (safe state)
    python -m pulse_control [config.toml]          # Default: sweep (backward compat)
"""

from __future__ import annotations

import sys
import time
from logging import getLogger
from pathlib import Path

from config import DEFAULT_VISA_ADDRESS, PulseConfig, SweepConfig
from core import PulseInstrument, _generate_widths, run_sweep
from log_setup import setup_logging

logger = getLogger(__name__)

DEFAULT_SWEEP_CONFIG = Path("sweep_config.toml")
DEFAULT_PULSE_CONFIG = Path("pulse_config.toml")


def main_pulse(config_path: str) -> None:
    """Run simple pulse mode."""
    logger.info("Config file: %s", config_path)
    config = PulseConfig.from_toml(config_path)

    errors = config.validate()
    if errors:
        logger.error("Config validation failed:")
        for e in errors:
            logger.error("  - %s", e)
        sys.exit(1)

    logger.info("=== Simple Pulse Mode ===")
    logger.info("  VISA: %s", config.visa_address)
    logger.info("  V_on=%s V, V_off=%s V", config.v_on, config.v_off)
    logger.info("  Pulse width: %s s", config.pulse_width)
    logger.info("  Frequency=%s Hz (period=%s s)", config.frequency, config.period)
    logger.info("  Trigger delay=%s points", config.trigger_delay)

    logger.info("Checking connection...")
    try:
        idn = PulseInstrument.check_connection(config.visa_address)
        logger.info("  OK: %s", idn)
    except Exception as exc:
        logger.exception("Connection failed: %s", exc)
        sys.exit(1)

    instrument = PulseInstrument(config.visa_address)
    try:
        instrument.setup(config, config.pulse_width)
        logger.info("Pulse output is ON. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        instrument.teardown()
        instrument.close()

    logger.info("Done.")


def main_sweep(config_path: str) -> None:
    """Run pulse width sweep mode."""
    logger.info("Config file: %s", config_path)
    config = SweepConfig.from_toml(config_path)

    errors = config.validate()
    if errors:
        logger.error("Config validation failed:")
        for e in errors:
            logger.error("  - %s", e)
        sys.exit(1)

    logger.info("=== Pulse Width Sweep Mode ===")
    logger.info("  VISA: %s", config.visa_address)
    logger.info("  V_on=%s V, V_off=%s V", config.v_on, config.v_off)
    logger.info(
        "  Width: %s -> %s (step %s) s",
        config.width_start, config.width_stop, config.width_step,
    )
    logger.info("  Frequency=%s Hz (period=%s s)", config.frequency, config.period)
    logger.info("  Trigger delay=%s points", config.trigger_delay)
    logger.info("  Wait time=%s s", config.wait_time)
    logger.info("  Waveform mode=%s", config.waveform_mode)

    logger.info("Checking connection...")
    try:
        idn = PulseInstrument.check_connection(config.visa_address)
        logger.info("  OK: %s", idn)
    except Exception as exc:
        logger.exception("Connection failed: %s", exc)
        sys.exit(1)

    logger.info("Starting sweep...")
    instrument = PulseInstrument(config.visa_address)
    try:
        if config.waveform_mode == "arbitrary":
            widths = _generate_widths(config.width_start, config.width_stop, config.width_step)
            instrument.setup_arbitrary(config, widths)
        else:
            instrument.setup(config, config.width_start)
        run_sweep(config, instrument)
        instrument.teardown()
    finally:
        instrument.close()

    logger.info("Sweep complete.")


def main_dc(visa_address: str) -> None:
    """Set output to DC 0V (safe state)."""
    logger.info("=== DC 0V Mode ===")
    logger.info("  VISA: %s", visa_address)

    logger.info("Checking connection...")
    try:
        idn = PulseInstrument.check_connection(visa_address)
        logger.info("  OK: %s", idn)
    except Exception as exc:
        logger.exception("Connection failed: %s", exc)
        sys.exit(1)

    instrument = PulseInstrument(visa_address)
    try:
        instrument.set_dc_zero()
    finally:
        instrument.close()

    logger.info("Done.")


def main() -> None:
    setup_logging()

    args = sys.argv[1:]

    if args and args[0] in ("pulse", "sweep", "dc"):
        mode = args[0]
        rest = args[1:]
    else:
        mode = "sweep"
        rest = args

    if mode == "dc":
        visa_address = rest[0] if rest else DEFAULT_VISA_ADDRESS
        main_dc(visa_address)
    elif mode == "pulse":
        config_path = rest[0] if rest else str(DEFAULT_PULSE_CONFIG)
        main_pulse(config_path)
    else:
        config_path = rest[0] if rest else str(DEFAULT_SWEEP_CONFIG)
        main_sweep(config_path)


if __name__ == "__main__":
    main()
