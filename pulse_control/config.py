"""Configuration module for Agilent 81180A AWG."""

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
class BaseConfig:
    """Common parameters shared by all operation modes."""

    # Connection
    visa_address: str

    # Pulse shape
    v_on: float        # Voltage during pulse ON [V]
    v_off: float       # Voltage during pulse OFF (base) [V]

    # AWG parameters
    frequency: float    # Repetition frequency [Hz] (width controlled via duty cycle)
    trigger_delay: int  # Trigger delay [sample points] (multiple of 8)
    resolution_n: int  # Delay resolution multiplier (points_per_period × n)

    @property
    def period(self) -> float:
        """Period [s] = 1 / frequency."""
        return 1.0 / self.frequency

    def _validate_common(self) -> list[str]:
        """Validate fields common to all modes."""
        errors: list[str] = []

        if self.frequency <= 0:
            errors.append("frequency must be positive")

        if self.trigger_delay < 0:
            errors.append("trigger_delay must be >= 0")
        if self.trigger_delay % 8 != 0:
            errors.append("trigger_delay must be a multiple of 8")

        # Amplitude/offset range check (same limits as VBA UpdateSQR)
        ampl = abs(self.v_on - self.v_off) / 2
        if ampl < 0.05 or ampl > 2:
            errors.append(
                f"Amplitude = {ampl:.4f} V is out of range (0.05–2.0 V)"
            )
        offs = (self.v_on + self.v_off) / 4
        if abs(offs) > 1.5:
            errors.append(
                f"Offset = {offs:.4f} V is out of range (-1.5–1.5 V)"
            )

        return errors

    @staticmethod
    def _load_and_flatten_toml(path: str | Path) -> dict:
        """Load TOML and flatten sections; handle period -> frequency conversion."""
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
        flat.setdefault("resolution_n", 1)
        return flat


@dataclass
class PulseConfig(BaseConfig):
    """Simple pulse output configuration for Agilent 81180A AWG."""

    pulse_width: float  # Pulse width [s]
    waveform_mode: str = "square"  # "square" or "arbitrary"

    @classmethod
    def from_toml(cls, path: str | Path) -> PulseConfig:
        """Load configuration from a TOML file."""
        flat = cls._load_and_flatten_toml(path)
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
                "pulse_width": self.pulse_width,
            },
            "awg": {
                "frequency": self.frequency,
                "period": self.period,
                "trigger_delay": self.trigger_delay,
                "waveform_mode": self.waveform_mode,
            },
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            toml.dump(data, f)

    def validate(self) -> list[str]:
        """Validate parameter consistency. Returns a list of error messages (empty if OK)."""
        logger.info("Running validation")
        errors = self._validate_common()

        if self.pulse_width <= 0:
            errors.append("pulse_width must be positive")

        if self.waveform_mode not in ("square", "arbitrary"):
            errors.append(
                f"waveform_mode must be 'square' or 'arbitrary', got '{self.waveform_mode}'"
            )

        # Square mode cannot handle V_ON < V_OFF (81180A ignores amplitude sign and :PHASe)
        if self.waveform_mode == "square" and self.v_on < self.v_off:
            errors.append(
                "Square mode does not support V_ON < V_OFF. Use Arbitrary mode."
            )

        # Duty cycle range check (0.1–99.9%)
        if self.frequency > 0 and self.pulse_width > 0:
            dcycle = self.pulse_width * self.frequency * 100
            if dcycle < 0.1 or dcycle > 99.9:
                errors.append(
                    f"Duty cycle = {dcycle:.2f}% at width {self.pulse_width:.6f} s "
                    "is out of range (0.1–99.9%)"
                )

        # Arbitrary-mode specific checks
        if self.waveform_mode == "arbitrary":
            from core import _calc_arb_params

            try:
                sample_rate, points_per_period = _calc_arb_params(
                    self.frequency, [self.pulse_width],
                )
                if sample_rate < 10e6 or sample_rate > 4.2e9:
                    errors.append(
                        f"Arbitrary mode sample rate = {sample_rate:.3e} Sa/s "
                        "is out of range (10 MSa/s – 4.2 GSa/s)"
                    )
                if points_per_period < 320:
                    errors.append(
                        f"Arbitrary mode segment length = {points_per_period} "
                        "is too short (must be >= 320)"
                    )
                if points_per_period % 32 != 0:
                    errors.append(
                        f"Arbitrary mode segment length = {points_per_period} "
                        "must be a multiple of 32"
                    )
            except ValueError as exc:
                errors.append(f"Arbitrary mode parameter error: {exc}")

        for e in errors:
            logger.warning("Validation error: %s", e)

        return errors


@dataclass
class SweepConfig(BaseConfig):
    """Pulse width sweep configuration for Agilent 81180A AWG."""

    # Sweep parameters
    width_start: float  # Pulse width start [s]
    width_stop: float   # Pulse width stop [s]
    width_step: float   # Pulse width step [s]

    # Sweep control
    wait_time: float    # Wait time between sweep steps [s]
    waveform_mode: str = "square"  # "square" or "arbitrary"
    settling_time: float = 0.0  # Initial settling time before sweep [s]
    trigger_delay_stop: int | None = None  # None = fixed delay; set to sweep delay
    delay_interp: str = "linear"  # "linear" or "inverse_width"

    @classmethod
    def from_toml(cls, path: str | Path) -> SweepConfig:
        """Load configuration from a TOML file.

        Either frequency or period can be specified in the [awg] section.
        If both are present, frequency takes precedence.
        """
        flat = cls._load_and_flatten_toml(path)
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
                "settling_time": self.settling_time,
                **({"trigger_delay_stop": self.trigger_delay_stop}
                   if self.trigger_delay_stop is not None else {}),
                **({"delay_interp": self.delay_interp}
                   if self.delay_interp != "linear" else {}),
            },
            "awg": {
                "frequency": self.frequency,
                "period": self.period,
                "trigger_delay": self.trigger_delay,
                "waveform_mode": self.waveform_mode,
            },
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            toml.dump(data, f)

    def validate(self) -> list[str]:
        """Validate parameter consistency. Returns a list of error messages (empty if OK)."""
        logger.info("Running validation")
        errors = self._validate_common()

        if self.width_start <= 0:
            errors.append("width_start must be positive")
        if self.width_stop <= 0:
            errors.append("width_stop must be positive")
        if self.width_step <= 0:
            errors.append("width_step must be positive")

        if self.wait_time < 0:
            errors.append("wait_time must be >= 0")

        if self.settling_time < 0:
            errors.append("settling_time must be >= 0")

        if self.trigger_delay_stop is not None:
            if self.trigger_delay_stop < 0:
                errors.append("trigger_delay_stop must be >= 0")
            if self.trigger_delay_stop % 8 != 0:
                errors.append("trigger_delay_stop must be a multiple of 8")

        if self.delay_interp not in ("linear", "inverse_width"):
            errors.append(
                f"delay_interp must be 'linear' or 'inverse_width', got '{self.delay_interp}'"
            )

        if self.waveform_mode not in ("square", "arbitrary"):
            errors.append(
                f"waveform_mode must be 'square' or 'arbitrary', got '{self.waveform_mode}'"
            )

        # Square mode cannot handle V_ON < V_OFF (81180A ignores amplitude sign and :PHASe)
        if self.waveform_mode == "square" and self.v_on < self.v_off:
            errors.append(
                "Square mode does not support V_ON < V_OFF. Use Arbitrary mode."
            )

        # Duty cycle range check (VBA UpdateSQR: 0.1–99.9%)
        for width in [self.width_start, self.width_stop]:
            dcycle = width * self.frequency * 100
            if dcycle < 0.1 or dcycle > 99.9:
                errors.append(
                    f"Duty cycle = {dcycle:.2f}% at width {width:.6f} s "
                    "is out of range (0.1–99.9%)"
                )

        # Arbitrary-mode specific checks
        if self.waveform_mode == "arbitrary":
            from core import _calc_arb_params, _generate_widths

            widths = _generate_widths(self.width_start, self.width_stop, self.width_step)
            try:
                sample_rate, points_per_period = _calc_arb_params(self.frequency, widths)
                if sample_rate < 10e6 or sample_rate > 4.2e9:
                    errors.append(
                        f"Arbitrary mode sample rate = {sample_rate:.3e} Sa/s "
                        "is out of range (10 MSa/s – 4.2 GSa/s)"
                    )
                if points_per_period < 320:
                    errors.append(
                        f"Arbitrary mode segment length = {points_per_period} "
                        "is too short (must be >= 320)"
                    )
                if points_per_period % 32 != 0:
                    errors.append(
                        f"Arbitrary mode segment length = {points_per_period} "
                        "must be a multiple of 32"
                    )
            except ValueError as exc:
                errors.append(f"Arbitrary mode parameter error: {exc}")

        for e in errors:
            logger.warning("Validation error: %s", e)

        return errors


@dataclass
class DelaySweepConfig(BaseConfig):
    """Trigger delay sweep configuration for Agilent 81180A AWG."""

    # Pulse (fixed during sweep)
    pulse_width: float   # Pulse width [s]

    # Delay sweep parameters (sample points, must be multiples of 8)
    delay_start: int     # Trigger delay start [sample points]
    delay_stop: int      # Trigger delay stop [sample points]
    delay_step: int      # Trigger delay step [sample points]

    # Sweep control
    wait_time: float     # Wait time between sweep steps [s]
    waveform_mode: str = "square"  # "square" or "arbitrary"
    settling_time: float = 0.0  # Initial settling time before sweep [s]

    @classmethod
    def from_toml(cls, path: str | Path) -> DelaySweepConfig:
        """Load configuration from a TOML file."""
        flat = cls._load_and_flatten_toml(path)
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in flat.items() if k in valid_keys}
        # Ensure delay fields are int
        for key in ("delay_start", "delay_stop", "delay_step"):
            if key in filtered:
                filtered[key] = int(filtered[key])
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
                "pulse_width": self.pulse_width,
            },
            "delay_sweep": {
                "delay_start": self.delay_start,
                "delay_stop": self.delay_stop,
                "delay_step": self.delay_step,
                "wait_time": self.wait_time,
                "settling_time": self.settling_time,
            },
            "awg": {
                "frequency": self.frequency,
                "period": self.period,
                "trigger_delay": self.trigger_delay,
                "waveform_mode": self.waveform_mode,
            },
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            toml.dump(data, f)

    def validate(self) -> list[str]:
        """Validate parameter consistency."""
        logger.info("Running validation")
        errors = self._validate_common()

        if self.pulse_width <= 0:
            errors.append("pulse_width must be positive")

        if self.waveform_mode not in ("square", "arbitrary"):
            errors.append(
                f"waveform_mode must be 'square' or 'arbitrary', got '{self.waveform_mode}'"
            )

        # Square mode cannot handle V_ON < V_OFF (81180A ignores amplitude sign and :PHASe)
        if self.waveform_mode == "square" and self.v_on < self.v_off:
            errors.append(
                "Square mode does not support V_ON < V_OFF. Use Arbitrary mode."
            )

        if self.delay_start < 0:
            errors.append("delay_start must be >= 0")
        if self.delay_stop < 0:
            errors.append("delay_stop must be >= 0")
        if self.delay_step <= 0:
            errors.append("delay_step must be positive")

        for name, val in [
            ("delay_start", self.delay_start),
            ("delay_stop", self.delay_stop),
            ("delay_step", self.delay_step),
        ]:
            if val % 8 != 0:
                errors.append(f"{name} must be a multiple of 8")

        if self.wait_time < 0:
            errors.append("wait_time must be >= 0")

        if self.settling_time < 0:
            errors.append("settling_time must be >= 0")

        # Duty cycle range check (DelaySweepConfig)
        if self.frequency > 0 and self.pulse_width > 0:
            dcycle = self.pulse_width * self.frequency * 100
            if dcycle < 0.1 or dcycle > 99.9:
                errors.append(
                    f"Duty cycle = {dcycle:.2f}% at width {self.pulse_width:.6f} s "
                    "is out of range (0.1–99.9%)"
                )

        # Arbitrary-mode specific checks
        if self.waveform_mode == "arbitrary":
            from core import _calc_arb_params

            try:
                sample_rate, points_per_period = _calc_arb_params(
                    self.frequency, [self.pulse_width],
                )
                if sample_rate < 10e6 or sample_rate > 4.2e9:
                    errors.append(
                        f"Arbitrary mode sample rate = {sample_rate:.3e} Sa/s "
                        "is out of range (10 MSa/s – 4.2 GSa/s)"
                    )
                if points_per_period < 320:
                    errors.append(
                        f"Arbitrary mode segment length = {points_per_period} "
                        "is too short (must be >= 320)"
                    )
                if points_per_period % 32 != 0:
                    errors.append(
                        f"Arbitrary mode segment length = {points_per_period} "
                        "must be a multiple of 32"
                    )
            except ValueError as exc:
                errors.append(f"Arbitrary mode parameter error: {exc}")

        for e in errors:
            logger.warning("Validation error: %s", e)

        return errors


# ================================================================== #
#  Unified TOML (single format for all modes)
# ================================================================== #

def load_unified_toml(path: str | Path) -> dict:
    """Load unified-format TOML. Handles period -> frequency conversion."""
    logger.info("Loading unified TOML: %s", path)
    data = toml.load(path)
    common = data.get("common", {})
    if "period" in common and "frequency" not in common:
        common["frequency"] = 1.0 / common.pop("period")
    elif "period" in common:
        common.pop("period")
    return data


def save_unified_toml(path: str | Path, data: dict) -> None:
    """Save unified-format TOML."""
    logger.info("Writing unified TOML: %s", path)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        toml.dump(data, f)


def next_save_path(save_dir: str, filename_format: str) -> Path:
    """Return next available path: {save_dir}/{filename_format}{nn:02d}.toml (starts at 01)."""
    d = Path(save_dir)
    d.mkdir(parents=True, exist_ok=True)
    nn = 1
    while True:
        p = d / f"{filename_format}{nn:02d}.toml"
        if not p.exists():
            return p
        nn += 1
