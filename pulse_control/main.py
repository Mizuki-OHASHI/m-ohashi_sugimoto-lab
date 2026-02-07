"""Pulse-width sweep CLI entry point for the Agilent 81180A AWG.

Usage:
    python -m pulse_control.main [config.toml]
"""

from __future__ import annotations

import sys
from logging import getLogger
from pathlib import Path

from config import SweepConfig
from core import PulseInstrument, run_sweep
from log_setup import setup_logging

logger = getLogger(__name__)

DEFAULT_CONFIG = Path("sweep_config.toml")


def main(config_path: str | None = None) -> None:
    setup_logging()

    if config_path is None:
        if len(sys.argv) > 1:
            config_path = sys.argv[1]
        else:
            config_path = str(DEFAULT_CONFIG)

    logger.info("Config file: %s", config_path)
    config = SweepConfig.from_toml(config_path)

    errors = config.validate()
    if errors:
        logger.error("Config validation failed:")
        for e in errors:
            logger.error("  - %s", e)
        sys.exit(1)

    logger.info("Config OK.")
    logger.info("  VISA: %s", config.visa_address)
    logger.info("  V_on=%s V, V_off=%s V", config.v_on, config.v_off)
    logger.info(
        "  Width: %s -> %s (step %s) s",
        config.width_start, config.width_stop, config.width_step,
    )
    logger.info("  frequency=%s Hz (period=%s s)", config.frequency, config.period)
    logger.info("  trigger_delay=%s points", config.trigger_delay)
    logger.info("  wait_time=%s s", config.wait_time)

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
        instrument.setup(config)
        run_sweep(config, instrument)
        instrument.teardown()
    finally:
        instrument.close()

    logger.info("Sweep complete.")


if __name__ == "__main__":
    main()
