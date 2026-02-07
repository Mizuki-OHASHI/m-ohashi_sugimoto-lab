"""Sweep configuration module for Agilent 81180A AWG."""

from __future__ import annotations

from dataclasses import dataclass, fields
from logging import getLogger
from pathlib import Path

import toml

logger = getLogger(__name__)


DEFAULT_VISA_ADDRESS = "TCPIP0::192.168.0.251::5025::SOCKET"
# NOTE: Format is TCPIP0::[IP address]::5025::SOCKET
# - Check IP address on the instrument: Utility > Remote Interface > LAN
# - To verify LAN connectivity, run `ping [IP address]` in PowerShell


@dataclass
class SweepConfig:
    """Pulse width sweep configuration for Agilent 81180A AWG."""

    # Connection
    visa_address: str

    # Pulse shape
    v_on: float        # Voltage during pulse ON [V]
    v_off: float       # Voltage during pulse OFF (base) [V]

    # Sweep parameters
    width_start: float  # Pulse width start [s]
    width_stop: float   # Pulse width stop [s]
    width_step: float   # Pulse width step [s]

    # AWG parameters
    frequency: float    # Repetition frequency [Hz] (width controlled via duty cycle)
    trigger_delay: int  # Trigger delay [sample points] (multiple of 8)
    wait_time: float    # Wait time between sweep steps [s]

    @property
    def period(self) -> float:
        """Period [s] = 1 / frequency."""
        return 1.0 / self.frequency

    @classmethod
    def from_toml(cls, path: str | Path) -> SweepConfig:
        """Load configuration from a TOML file.

        Either frequency or period can be specified in the [awg] section.
        If both are present, frequency takes precedence.
        """
        logger.info("Loading TOML: %s", path)
        data = toml.load(path)
        # Flatten sections into a single dict
        flat: dict = {}
        for value in data.values():
            if isinstance(value, dict):
                flat.update(value)
            else:
                flat[str(value)] = value
        # Convert period to frequency if needed
        if "period" in flat and "frequency" not in flat:
            flat["frequency"] = 1.0 / flat.pop("period")
        elif "period" in flat:
            flat.pop("period")  # frequency takes precedence
        # Keep only valid dataclass field names
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in flat.items() if k in valid_keys}
        return cls(**filtered)

    def to_toml(self, path: str | Path) -> None:
        """Export to a TOML file (includes both frequency and period)."""
        logger.info("Writing TOML: %s", path)
        data = {
            "connection": {
                "visa_address": self.visa_address,
            },
            "pulse": {
                "v_on": self.v_on,
                "v_off": self.v_off,
            },
            "sweep": {
                "width_start": self.width_start,
                "width_stop": self.width_stop,
                "width_step": self.width_step,
                "wait_time": self.wait_time,
            },
            "awg": {
                "frequency": self.frequency,
                "period": self.period,
                "trigger_delay": self.trigger_delay,
            },
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            toml.dump(data, f)

    def validate(self) -> list[str]:
        """Validate parameter consistency. Returns a list of error messages (empty if OK)."""
        logger.info("Running validation")
        errors: list[str] = []

        if self.width_start <= 0:
            errors.append("width_start must be positive")
        if self.width_stop <= 0:
            errors.append("width_stop must be positive")
        if self.width_step <= 0:
            errors.append("width_step must be positive")

        if self.frequency <= 0:
            errors.append("frequency must be positive")

        if self.trigger_delay < 0:
            errors.append("trigger_delay must be >= 0")
        if self.trigger_delay % 8 != 0:
            errors.append("trigger_delay must be a multiple of 8")

        if self.wait_time < 0:
            errors.append("wait_time must be >= 0")

        # Duty cycle range check (VBA UpdateSQR: 0.1–99.9%)
        for width in [self.width_start, self.width_stop]:
            dcycle = width * self.frequency * 100
            if dcycle < 0.1 or dcycle > 99.9:
                errors.append(
                    f"Duty cycle = {dcycle:.2f}% at width {width:.6f} s "
                    "is out of range (0.1–99.9%)"
                )

        # Amplitude/offset range check (same limits as VBA UpdateSQR)
        ampl = (self.v_on - self.v_off) / 2
        if ampl < 0.05 or ampl > 2:
            errors.append(
                f"Amplitude = {ampl:.4f} V is out of range (0.05–2.0 V)"
            )
        offs = (self.v_on + self.v_off) / 4
        if abs(offs) > 1.5:
            errors.append(
                f"Offset = {offs:.4f} V is out of range (-1.5–1.5 V)"
            )

        for e in errors:
            logger.warning("Validation error: %s", e)

        return errors
