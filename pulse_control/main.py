"""Pulse control CLI entry point for the Agilent 81180A AWG.

Usage:
    python -m pulse_control pulse [config.toml]         # Simple pulse output
    python -m pulse_control sweep [config.toml]         # Pulse width sweep
    python -m pulse_control integration [config.toml]   # Voltage-triggered sweep
    python -m pulse_control dc [visa_address]            # DC 0V (safe state)
    python -m pulse_control [config.toml]                # Default: sweep (backward compat)
"""

from __future__ import annotations

import sys
import time
from logging import getLogger
from pathlib import Path

from config import DEFAULT_VISA_ADDRESS, PulseConfig, SweepConfig, load_unified_toml
from core import PulseInstrument, _generate_widths, run_sweep
from log_setup import setup_logging

logger = getLogger(__name__)

DEFAULT_CONFIG = Path("configs/config.toml")


def main_pulse(config_path: str) -> None:
    """Run simple pulse mode."""
    logger.info("Config file: %s", config_path)
    data = load_unified_toml(config_path)
    common = data.get("common", {})
    sp = data.get("simple_pulse", {})
    config = PulseConfig(
        visa_address=data.get("connection", {}).get("visa_address", DEFAULT_VISA_ADDRESS),
        v_on=common.get("v_on", 0.0),
        v_off=common.get("v_off", -1.0),
        frequency=common.get("frequency", 10_000_000.0),
        trigger_delay=int(common.get("trigger_delay", 0)),
        resolution_n=int(common.get("resolution_n", 1)),
        pulse_width=sp.get("pulse_width", 1e-8),
    )

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
    data = load_unified_toml(config_path)
    common = data.get("common", {})
    ws = data.get("width_sweep", {})
    config = SweepConfig(
        visa_address=data.get("connection", {}).get("visa_address", DEFAULT_VISA_ADDRESS),
        v_on=common.get("v_on", 0.0),
        v_off=common.get("v_off", -1.0),
        frequency=common.get("frequency", 10_000_000.0),
        trigger_delay=int(common.get("trigger_delay", 0)),
        resolution_n=int(common.get("resolution_n", 1)),
        width_start=ws.get("width_start", 1e-8),
        width_stop=ws.get("width_stop", 5e-8),
        width_step=ws.get("width_step", 5e-9),
        wait_time=ws.get("wait_time", 1.0),
        settling_time=ws.get("settling_time", 0.0),
        trigger_delay_stop=ws.get("trigger_delay_stop"),
        delay_exponent=ws.get("delay_exponent", 1.0),
    )

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
    logger.info("  Waveform mode=arbitrary")

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
        widths = _generate_widths(
            config.width_start, config.width_stop, config.width_step,
            step_zones=config.step_zones,
        )
        instrument.setup_arbitrary(config, widths)
        run_sweep(config, instrument)
        instrument.teardown()
    finally:
        instrument.close()

    logger.info("Sweep complete.")


def main_integration(config_path: str) -> None:
    """Run voltage-triggered integrated sweep mode."""
    from core_34401A import Multimeter
    from core_integration import IntegrationConfig, run_integrated_sweep

    logger.info("Config file: %s", config_path)
    data = load_unified_toml(config_path)
    common = data.get("common", {})
    ws = data.get("width_sweep", {})
    integ = data.get("integration", {})

    sweep_config = SweepConfig(
        visa_address=data.get("connection", {}).get("visa_address", DEFAULT_VISA_ADDRESS),
        v_on=common.get("v_on", 0.0),
        v_off=common.get("v_off", -1.0),
        frequency=common.get("frequency", 10_000_000.0),
        trigger_delay=int(common.get("trigger_delay", 0)),
        resolution_n=int(common.get("resolution_n", 1)),
        width_start=ws.get("width_start", 1e-8),
        width_stop=ws.get("width_stop", 5e-8),
        width_step=ws.get("width_step", 5e-9),
        wait_time=ws.get("wait_time", 1.0),
        settling_time=ws.get("settling_time", 0.0),
        trigger_delay_stop=ws.get("trigger_delay_stop"),
        delay_exponent=ws.get("delay_exponent", 1.0),
        delay_mode=ws.get("delay_mode", "exponent"),
        delay_table=ws.get("delay_table"),
    )

    integration_config = IntegrationConfig(
        dmm_visa_address=integ.get("dmm_visa_address", "ASRL3::INSTR"),
        trigger_start_voltage=integ.get("trigger_start_voltage", -9.8),
        trigger_end_voltage=integ.get("trigger_end_voltage", -9.2),
        sweep_start_voltage=integ.get("sweep_start_voltage", -9.0),
        poll_interval=integ.get("poll_interval", 1.0),
        num_cycles=int(integ.get("num_cycles", 0)),
    )

    # Validate both configs
    errors = sweep_config.validate() + integration_config.validate()
    if errors:
        logger.error("Config validation failed:")
        for e in errors:
            logger.error("  - %s", e)
        sys.exit(1)

    logger.info("=== Voltage-Triggered Integration Mode ===")
    logger.info("  AWG VISA: %s", sweep_config.visa_address)
    logger.info("  DMM VISA: %s", integration_config.dmm_visa_address)
    logger.info("  V_on=%s V, V_off=%s V", sweep_config.v_on, sweep_config.v_off)
    logger.info(
        "  Width: %s -> %s (step %s) s",
        sweep_config.width_start, sweep_config.width_stop, sweep_config.width_step,
    )
    logger.info("  Frequency=%s Hz (period=%s s)", sweep_config.frequency, sweep_config.period)
    logger.info(
        "  Ramp detection: trigger %.2f V -> %.2f V, sweep at %.2f V",
        integration_config.trigger_start_voltage,
        integration_config.trigger_end_voltage,
        integration_config.sweep_start_voltage,
    )
    logger.info("  Poll interval=%.1f s", integration_config.poll_interval)
    logger.info(
        "  Cycles=%s",
        integration_config.num_cycles if integration_config.num_cycles > 0 else "infinite",
    )

    logger.info("Checking AWG connection...")
    try:
        idn = PulseInstrument.check_connection(sweep_config.visa_address)
        logger.info("  AWG OK: %s", idn)
    except Exception as exc:
        logger.exception("AWG connection failed: %s", exc)
        sys.exit(1)

    logger.info("Checking DMM connection...")
    try:
        idn = Multimeter.check_connection(integration_config.dmm_visa_address)
        logger.info("  DMM OK: %s", idn)
    except Exception as exc:
        logger.exception("DMM connection failed: %s", exc)
        sys.exit(1)

    logger.info("Starting integrated sweep...")
    run_integrated_sweep(sweep_config, integration_config)
    logger.info("Integrated sweep complete.")


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

    if args and args[0] in ("pulse", "sweep", "integration", "dc"):
        mode = args[0]
        rest = args[1:]
    else:
        mode = "sweep"
        rest = args

    if mode == "dc":
        visa_address = rest[0] if rest else DEFAULT_VISA_ADDRESS
        main_dc(visa_address)
    elif mode == "pulse":
        config_path = rest[0] if rest else str(DEFAULT_CONFIG)
        main_pulse(config_path)
    elif mode == "integration":
        config_path = rest[0] if rest else str(DEFAULT_CONFIG)
        main_integration(config_path)
    else:
        config_path = rest[0] if rest else str(DEFAULT_CONFIG)
        main_sweep(config_path)


if __name__ == "__main__":
    main()
