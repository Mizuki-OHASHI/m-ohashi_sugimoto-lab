"""Pulse Width Sweep Streamlit UI (Agilent 81180A AWG).

Usage:
    streamlit run pulse_control/app.py
"""

from __future__ import annotations

import re
import tempfile
from logging import getLogger
from pathlib import Path

import streamlit as st

from config import DEFAULT_VISA_ADDRESS, SweepConfig

DEFAULT_CONFIG = Path("sweep_config.toml")
from core import PulseInstrument, _generate_widths, run_sweep
from log_setup import setup_logging

setup_logging()
logger = getLogger(__name__)

st.set_page_config(page_title="Pulse Width Sweep", layout="wide")

# ================================================================== #
#  SI prefix parse / format
# ================================================================== #
_SI_PREFIXES: dict[str, float] = {
    "n": 1e-9, "u": 1e-6, "μ": 1e-6, "m": 1e-3,
    "k": 1e3, "M": 1e6,
}
_SI_PARSE_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)\s*([nuμmkM])?\s*$")

# Ordered largest-first for formatting
_FORMAT_PREFIXES = [(1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n")]


def parse_si(text: str) -> float:
    """Parse SI-prefixed string: '1n' → 1e-9, '10u' → 10e-6, '20k' → 20e3."""
    m = _SI_PARSE_RE.match(text)
    if not m:
        raise ValueError(f"Invalid value: {text!r}")
    num = float(m.group(1))
    prefix = m.group(2)
    if prefix:
        num *= _SI_PREFIXES[prefix]
    return num


def format_si(value: float) -> str:
    """Format to SI-prefixed string: 1e-9 → '1n', 0.02 → '20m', 20000 → '20k'."""
    if value == 0:
        return "0"
    for factor, prefix in _FORMAT_PREFIXES:
        scaled = value / factor
        if abs(scaled) >= 1:
            return f"{scaled:g}{prefix}"
    # Fallback for extremely small values
    factor, prefix = _FORMAT_PREFIXES[-1]
    return f"{value / factor:g}{prefix}"


# ================================================================== #
#  Session initialisation
# ================================================================== #
if "config" not in st.session_state:
    st.session_state.config = SweepConfig.from_toml(DEFAULT_CONFIG)

cfg: SweepConfig = st.session_state.config


# ================================================================== #
#  Callbacks: frequency ↔ period sync
# ================================================================== #
def _on_freq_change() -> None:
    """Frequency text changed → recalculate period."""
    try:
        freq = parse_si(st.session_state._w_freq)
        if freq > 0:
            st.session_state._w_period = format_si(1.0 / freq)
    except ValueError:
        pass


def _on_period_change() -> None:
    """Period text changed → recalculate frequency."""
    try:
        period = parse_si(st.session_state._w_period)
        if period > 0:
            st.session_state._w_freq = format_si(1.0 / period)
    except ValueError:
        pass


def _load_config_to_widgets(new_cfg: SweepConfig) -> None:
    """Push SweepConfig values into widget session state."""
    st.session_state.config = new_cfg
    st.session_state._w_width_start = format_si(new_cfg.width_start)
    st.session_state._w_width_stop = format_si(new_cfg.width_stop)
    st.session_state._w_width_step = format_si(new_cfg.width_step)
    st.session_state._w_wait_time = format_si(new_cfg.wait_time)
    st.session_state._w_freq = format_si(new_cfg.frequency)
    if new_cfg.frequency > 0:
        st.session_state._w_period = format_si(1.0 / new_cfg.frequency)


# ================================================================== #
#  Sidebar: title + connection + TOML import/export
# ================================================================== #
with st.sidebar:
    st.header("Pulse Width Sweep")
    st.caption("Agilent 81180A AWG")

    st.divider()
    st.markdown("**Connection**")
    visa_address = st.text_input("VISA Address", value=cfg.visa_address)

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("Reset", use_container_width=True):
            cfg.visa_address = DEFAULT_VISA_ADDRESS
            st.rerun()
    with btn_col2:
        check_conn = st.button("Check", use_container_width=True)

    if check_conn:
        with st.spinner("Connecting..."):
            try:
                idn = PulseInstrument.check_connection(visa_address)
                st.success(f"OK: {idn}")
                logger.info("Connection check OK: %s", idn)
            except Exception as exc:
                st.error(f"Failed: {exc}")
                logger.error("Connection check failed: %s", exc)

    st.divider()
    st.markdown("**TOML Config**")

    uploaded = st.file_uploader("Import TOML", type=["toml"])
    if uploaded is not None:
        upload_id = f"{uploaded.name}_{uploaded.size}"
        if st.session_state.get("_last_upload_id") != upload_id:
            st.session_state._last_upload_id = upload_id
            with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as tmp:
                tmp.write(uploaded.read())
                tmp.flush()
                _load_config_to_widgets(SweepConfig.from_toml(tmp.name))
            st.rerun()

# ================================================================== #
#  Main: parameter inputs
# ================================================================== #
col1, col2, col3 = st.columns(3)

parse_errors: list[str] = []

with col1:
    st.subheader("Pulse")
    v_on = st.number_input("V_on [V]", value=cfg.v_on, format="%.4f")
    v_off = st.number_input("V_off [V]", value=cfg.v_off, format="%.4f")
    freq_col, period_col = st.columns(2)
    with freq_col:
        st.text_input(
            "Frequency [Hz]",
            value=format_si(cfg.frequency),
            key="_w_freq",
            on_change=_on_freq_change,
        )
    with period_col:
        st.text_input(
            "Period [s]",
            value=format_si(1.0 / cfg.frequency),
            key="_w_period",
            on_change=_on_period_change,
        )

with col2:
    st.subheader("Sweep Range")
    st.text_input(
        "Width Start [s]",
        value=format_si(cfg.width_start),
        key="_w_width_start",
    )
    st.text_input(
        "Width Stop [s]",
        value=format_si(cfg.width_stop),
        key="_w_width_stop",
    )
    st.text_input(
        "Width Step [s]",
        value=format_si(cfg.width_step),
        key="_w_width_step",
    )

with col3:
    st.subheader("Trigger")
    trigger_delay = st.number_input(
        "Trigger Delay [points] (multiple of 8)",
        value=cfg.trigger_delay, min_value=0, step=8,
    )

    st.subheader("Sweep Control")
    st.text_input(
        "Wait Time [s]",
        value=format_si(cfg.wait_time),
        key="_w_wait_time",
    )
    _MODE_LABELS = {"square": "Square", "arbitrary": "Arbitrary (glitch-free)"}
    waveform_mode = st.radio(
        "Waveform Mode",
        ["square", "arbitrary"],
        format_func=lambda x: _MODE_LABELS[x],
        horizontal=True,
    )
    st.info("Pulse center is fixed at the middle of the period during sweep.")

# ------------------------------------------------------------------ #
#  Parse SI text fields
# ------------------------------------------------------------------ #
_SI_FIELDS = {
    "frequency": "_w_freq",
    "width_start": "_w_width_start",
    "width_stop": "_w_width_stop",
    "width_step": "_w_width_step",
    "wait_time": "_w_wait_time",
}

parsed: dict[str, float] = {}
for name, key in _SI_FIELDS.items():
    try:
        parsed[name] = parse_si(st.session_state[key])
    except (ValueError, KeyError):
        parse_errors.append(f"{name}: invalid value \"{st.session_state.get(key, '')}\"")

try:
    parsed["period"] = parse_si(st.session_state["_w_period"])
except (ValueError, KeyError):
    parse_errors.append(f"period: invalid value \"{st.session_state.get('_w_period', '')}\"")


# ------------------------------------------------------------------ #
#  Build SweepConfig from UI values
# ------------------------------------------------------------------ #
def _build_config_from_ui() -> SweepConfig | None:
    if parse_errors:
        return None
    return SweepConfig(
        visa_address=visa_address,
        v_on=v_on,
        v_off=v_off,
        width_start=parsed["width_start"],
        width_stop=parsed["width_stop"],
        width_step=parsed["width_step"],
        frequency=parsed["frequency"],
        trigger_delay=int(trigger_delay),
        wait_time=parsed["wait_time"],
        waveform_mode=waveform_mode,
    )


# ================================================================== #
#  TOML export
# ================================================================== #
with st.sidebar:
    config_or_none = _build_config_from_ui()
    if config_or_none is not None:
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as tmp:
            config_or_none.to_toml(tmp.name)
            with open(tmp.name) as f:
                toml_str = f.read()
        st.download_button(
            "Export TOML",
            data=toml_str,
            file_name="sweep_config.toml",
            mime="text/plain",
        )

# ================================================================== #
#  Validation
# ================================================================== #
errors = list(parse_errors)
if config_or_none is not None:
    errors.extend(config_or_none.validate())

st.divider()
if errors:
    msg = "Configuration error:\n" + "\n".join(f"- {e}" for e in errors)
    st.error(msg)
else:
    st.success("Parameters OK")

# ================================================================== #
#  Run sweep
# ================================================================== #
if st.button("Start Sweep", disabled=bool(errors) or not visa_address, type="primary"):
    config = _build_config_from_ui()
    logger.info("Sweep started")
    progress = st.progress(0, text="Connecting...")

    try:
        instrument = PulseInstrument(config.visa_address)
        progress.progress(0, text="Setting up instrument...")

        if config.waveform_mode == "arbitrary":
            widths = _generate_widths(config.width_start, config.width_stop, config.width_step)
            instrument.setup_arbitrary(config, widths)
        else:
            instrument.setup(config)

        def on_step(i: int, total: int) -> None:
            pct = (i + 1) / total
            progress.progress(pct, text=f"Sweeping... {i + 1}/{total}")

        run_sweep(config, instrument, callback=on_step)
        instrument.teardown()
        instrument.close()

        progress.progress(1.0, text="Done!")
        logger.info("Sweep completed")

    except Exception as exc:
        st.error(f"Error: {exc}")
        logger.exception("Error during sweep")
