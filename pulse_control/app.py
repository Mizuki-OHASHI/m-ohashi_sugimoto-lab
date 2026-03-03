"""Pulse Control Streamlit UI (Agilent 81180A AWG).

Usage:
    streamlit run pulse_control/app.py
"""

from __future__ import annotations

import csv
import re
import tempfile
import time
from datetime import datetime
from logging import getLogger
from pathlib import Path

import streamlit as st

from config import (
    DEFAULT_VISA_ADDRESS,
    DelaySweepConfig,
    IntervalSweepConfig,
    PulseConfig,
    PumpProbeConfig,
    SweepConfig,
    load_unified_toml,
    next_save_path,
    save_unified_toml,
)
from core import (
    PulseInstrument,
    _calc_arb_params,
    _generate_intervals,
    _generate_widths,
    run_delay_sweep,
    run_interval_sweep,
    run_sweep,
)
from core_34401A import DEFAULT_34401A_ADDRESS, Multimeter
from core_integration import IntegrationConfig, detect_ramp_start
from log_setup import setup_logging

DEFAULT_CONFIG = Path("configs/config.toml")
SAVED_RECORDS_CSV = Path("saved_pulse_records.csv")
SAVED_PP_RECORDS_CSV = Path("saved_pump_probe_records.csv")

setup_logging()
logger = getLogger(__name__)

st.set_page_config(page_title="Pulse Control", layout="wide")

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
    """Parse SI-prefixed string: '1n' -> 1e-9, '10u' -> 10e-6, '20k' -> 20e3."""
    m = _SI_PARSE_RE.match(text)
    if not m:
        raise ValueError(f"Invalid value: {text!r}")
    num = float(m.group(1))
    prefix = m.group(2)
    if prefix:
        num *= _SI_PREFIXES[prefix]
    return num


def format_si(value: float) -> str:
    """Format to SI-prefixed string: 1e-9 -> '1n', 0.02 -> '20m', 20000 -> '20k'."""
    if value == 0:
        return "0"
    for factor, prefix in _FORMAT_PREFIXES:
        scaled = value / factor
        if abs(scaled) >= 1:
            return f"{scaled:g}{prefix}"
    # Fallback for extremely small values
    factor, prefix = _FORMAT_PREFIXES[-1]
    return f"{value / factor:g}{prefix}"


def _save_records_to_csv(records: list[dict]) -> None:
    """Save pulse records to CSV on disk."""
    with open(SAVED_RECORDS_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "pulse_width", "trigger_delay"])
        for r in records:
            writer.writerow([r["timestamp"], r["pulse_width"], r["trigger_delay"]])


def _load_records_from_csv() -> list[dict]:
    """Load pulse records from CSV if it exists."""
    if not SAVED_RECORDS_CSV.exists():
        return []
    records = []
    with open(SAVED_RECORDS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append({
                "timestamp": row["timestamp"],
                "pulse_width": row["pulse_width"],
                "trigger_delay": int(row["trigger_delay"]),
            })
    return records


def _save_pp_records_to_csv(records: list[dict]) -> None:
    """Save pump-probe records to CSV on disk."""
    with open(SAVED_PP_RECORDS_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "pulse_interval", "trigger_delay"])
        for r in records:
            writer.writerow([r["timestamp"], r["pulse_interval"], r["trigger_delay"]])


def _load_pp_records_from_csv() -> list[dict]:
    """Load pump-probe records from CSV if it exists."""
    if not SAVED_PP_RECORDS_CSV.exists():
        return []
    records = []
    with open(SAVED_PP_RECORDS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append({
                "timestamp": row["timestamp"],
                "pulse_interval": row["pulse_interval"],
                "trigger_delay": int(row["trigger_delay"]),
            })
    return records


_CHANNEL_MAP = {"CH1": [1], "CH2": [2], "Both": [1, 2]}

MAX_SAMPLE_RATE = 4.2e9  # 81180A maximum sample clock


def _show_arb_info(frequency: float, widths: list[float], *, resolution_n: int = 1) -> None:
    """Show arbitrary waveform parameters in a collapsed expander."""
    try:
        sample_rate, pts = _calc_arb_params(frequency, widths, resolution_n=resolution_n)
    except Exception as exc:
        st.warning(f"ARB calc error: {exc}")
        return
    period = 1.0 / frequency
    tpp = period / pts
    delay_step_time = 8 * tpp
    total_memory = len(widths) * pts

    if sample_rate > MAX_SAMPLE_RATE:
        st.warning(
            f"Sample rate {sample_rate:.3e} Sa/s exceeds 4.2 GSa/s limit. "
            "Increase period or use a coarser width step."
        )

    with st.expander("Arbitrary Waveform Details"):
        st.json({
            "segments": len(widths),
            "points_per_period": pts,
            "sample_rate": f"{sample_rate:.3e} Sa/s",
            "time_per_point": f"{format_si(tpp)}s",
            "delay_resolution (×8)": f"{format_si(delay_step_time)}s",
            "total_memory": f"{total_memory:,} words",
            "phase_shift": "Pulse center is fixed at the middle of the period during sweep."
        })


# ================================================================== #
#  Session initialisation (unified TOML)
# ================================================================== #
if "unified_config" not in st.session_state:
    st.session_state.unified_config = load_unified_toml(DEFAULT_CONFIG)

ucfg: dict = st.session_state.unified_config
_save = ucfg.get("save", {})
_conn = ucfg.get("connection", {})
_common = ucfg.get("common", {})
_sp = ucfg.get("simple_pulse", {})
_ws = ucfg.get("width_sweep", {})
_ds = ucfg.get("delay_sweep", {})
_pp = ucfg.get("pump_probe", {})
_isw = ucfg.get("interval_sweep", {})
_ig = ucfg.get("integration", {})


# ================================================================== #
#  Callbacks: frequency <-> period sync
# ================================================================== #
def _on_freq_change() -> None:
    """Frequency text changed -> recalculate period."""
    try:
        freq = parse_si(st.session_state._w_freq)
        if freq > 0:
            st.session_state._w_period = format_si(1.0 / freq)
    except ValueError:
        pass


def _on_period_change() -> None:
    """Period text changed -> recalculate frequency."""
    try:
        period = parse_si(st.session_state._w_period)
        if period > 0:
            st.session_state._w_freq = format_si(1.0 / period)
    except ValueError:
        pass


def _load_config_to_widgets(data: dict) -> None:
    """Push unified TOML data into widget session state."""
    st.session_state.unified_config = data

    save = data.get("save", {})
    conn = data.get("connection", {})
    common = data.get("common", {})
    sp = data.get("simple_pulse", {})
    ws = data.get("width_sweep", {})
    ds = data.get("delay_sweep", {})

    # Save settings
    st.session_state._w_save_dir = save.get("save_dir", "configs")
    st.session_state._w_filename_format = save.get("filename_format", "")

    # Connection
    st.session_state._w_visa_address = conn.get("visa_address", DEFAULT_VISA_ADDRESS)

    # Common
    st.session_state._w_v_on = common.get("v_on", 0.0)
    st.session_state._w_v_off = common.get("v_off", -1.0)
    freq = common.get("frequency", 10_000_000.0)
    st.session_state._w_freq = format_si(freq)
    if freq > 0:
        st.session_state._w_period = format_si(1.0 / freq)
    st.session_state._w_trigger_delay = common.get("trigger_delay", 0)
    st.session_state._w_resolution_n = common.get("resolution_n", 1)

    # Simple Pulse
    st.session_state._w_pulse_width = format_si(sp.get("pulse_width", 1e-8))
    # waveform_mode is always "arbitrary" (square mode removed)
    # Restore saved_pulse_records from simple_pulse.saved_records or width_sweep.delay_table
    _saved = sp.get("saved_records") or ws.get("delay_table")
    if _saved is not None:
        st.session_state.saved_pulse_records = [
            {
                "timestamp": "",
                "pulse_width": format_si(row[0]),
                "trigger_delay": int(row[1]),
            }
            for row in _saved
        ]
    elif not st.session_state.get("saved_pulse_records"):
        # Restore from CSV on disk (crash recovery)
        _csv_records = _load_records_from_csv()
        if _csv_records:
            st.session_state.saved_pulse_records = _csv_records

    # Width Sweep
    st.session_state._w_width_start = format_si(ws.get("width_start", 1e-8))
    st.session_state._w_width_stop = format_si(ws.get("width_stop", 5e-8))
    st.session_state._w_width_step = format_si(ws.get("width_step", 5e-9))
    st.session_state._w_wait_time = format_si(ws.get("wait_time", 1.0))
    st.session_state._w_settling_time = ws.get("settling_time", 0.0)
    # waveform_mode is always "arbitrary" (square mode removed)
    td_stop = ws.get("trigger_delay_stop")
    st.session_state._w_trigger_delay_stop = (
        td_stop if td_stop is not None else common.get("trigger_delay", 0)
    )
    st.session_state._w_delay_exponent = ws.get("delay_exponent", 1.0)
    _dm = ws.get("delay_mode", "exponent")
    st.session_state._w_delay_mode_radio = "Exponent" if _dm == "exponent" else "Table"
    # Variable step zones
    _sz = ws.get("step_zones", [])
    st.session_state._w_variable_step = bool(_sz)
    if _sz:
        z1 = _sz[0] if len(_sz) >= 1 else [None, None]
        st.session_state._w_step_zone1_boundary = format_si(z1[0]) if z1[0] is not None else ""
        st.session_state._w_step_zone1_step = format_si(z1[1]) if z1[1] is not None else ""
        z2 = _sz[1] if len(_sz) >= 2 else [None, None]
        st.session_state._w_step_zone2_boundary = format_si(z2[0]) if z2[0] is not None else ""
        st.session_state._w_step_zone2_step = format_si(z2[1]) if z2[1] is not None else ""

    # Integration (Auto Sweep)
    ig = data.get("integration", {})
    st.session_state._w_ig_dmm_address = ig.get("dmm_visa_address", DEFAULT_34401A_ADDRESS)
    st.session_state._w_ig_trigger_start = ig.get("trigger_start_voltage", -9.8)
    st.session_state._w_ig_trigger_end = ig.get("trigger_end_voltage", -9.2)
    st.session_state._w_ig_sweep_start = ig.get("sweep_start_voltage", -9.0)
    st.session_state._w_ig_poll_interval = ig.get("poll_interval", 1.0)
    st.session_state._w_ig_num_cycles = ig.get("num_cycles", 0)

    # Delay Sweep
    st.session_state._w_delay_pulse_width = format_si(ds.get("pulse_width", 1e-8))
    st.session_state._w_delay_start = ds.get("delay_start", 0)
    st.session_state._w_delay_stop = ds.get("delay_stop", 80)
    st.session_state._w_delay_step = ds.get("delay_step", 8)
    st.session_state._w_delay_wait_time = format_si(ds.get("wait_time", 1.0))
    st.session_state._w_delay_settling_time = ds.get("settling_time", 0.0)
    # waveform_mode is always "arbitrary" (square mode removed)

    # Pump-Probe
    pp = data.get("pump_probe", {})
    st.session_state._w_pp_pulse_width = format_si(pp.get("pulse_width", 1e-8))
    st.session_state._w_pp_pulse_interval = format_si(pp.get("pulse_interval", 2e-8))
    # Restore saved_pp_records
    _pp_saved = pp.get("saved_records") or data.get("interval_sweep", {}).get("delay_table")
    if _pp_saved is not None:
        st.session_state.saved_pp_records = [
            {
                "timestamp": "",
                "pulse_interval": format_si(row[0]),
                "trigger_delay": int(row[1]),
            }
            for row in _pp_saved
        ]
    elif not st.session_state.get("saved_pp_records"):
        _pp_csv = _load_pp_records_from_csv()
        if _pp_csv:
            st.session_state.saved_pp_records = _pp_csv

    # Interval Sweep
    isw = data.get("interval_sweep", {})
    st.session_state._w_interval_pulse_width = format_si(isw.get("pulse_width", 1e-8))
    st.session_state._w_interval_start = format_si(isw.get("interval_start", 1e-8))
    st.session_state._w_interval_stop = format_si(isw.get("interval_stop", 5e-8))
    st.session_state._w_interval_step = format_si(isw.get("interval_step", 5e-9))
    st.session_state._w_interval_wait_time = format_si(isw.get("wait_time", 1.0))
    st.session_state._w_interval_settling_time = isw.get("settling_time", 0.0)
    td_stop_isw = isw.get("trigger_delay_stop")
    st.session_state._w_interval_trigger_delay_stop = (
        td_stop_isw if td_stop_isw is not None else common.get("trigger_delay", 0)
    )
    st.session_state._w_interval_delay_exponent = isw.get("delay_exponent", 1.0)
    _dm_isw = isw.get("delay_mode", "exponent")
    st.session_state._w_interval_delay_mode_radio = "Exponent" if _dm_isw == "exponent" else "Table"
    _isz = isw.get("step_zones", [])
    st.session_state._w_interval_variable_step = bool(_isz)
    if _isz:
        z1 = _isz[0] if len(_isz) >= 1 else [None, None]
        st.session_state._w_interval_step_zone1_boundary = format_si(z1[0]) if z1[0] is not None else ""
        st.session_state._w_interval_step_zone1_step = format_si(z1[1]) if z1[1] is not None else ""
        z2 = _isz[1] if len(_isz) >= 2 else [None, None]
        st.session_state._w_interval_step_zone2_boundary = format_si(z2[0]) if z2[0] is not None else ""
        st.session_state._w_interval_step_zone2_step = format_si(z2[1]) if z2[1] is not None else ""


# Process pending import BEFORE any widgets are instantiated
if "_pending_import" in st.session_state:
    _load_config_to_widgets(st.session_state.pop("_pending_import"))


# ================================================================== #
#  Instrument helpers
# ================================================================== #
def _close_live_connection() -> None:
    """Close the live connection and reset associated state."""
    inst = st.session_state.pop("live_instrument", None)
    if inst is not None:
        try:
            inst.close()
        except Exception:
            pass
    st.session_state.live_connection = False
    st.session_state.pop("last_trigger_delay", None)
    logger.info("Live connection closed")


def _pulse_start(config: PulseConfig, channel: int) -> None:
    """Start pulse output. Reuses live connection if active, otherwise fire-and-forget."""
    if st.session_state.get("live_connection"):
        inst = st.session_state.get("live_instrument")
        if inst is None:
            inst = PulseInstrument(config.visa_address)
            st.session_state.live_instrument = inst
        close_after = False
    else:
        inst = PulseInstrument(config.visa_address)
        close_after = True

    try:
        inst.setup_arbitrary(config, [config.pulse_width], channel=channel)
    except Exception:
        if close_after:
            inst.close()
        raise

    if close_after:
        inst.close()
    else:
        st.session_state.last_trigger_delay = config.trigger_delay


def _pump_probe_start(config: PumpProbeConfig, channel: int) -> None:
    """Start pump-probe output. Same live-connection pattern as _pulse_start."""
    if st.session_state.get("live_connection"):
        inst = st.session_state.get("live_instrument")
        if inst is None:
            inst = PulseInstrument(config.visa_address)
            st.session_state.live_instrument = inst
        close_after = False
    else:
        inst = PulseInstrument(config.visa_address)
        close_after = True

    try:
        inst.setup_pump_probe_arbitrary(
            config, config.pulse_width, [config.pulse_interval], channel=channel,
        )
    except Exception:
        if close_after:
            inst.close()
        raise

    if close_after:
        inst.close()
    else:
        st.session_state.last_trigger_delay = config.trigger_delay


def _pulse_stop(visa_addr: str, channel: int) -> None:
    """Stop pulse output. Reuses live connection if active, otherwise fire-and-forget."""
    if st.session_state.get("live_connection"):
        inst = st.session_state.get("live_instrument")
        if inst is not None:
            inst.teardown(channel=channel)
        else:
            tmp = PulseInstrument(visa_addr)
            try:
                tmp.teardown(channel=channel)
            finally:
                tmp.close()
    else:
        tmp = PulseInstrument(visa_addr)
        try:
            tmp.teardown(channel=channel)
        finally:
            tmp.close()

    st.session_state[f"ch{channel}_running"] = False

    # Auto-OFF live connection when all channels become idle
    # Check both Simple Pulse and Pump-Probe running states
    any_running = (
        st.session_state.get("ch1_running")
        or st.session_state.get("ch2_running")
        or st.session_state.get("pp_ch1_running")
        or st.session_state.get("pp_ch2_running")
    )
    if not any_running:
        if st.session_state.get("live_connection"):
            _close_live_connection()
            st.session_state._w_live_connection = False


# ================================================================== #
#  Sidebar: title + connection + DC 0V + TOML import/export
# ================================================================== #
with st.sidebar:
    st.header("Pulse Control")
    st.caption("Agilent 81180A AWG")

    st.subheader("Connection")
    visa_address = st.text_input(
        "VISA Address",
        value=_conn.get("visa_address", DEFAULT_VISA_ADDRESS),
        key="_w_visa_address",
    )

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("Reset", use_container_width=True):
            st.session_state._w_visa_address = DEFAULT_VISA_ADDRESS
            st.rerun()
    with btn_col2:
        check_conn = st.button("Check", use_container_width=True)

    if check_conn:
        if st.session_state.get("live_connection"):
            _close_live_connection()
            st.session_state._w_live_connection = False
        with st.spinner("Connecting..."):
            try:
                idn = PulseInstrument.check_connection(visa_address)
                st.success(f"OK: {idn}")
                logger.info("Connection check OK: %s", idn)
            except Exception as exc:
                st.error(f"Failed: {exc}")
                logger.error("Connection check failed: %s", exc)

    # DC 0V button (always visible)
    if st.button("DC 0V", use_container_width=True, help="Set output to DC 0V (safe state)", type="primary"):
        if st.session_state.get("live_connection"):
            _close_live_connection()
            st.session_state._w_live_connection = False
        with st.spinner("Setting DC 0V..."):
            try:
                inst = PulseInstrument(visa_address)
                try:
                    inst.set_dc_zero()
                finally:
                    inst.close()
                st.success("DC 0V set")
                logger.info("DC 0V set via UI")
            except Exception as exc:
                st.error(f"Failed: {exc}")
                logger.error("DC 0V failed: %s", exc)

    st.subheader("TOML Config")

    with st.expander("Settings / Import"):
        st.text_input(
            "Save Directory",
            value=_save.get("save_dir", "configs"),
            key="_w_save_dir",
        )
        st.text_input(
            "Filename Format",
            value=_save.get("filename_format", "pulse_control_"),
            key="_w_filename_format",
        )

        uploaded = st.file_uploader("Import TOML", type=["toml"])
        if uploaded is not None:
            upload_id = f"{uploaded.name}_{uploaded.size}"
            if st.session_state.get("_last_upload_id") != upload_id:
                st.session_state._last_upload_id = upload_id
                with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as tmp:
                    tmp.write(uploaded.read())
                    tmp.flush()
                    try:
                        st.session_state._pending_import = load_unified_toml(tmp.name)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Import failed: {exc}")

    _save_btn_placeholder = st.empty()


# ================================================================== #
#  Main: Common parameters (always visible)
# ================================================================== #
col_left, col_right = st.columns(2)

with col_left:
    st.text("Voltage Levels and Timing")
    col_volt_left, col_volt_right = st.columns(2) 
    with col_volt_left:
        v_on = st.number_input(
            "V_on [V]", value=_common.get("v_on", 0.0), format="%.4f", key="_w_v_on",
        )
    with col_volt_right:
        v_off = st.number_input(
            "V_off [V]", value=_common.get("v_off", -1.0), format="%.4f", key="_w_v_off",
        )
    freq_col, period_col = st.columns(2)
    with freq_col:
        st.text_input(
            "Frequency [Hz]",
            value=format_si(_common.get("frequency", 10_000_000.0)),
            key="_w_freq",
            on_change=_on_freq_change,
        )
    with period_col:
        _freq_default = _common.get("frequency", 10_000_000.0)
        st.text_input(
            "Period [s]",
            value=format_si(1.0 / _freq_default) if _freq_default > 0 else "0",
            key="_w_period",
            on_change=_on_period_change,
        )

with col_right:
    st.text("Trigger Delay")
    trigger_delay = st.number_input(
        "Trigger Delay [points] (multiple of 8)",
        value=_common.get("trigger_delay", 0), min_value=0, step=8,
        key="_w_trigger_delay",
    )
    col_res_n, col_res_val = st.columns(2)
    with col_res_n:
        resolution_n = st.number_input(
            "Delay Resolution (×n)",
            value=_common.get("resolution_n", 1), min_value=1, step=1,
            help="Multiplier for points_per_period. Higher = finer delay resolution.",
            key="_w_resolution_n",
        )
    with col_res_val:
        _delay_res_placeholder = st.empty()

# Parse common SI fields
common_parse_errors: list[str] = []
common_parsed: dict[str, float] = {}

try:
    common_parsed["frequency"] = parse_si(st.session_state._w_freq)
except (ValueError, KeyError):
    common_parse_errors.append(
        f"frequency: invalid value \"{st.session_state.get('_w_freq', '')}\""
    )

# ================================================================== #
#  Tabs: mode-specific UI
# ================================================================== #
pulse_config: PulseConfig | None = None
sweep_config_built: SweepConfig | None = None
delay_config_built: DelaySweepConfig | None = None
pulse_parse_errors: list[str] = []
sweep_parse_errors: list[str] = []
delay_parse_errors: list[str] = []

# Tab locking: prevent switching tabs while output is running
_sp_running = st.session_state.get("ch1_running") or st.session_state.get("ch2_running")
_pp_running = st.session_state.get("pp_ch1_running") or st.session_state.get("pp_ch2_running")
_active_output_tab: str | None = (
    "simple_pulse" if _sp_running else
    "pump_probe" if _pp_running else
    None
)

tab_pulse, tab_pp, tab_sweep, tab_isweep, tab_delay = st.tabs([
    "Simple Pulse", "Pump-Probe", "Width Sweep", "Interval Sweep", "Delay Sweep",
])

# ================================================================== #
#  Simple Pulse tab
# ================================================================== #
with tab_pulse:
    if _active_output_tab is not None and _active_output_tab != "simple_pulse":
        _mode_label = "Simple Pulse" if _sp_running else "Pump-Probe"
        _chs = [str(ch) for ch in [1, 2]
                if st.session_state.get(f"ch{ch}_running")
                or st.session_state.get(f"pp_ch{ch}_running")]
        st.warning(
            f"{_mode_label} output is running (CH{', '.join(_chs)}). "
            "Stop output before switching modes."
        )
    else:
        _pulse_left, _pulse_right = st.columns([2, 1])

        with _pulse_left:
            st.text_input(
                "Pulse Width [s]",
                value=format_si(_sp.get("pulse_width", 1e-8)),
                key="_w_pulse_width",
            )
            pulse_waveform_mode = "arbitrary"

            # Parse pulse-specific fields
            pulse_parse_errors = list(common_parse_errors)
            try:
                pulse_width_val = parse_si(st.session_state._w_pulse_width)
            except (ValueError, KeyError):
                pulse_width_val = None
                pulse_parse_errors.append(
                    f"pulse_width: invalid value \"{st.session_state.get('_w_pulse_width', '')}\""
                )

            # Build pulse config
            if not pulse_parse_errors and pulse_width_val is not None:
                pulse_config = PulseConfig(
                    visa_address=visa_address,
                    v_on=v_on,
                    v_off=v_off,
                    frequency=common_parsed["frequency"],
                    trigger_delay=int(trigger_delay),
                    resolution_n=int(resolution_n),
                    pulse_width=pulse_width_val,
                    waveform_mode=pulse_waveform_mode,
                )

            # Validation
            errors_pulse = list(pulse_parse_errors)
            if pulse_config is not None:
                errors_pulse.extend(pulse_config.validate())

            if errors_pulse:
                st.error("Configuration error:\n" + "\n".join(f"- {e}" for e in errors_pulse))
            else:
                st.success("Parameters OK")
                if pulse_config is not None:
                    _show_arb_info(pulse_config.frequency, [pulse_config.pulse_width], resolution_n=resolution_n)

            # Per-channel toggle + Live toggle
            ch1_running = st.session_state.get("ch1_running", False)
            ch2_running = st.session_state.get("ch2_running", False)
            can_start = not bool(errors_pulse) and bool(visa_address)

            btn_ch1 = False
            btn_ch2 = False
            live_on = False
            live_off = False
            is_live = st.session_state.get("live_connection", False)

            c1, c2, c3 = st.columns(3)
            with c1:
                if ch1_running:
                    btn_ch1 = st.button("Stop CH1", type="primary", use_container_width=True)
                else:
                    btn_ch1 = st.button(
                        "Start CH1", use_container_width=True,
                        disabled=not can_start,
                    )
            with c2:
                if ch2_running:
                    btn_ch2 = st.button("Stop CH2", type="primary", use_container_width=True)
                else:
                    btn_ch2 = st.button(
                        "Start CH2", use_container_width=True,
                        disabled=not can_start,
                    )
            with c3:
                if is_live:
                    live_off = st.button("Live Off", type="primary", use_container_width=True)
                else:
                    live_on = st.button(
                        "Live On", use_container_width=True,
                        disabled=not bool(visa_address),
                    )

            # Status
            if st.session_state.get("live_connection"):
                st.warning("Live Connection: ON (front panel locked in REMOTE mode)")
            if ch1_running:
                st.info("CH1: Pulse output is ON.")
            if ch2_running:
                st.info("CH2: Pulse output is ON.")

        with _pulse_right:
            if "saved_pulse_records" not in st.session_state:
                st.session_state.saved_pulse_records = []

            _sv_col1, _sv_col2 = st.columns(2)
            with _sv_col1:
                _btn_save = st.button("Save", type="primary", use_container_width=True)
            with _sv_col2:
                _btn_clear = st.button("Clear", use_container_width=True)

            if _btn_save:
                pw = st.session_state.get("_w_pulse_width", "")
                new_record = {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "pulse_width": pw,
                    "trigger_delay": int(trigger_delay),
                }
                records = st.session_state.saved_pulse_records
                # Overwrite if same pulse_width exists
                replaced = False
                for i, r in enumerate(records):
                    if r["pulse_width"] == pw:
                        records[i] = new_record
                        replaced = True
                        break
                if not replaced:
                    records.append(new_record)
                # Sort by pulse_width
                records.sort(key=lambda r: parse_si(r["pulse_width"]))
                _save_records_to_csv(records)
                st.rerun()

            if _btn_clear:
                st.session_state.saved_pulse_records = []
                _save_records_to_csv([])
                st.rerun()

            if st.session_state.saved_pulse_records:
                lines = ["timestamp,pulse_width,trigger_delay"]
                for r in st.session_state.saved_pulse_records:
                    lines.append(f"{r['timestamp']},{r['pulse_width']},{r['trigger_delay']}")
                st.markdown("```csv\n" + "\n".join(lines) + "\n```")

        # CH1 toggle
        if btn_ch1:
            if ch1_running:
                try:
                    _pulse_stop(visa_address, channel=1)
                except Exception as exc:
                    logger.error("Teardown CH1 error: %s", exc)
                logger.info("Pulse CH1 stopped via UI")
                st.rerun()
            elif pulse_config is not None:
                try:
                    _pulse_start(pulse_config, channel=1)
                    st.session_state.ch1_running = True
                    logger.info("Pulse CH1 started via UI (%s)", pulse_config.waveform_mode)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error: {exc}")
                    logger.exception("Error starting pulse CH1")

        # CH2 toggle
        if btn_ch2:
            if ch2_running:
                try:
                    _pulse_stop(visa_address, channel=2)
                except Exception as exc:
                    logger.error("Teardown CH2 error: %s", exc)
                logger.info("Pulse CH2 stopped via UI")
                st.rerun()
            elif pulse_config is not None:
                try:
                    _pulse_start(pulse_config, channel=2)
                    st.session_state.ch2_running = True
                    logger.info("Pulse CH2 started via UI (%s)", pulse_config.waveform_mode)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error: {exc}")
                    logger.exception("Error starting pulse CH2")

        # Live connection state management (button-driven)
        if live_on:
            try:
                inst = PulseInstrument(visa_address)
                st.session_state.live_instrument = inst
                st.session_state.live_connection = True
                delay_val = int(trigger_delay)
                for ch_num in [1, 2]:
                    if st.session_state.get(f"ch{ch_num}_running"):
                        inst.set_trigger_delay(delay_val, channel=ch_num)
                st.session_state.last_trigger_delay = delay_val
                logger.info("Live connection opened")
                st.rerun()
            except Exception as exc:
                st.error(f"Live connection failed: {exc}")
                st.session_state.live_connection = False
                logger.exception("Live connection error")

        if live_off:
            _close_live_connection()
            st.rerun()

        if is_live and not live_off:
            delay_val = int(trigger_delay)
            prev_delay = st.session_state.get("last_trigger_delay")
            if prev_delay is not None and delay_val != prev_delay:
                inst = st.session_state.get("live_instrument")
                if inst is not None:
                    try:
                        for ch_num in [1, 2]:
                            if st.session_state.get(f"ch{ch_num}_running"):
                                inst.set_trigger_delay(delay_val, channel=ch_num)
                        st.session_state.last_trigger_delay = delay_val
                        logger.info("Live: trigger delay updated to %d", delay_val)
                    except Exception as exc:
                        st.error(f"Failed to update trigger delay: {exc}")
                        logger.exception("Live trigger delay update error")
                        _close_live_connection()

# ================================================================== #
#  Pump-Probe tab
# ================================================================== #
with tab_pp:
    if _active_output_tab is not None and _active_output_tab != "pump_probe":
        _mode_label = "Simple Pulse" if _sp_running else "Pump-Probe"
        _chs = [str(ch) for ch in [1, 2]
                if st.session_state.get(f"ch{ch}_running")
                or st.session_state.get(f"pp_ch{ch}_running")]
        st.warning(
            f"{_mode_label} output is running (CH{', '.join(_chs)}). "
            "Stop output before switching modes."
        )
    else:
        _pp_left, _pp_right = st.columns([2, 1])

        with _pp_left:
            st.text_input(
                "Pulse Width [s]",
                value=format_si(_pp.get("pulse_width", 1e-8)),
                key="_w_pp_pulse_width",
            )
            st.text_input(
                "Pulse Interval [s]",
                value=format_si(_pp.get("pulse_interval", 2e-8)),
                key="_w_pp_pulse_interval",
            )

            # Parse pump-probe specific fields
            pp_parse_errors = list(common_parse_errors)
            pp_pulse_width_val: float | None = None
            pp_pulse_interval_val: float | None = None
            try:
                pp_pulse_width_val = parse_si(st.session_state._w_pp_pulse_width)
            except (ValueError, KeyError):
                pp_parse_errors.append(
                    f"pulse_width: invalid value \"{st.session_state.get('_w_pp_pulse_width', '')}\""
                )
            try:
                pp_pulse_interval_val = parse_si(st.session_state._w_pp_pulse_interval)
            except (ValueError, KeyError):
                pp_parse_errors.append(
                    f"pulse_interval: invalid value \"{st.session_state.get('_w_pp_pulse_interval', '')}\""
                )

            pp_config: PumpProbeConfig | None = None
            if not pp_parse_errors and pp_pulse_width_val is not None and pp_pulse_interval_val is not None:
                pp_config = PumpProbeConfig(
                    visa_address=visa_address,
                    v_on=v_on,
                    v_off=v_off,
                    frequency=common_parsed["frequency"],
                    trigger_delay=int(trigger_delay),
                    resolution_n=int(resolution_n),
                    pulse_width=pp_pulse_width_val,
                    pulse_interval=pp_pulse_interval_val,
                )

            errors_pp = list(pp_parse_errors)
            if pp_config is not None:
                errors_pp.extend(pp_config.validate())

            if errors_pp:
                st.error("Configuration error:\n" + "\n".join(f"- {e}" for e in errors_pp))
            else:
                st.success("Parameters OK")
                if pp_config is not None:
                    _show_arb_info(
                        pp_config.frequency, [pp_config.pulse_width],
                        resolution_n=resolution_n,
                    )

            can_start_pp = not bool(errors_pp) and bool(visa_address) and pp_config is not None
            pp_ch1_running = st.session_state.get("pp_ch1_running", False)
            pp_ch2_running = st.session_state.get("pp_ch2_running", False)
            pp_is_live = st.session_state.get("live_connection", False)
            pp_live_on = False
            pp_live_off = False

            c1, c2, c3 = st.columns(3)
            with c1:
                if pp_ch1_running:
                    pp_btn_ch1 = st.button("Stop CH1", type="primary", use_container_width=True, key="_pp_btn_ch1")
                else:
                    pp_btn_ch1 = st.button(
                        "Start CH1", use_container_width=True,
                        disabled=not can_start_pp, key="_pp_btn_ch1",
                    )
            with c2:
                if pp_ch2_running:
                    pp_btn_ch2 = st.button("Stop CH2", type="primary", use_container_width=True, key="_pp_btn_ch2")
                else:
                    pp_btn_ch2 = st.button(
                        "Start CH2", use_container_width=True,
                        disabled=not can_start_pp, key="_pp_btn_ch2",
                    )
            with c3:
                if pp_is_live:
                    pp_live_off = st.button("Live Off", type="primary", use_container_width=True, key="_pp_live_off")
                else:
                    pp_live_on = st.button(
                        "Live On", use_container_width=True,
                        disabled=not bool(visa_address), key="_pp_live_on",
                    )

            if st.session_state.get("live_connection"):
                st.warning("Live Connection: ON (front panel locked in REMOTE mode)")
            if pp_ch1_running:
                st.info("CH1: Pump-probe output is ON.")
            if pp_ch2_running:
                st.info("CH2: Pump-probe output is ON.")

        with _pp_right:
            if "saved_pp_records" not in st.session_state:
                st.session_state.saved_pp_records = []

            _pp_sv1, _pp_sv2 = st.columns(2)
            with _pp_sv1:
                _pp_btn_save = st.button("Save", type="primary", use_container_width=True, key="_pp_save")
            with _pp_sv2:
                _pp_btn_clear = st.button("Clear", use_container_width=True, key="_pp_clear")

            if _pp_btn_save:
                iv = st.session_state.get("_w_pp_pulse_interval", "")
                new_record = {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "pulse_interval": iv,
                    "trigger_delay": int(trigger_delay),
                }
                records = st.session_state.saved_pp_records
                replaced = False
                for i, r in enumerate(records):
                    if r["pulse_interval"] == iv:
                        records[i] = new_record
                        replaced = True
                        break
                if not replaced:
                    records.append(new_record)
                records.sort(key=lambda r: parse_si(r["pulse_interval"]))
                _save_pp_records_to_csv(records)
                st.rerun()

            if _pp_btn_clear:
                st.session_state.saved_pp_records = []
                _save_pp_records_to_csv([])
                st.rerun()

            if st.session_state.saved_pp_records:
                lines = ["timestamp,pulse_interval,trigger_delay"]
                for r in st.session_state.saved_pp_records:
                    lines.append(f"{r['timestamp']},{r['pulse_interval']},{r['trigger_delay']}")
                st.markdown("```csv\n" + "\n".join(lines) + "\n```")

        # CH1 toggle (pump-probe)
        if pp_btn_ch1:
            if pp_ch1_running:
                st.session_state.pp_ch1_running = False
                try:
                    _pulse_stop(visa_address, channel=1)
                except Exception as exc:
                    logger.error("Teardown CH1 error: %s", exc)
                logger.info("Pump-probe CH1 stopped via UI")
                st.rerun()
            elif pp_config is not None:
                try:
                    _pump_probe_start(pp_config, channel=1)
                    st.session_state.pp_ch1_running = True
                    logger.info("Pump-probe CH1 started via UI")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error: {exc}")
                    logger.exception("Error starting pump-probe CH1")

        # CH2 toggle (pump-probe)
        if pp_btn_ch2:
            if pp_ch2_running:
                st.session_state.pp_ch2_running = False
                try:
                    _pulse_stop(visa_address, channel=2)
                except Exception as exc:
                    logger.error("Teardown CH2 error: %s", exc)
                logger.info("Pump-probe CH2 stopped via UI")
                st.rerun()
            elif pp_config is not None:
                try:
                    _pump_probe_start(pp_config, channel=2)
                    st.session_state.pp_ch2_running = True
                    logger.info("Pump-probe CH2 started via UI")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error: {exc}")
                    logger.exception("Error starting pump-probe CH2")

        # Live connection (pump-probe tab)
        if pp_live_on:
            try:
                inst = PulseInstrument(visa_address)
                st.session_state.live_instrument = inst
                st.session_state.live_connection = True
                delay_val = int(trigger_delay)
                for ch_num in [1, 2]:
                    if st.session_state.get(f"pp_ch{ch_num}_running"):
                        inst.set_trigger_delay(delay_val, channel=ch_num)
                st.session_state.last_trigger_delay = delay_val
                logger.info("Live connection opened (pump-probe tab)")
                st.rerun()
            except Exception as exc:
                st.error(f"Live connection failed: {exc}")
                st.session_state.live_connection = False
                logger.exception("Live connection error")

        if pp_live_off:
            _close_live_connection()
            st.rerun()

        # Live trigger delay update (pump-probe tab)
        if pp_is_live and not pp_live_off:
            delay_val = int(trigger_delay)
            prev_delay = st.session_state.get("last_trigger_delay")
            if prev_delay is not None and delay_val != prev_delay:
                inst = st.session_state.get("live_instrument")
                if inst is not None:
                    try:
                        for ch_num in [1, 2]:
                            if st.session_state.get(f"pp_ch{ch_num}_running"):
                                inst.set_trigger_delay(delay_val, channel=ch_num)
                        st.session_state.last_trigger_delay = delay_val
                        logger.info("Live (PP): trigger delay updated to %d", delay_val)
                    except Exception as exc:
                        st.error(f"Failed to update trigger delay: {exc}")
                        logger.exception("Live trigger delay update error (PP)")
                        _close_live_connection()

# ================================================================== #
#  Width Sweep tab
# ================================================================== #
with tab_sweep:
    if _active_output_tab is not None and _active_output_tab != "width_sweep":
        _mode_label = "Simple Pulse" if _sp_running else "Pump-Probe"
        _chs = [str(ch) for ch in [1, 2]
                if st.session_state.get(f"ch{ch}_running")
                or st.session_state.get(f"pp_ch{ch}_running")]
        st.warning(
            f"{_mode_label} output is running (CH{', '.join(_chs)}). "
            "Stop output before switching modes."
        )
    else:
        col_range, col_timing, col_opts = st.columns(3)

        with col_range:
            st.text_input(
                "Width Start [s]",
                value=format_si(_ws.get("width_start", 1e-8)),
                key="_w_width_start",
            )
            st.text_input(
                "Width Stop [s]",
                value=format_si(_ws.get("width_stop", 5e-8)),
                key="_w_width_stop",
            )
            st.text_input(
                "Width Step [s]",
                value=format_si(_ws.get("width_step", 5e-9)),
                key="_w_width_step",
                help="Default step (or step for last zone when variable step is enabled)",
            )
            _var_step_default = bool(_ws.get("step_zones"))
            variable_step = st.checkbox(
                "Variable step size", value=_var_step_default, key="_w_variable_step",
            )
            if variable_step:
                _sz = _ws.get("step_zones", [])
                _z1 = _sz[0] if len(_sz) >= 1 else (None, None)
                _z2 = _sz[1] if len(_sz) >= 2 else (None, None)
                # Build expander title showing current zone values
                _exp_parts: list[str] = []
                _z1_b = st.session_state.get("_w_step_zone1_boundary", "").strip()
                _z1_s = st.session_state.get("_w_step_zone1_step", "").strip()
                if _z1_b and _z1_s:
                    _exp_parts.append(f"{_z1_s} (~ {_z1_b})")
                _z2_b = st.session_state.get("_w_step_zone2_boundary", "").strip()
                _z2_s = st.session_state.get("_w_step_zone2_step", "").strip()
                if _z2_b and _z2_s:
                    _exp_parts.append(f"{_z2_s} (~ {_z2_b})")
                _exp_title = "Step Zones: " + ", ".join(_exp_parts) if _exp_parts else "Step Zones"
                with st.expander(_exp_title, expanded=True):
                    _zc1, _zc2 = st.columns(2)
                    with _zc1:
                        st.text_input(
                            "Zone 1: width ≤ [s]",
                            value=format_si(_z1[0]) if _z1[0] is not None else "",
                            key="_w_step_zone1_boundary",
                        )
                    with _zc2:
                        st.text_input(
                            "Zone 1 step [s]",
                            value=format_si(_z1[1]) if _z1[1] is not None else "",
                            key="_w_step_zone1_step",
                        )
                    _zc3, _zc4 = st.columns(2)
                    with _zc3:
                        st.text_input(
                            "Zone 2: width ≤ [s]",
                            value=format_si(_z2[0]) if _z2[0] is not None else "",
                            key="_w_step_zone2_boundary",
                            help="Leave blank if only 1 zone boundary needed",
                        )
                    with _zc4:
                        st.text_input(
                            "Zone 2 step [s]",
                            value=format_si(_z2[1]) if _z2[1] is not None else "",
                            key="_w_step_zone2_step",
                        )
                    st.caption("Above last boundary → uses Width Step as default step")

        with col_timing:
            st.text_input(
                "Wait Time [s]",
                value=format_si(_ws.get("wait_time", 1.0)),
                key="_w_wait_time",
            )
            sweep_settling_time = st.number_input(
                "Settling Time [s]",
                value=_ws.get("settling_time", 0.0), min_value=0.0, step=1.0, format="%.1f",
                help="Wait time before sweep starts (for DUT to reach steady state)",
                key="_w_settling_time",
            )
            sweep_channel = st.radio(
                "Channel", ["CH1", "CH2", "Both"], horizontal=True, key="_sweep_ch",
            )

        waveform_mode = "arbitrary"
        with col_opts:
            delay_mode = st.radio(
                "Delay Mode", ["Exponent", "Table"],
                horizontal=True, key="_w_delay_mode_radio",
            )
            _delay_mode_val = "exponent" if delay_mode == "Exponent" else "table"

            if _delay_mode_val == "exponent":
                sweep_trigger_delay_stop = st.number_input(
                    "Trigger Delay Stop [points] (×8)",
                    value=_common.get("trigger_delay", 0), min_value=0, step=8,
                    help="End value for trigger delay sweep. "
                         "Set equal to Trigger Delay for fixed delay.",
                    key="_w_trigger_delay_stop",
                )
                delay_exponent = st.number_input(
                    "Delay Exponent",
                    value=_ws.get("delay_exponent", 1.0),
                    min_value=-4.0, max_value=4.0, step=0.25, format="%.2f",
                    help="delay = a × pw^n + b (1=linear, -1=1/pw)",
                    key="_w_delay_exponent",
                )
            else:
                sweep_trigger_delay_stop = int(trigger_delay)  # not used in table mode
                delay_exponent = 1.0  # not used in table mode
                records = st.session_state.get("saved_pulse_records", [])
                if len(records) < 2:
                    st.warning("Table mode requires >= 2 saved records (use Simple Pulse tab).")
                else:
                    # st.caption(f"Delay table: {len(records)} points")
                    # for r in records:
                    #     st.text(f"  {r['pulse_width']}s → {r['trigger_delay']} pts")
                    with st.expander(f"Delay Table: {len(records)} points"):
                        # for r in records:
                        #     st.text(f"  {r['pulse_width']}s → {r['trigger_delay']} pts")
                        st.table({
                            "Pulse Width [s]": [r["pulse_width"] for r in records],
                            "Trigger Delay [pts]": [r["trigger_delay"] for r in records],
                        })

        # st.info("Pulse center is fixed at the middle of the period during sweep.")

        # Parse sweep-specific fields
        sweep_parse_errors = list(common_parse_errors)
        sweep_parsed = dict(common_parsed)

        for name, key in {
            "width_start": "_w_width_start",
            "width_stop": "_w_width_stop",
            "width_step": "_w_width_step",
            "wait_time": "_w_wait_time",
        }.items():
            try:
                sweep_parsed[name] = parse_si(st.session_state[key])
            except (ValueError, KeyError):
                sweep_parse_errors.append(
                    f"{name}: invalid value \"{st.session_state.get(key, '')}\""
                )

        # Build step_zones from UI
        _step_zones: list[tuple[float, float]] | None = None
        if st.session_state.get("_w_variable_step", False):
            _zones_list: list[tuple[float, float]] = []
            for _zn in ("zone1", "zone2"):
                _b_raw = st.session_state.get(f"_w_step_{_zn}_boundary", "").strip()
                _s_raw = st.session_state.get(f"_w_step_{_zn}_step", "").strip()
                if _b_raw and _s_raw:
                    try:
                        _zones_list.append((parse_si(_b_raw), parse_si(_s_raw)))
                    except ValueError:
                        sweep_parse_errors.append(f"step {_zn}: invalid value")
            if _zones_list:
                _step_zones = _zones_list

        # Build sweep config
        if not sweep_parse_errors:
            _delay_stop_val = int(sweep_trigger_delay_stop)
            # Build delay_table from saved_pulse_records when in table mode
            _delay_table: list[tuple[float, int]] | None = None
            if _delay_mode_val == "table":
                _records = st.session_state.get("saved_pulse_records", [])
                if _records:
                    _delay_table = [
                        (parse_si(r["pulse_width"]), int(r["trigger_delay"]))
                        for r in _records
                    ]
            sweep_config_built = SweepConfig(
                visa_address=visa_address,
                v_on=v_on,
                v_off=v_off,
                width_start=sweep_parsed["width_start"],
                width_stop=sweep_parsed["width_stop"],
                width_step=sweep_parsed["width_step"],
                frequency=sweep_parsed["frequency"],
                trigger_delay=int(trigger_delay),
                resolution_n=int(resolution_n),
                wait_time=sweep_parsed["wait_time"],
                waveform_mode=waveform_mode,
                settling_time=sweep_settling_time,
                trigger_delay_stop=_delay_stop_val if _delay_stop_val != int(trigger_delay) else None,
                delay_exponent=delay_exponent,
                delay_mode=_delay_mode_val,
                delay_table=_delay_table,
                step_zones=_step_zones,
            )

        # Validation
        errors_sweep = list(sweep_parse_errors)
        if sweep_config_built is not None:
            errors_sweep.extend(sweep_config_built.validate())

        if errors_sweep:
            st.error("Configuration error:\n" + "\n".join(f"- {e}" for e in errors_sweep))
        else:
            st.success("Parameters OK")
            if sweep_config_built is not None:
                widths = _generate_widths(
                    sweep_config_built.width_start,
                    sweep_config_built.width_stop,
                    sweep_config_built.width_step,
                    step_zones=sweep_config_built.step_zones,
                )
                _show_arb_info(sweep_config_built.frequency, widths, resolution_n=resolution_n)

        # Run sweep
        if st.button("Start Sweep", disabled=bool(errors_sweep) or not visa_address, type="primary",
                      key="_btn_start_width_sweep"):
            config = sweep_config_built
            channels = _CHANNEL_MAP[sweep_channel]
            logger.info("Width sweep started (channels=%s)", channels)
            progress = st.progress(0, text="Connecting...")

            instrument = None
            try:
                instrument = PulseInstrument(config.visa_address)
                progress.progress(0, text="Setting up instrument...")

                widths = _generate_widths(
                    config.width_start, config.width_stop, config.width_step,
                    step_zones=config.step_zones,
                )

                def on_upload(i: int, total: int) -> None:
                    progress.progress(
                        (i + 1) / total,
                        text=f"Uploading segments... [{i + 1}/{total}]",
                    )

                for ch in channels:
                    instrument.setup_arbitrary(
                        config, widths, channel=ch, callback=on_upload,
                    )

                # Settling phase
                if config.settling_time > 0:
                    t0 = time.time()
                    while (elapsed := time.time() - t0) < config.settling_time:
                        pct = elapsed / config.settling_time
                        progress.progress(
                            pct,
                            text=f"Settling... {elapsed:.1f}s / {config.settling_time:.1f}s",
                        )
                        time.sleep(0.2)

                sweep_start = time.time()

                def on_step(i: int, total: int) -> None:
                    pct = (i + 1) / total
                    elapsed = time.time() - sweep_start
                    rate = (i + 1) / elapsed if elapsed > 0 else 0
                    remaining = (total - i - 1) / rate if rate > 0 else 0
                    progress.progress(
                        pct,
                        text=(
                            f"Sweeping... {i + 1}/{total}"
                            f" ({elapsed:.1f}s elapsed, ~{remaining:.0f}s remaining)"
                        ),
                    )

                run_sweep(config, instrument, callback=on_step, channels=channels)

                for ch in channels:
                    instrument.teardown(channel=ch)

                progress.progress(1.0, text="Done!")
                logger.info("Width sweep completed")

            except Exception as exc:
                st.error(f"Error: {exc}")
                logger.exception("Error during width sweep")
            finally:
                if instrument is not None:
                    instrument.close()

        # ============================================================ #
        #  Auto Sweep (Voltage-Triggered Integration)
        # ============================================================ #
        st.divider()
        st.text("Auto Sweep (Voltage-Triggered)")

        # Detection mode selector + common params
        ig_mode_col, ig_common_col = st.columns([1, 2])

        with ig_mode_col:
            with st.expander(f"DMM Settings ({_ig.get("dmm_visa_address", DEFAULT_34401A_ADDRESS)})", expanded=False):
                st.text_input(
                    "DMM VISA Address",
                    value=_ig.get("dmm_visa_address", DEFAULT_34401A_ADDRESS),
                    key="_w_ig_dmm_address",
                )
                _dmm_btn_col1, _dmm_btn_col2 = st.columns(2)
                with _dmm_btn_col1:
                    if st.button("Check DMM", key="_btn_check_dmm", use_container_width=True):
                        with st.spinner("Checking DMM..."):
                            try:
                                idn = Multimeter.check_connection(
                                    st.session_state.get("_w_ig_dmm_address", DEFAULT_34401A_ADDRESS),
                                )
                                st.success(f"DMM OK: {idn}")
                            except Exception as exc:
                                st.error(f"DMM failed: {exc}")
                with _dmm_btn_col2:
                    if st.button("Read Once", key="_btn_dmm_read_once", use_container_width=True):
                        with st.spinner("Reading..."):
                            try:
                                _dmm_addr = st.session_state.get("_w_ig_dmm_address", DEFAULT_34401A_ADDRESS)
                                _dmm = Multimeter(_dmm_addr)
                                _dmm.configure_dc_voltage()
                                _val = _dmm.read()
                                _dmm.close()
                                with st.container(border=True):
                                    st.text(f"DMM Voltage: {_val:.4f} V")
                            except Exception as exc:
                                st.error(f"DMM read failed: {exc}")

        with ig_common_col:
            _cc1, _cc2 = st.columns(2)
            with _cc1:
                ig_poll_interval = st.number_input(
                    "Poll Interval [s]",
                    value=_ig.get("poll_interval", 1.0),
                    min_value=0.1, step=0.5, format="%.1f",
                    key="_w_ig_poll_interval",
                    help="Interval between DMM voltage readings. Shorter = more accurate detection, but increases communication load.",
                )
            with _cc2:
                ig_num_cycles = st.number_input(
                    "Cycles (0 = infinite)",
                    value=_ig.get("num_cycles", 0),
                    min_value=0, step=1,
                    key="_w_ig_num_cycles",
                    help="Number of detect-then-sweep cycles. Set 0 for infinite loop (stop by reloading the page).",
                )

        # Ramp detection parameters
        _r1, _r2, _r3 = st.columns(3)
        with _r1:
            ig_trigger_start = st.number_input(
                "Trigger Start [V]",
                value=_ig.get("trigger_start_voltage", -9.8),
                format="%.2f",
                key="_w_ig_trigger_start",
                help="Start collecting fit data when voltage crosses this value upward. Must be below Trigger End.",
            )
        with _r2:
            ig_trigger_end = st.number_input(
                "Trigger End [V]",
                value=_ig.get("trigger_end_voltage", -9.2),
                format="%.2f",
                key="_w_ig_trigger_end",
                help="Stop collecting and perform linear fit at this voltage. The range from Start to End provides data for regression.",
            )
        with _r3:
            ig_sweep_start = st.number_input(
                "Sweep Start [V]",
                value=_ig.get("sweep_start_voltage", -9.0),
                format="%.2f",
                key="_w_ig_sweep_start",
                help="Predicted voltage at which the sweep begins. Calculated from the linear fit of the ramp.",
            )

        # Build and validate IntegrationConfig
        ig_config: IntegrationConfig | None = None
        ig_errors: list[str] = []

        if not errors_sweep and sweep_config_built is not None:
            ig_config = IntegrationConfig(
                dmm_visa_address=st.session_state.get("_w_ig_dmm_address", DEFAULT_34401A_ADDRESS),
                trigger_start_voltage=float(ig_trigger_start),
                trigger_end_voltage=float(ig_trigger_end),
                sweep_start_voltage=float(ig_sweep_start),
                poll_interval=float(ig_poll_interval),
                num_cycles=int(ig_num_cycles),
            )
            ig_errors = ig_config.validate()

        if ig_errors:
            st.error("Integration config error:\n" + "\n".join(f"- {e}" for e in ig_errors))

        can_start_auto = (
            not bool(errors_sweep)
            and not bool(ig_errors)
            and bool(visa_address)
            and sweep_config_built is not None
            and ig_config is not None
        )

        if ig_num_cycles == 0:
            st.caption("Cycles=0: runs until page is refreshed.")

        if st.button(
            "Start Auto Sweep",
            disabled=not can_start_auto,
            type="primary",
            key="_btn_start_auto_sweep",
        ):
            config = sweep_config_built
            integration = ig_config
            channels = _CHANNEL_MAP[sweep_channel]
            logger.info("Auto sweep started (channels=%s, cycles=%s)", channels, integration.num_cycles)

            cycle_status = st.empty()
            phase_status = st.empty()
            voltage_display = st.empty()
            progress = st.progress(0)

            instrument = None
            dmm = None
            try:
                # Connect AWG
                phase_status.info("Connecting to AWG...")
                instrument = PulseInstrument(config.visa_address)

                # Connect DMM
                phase_status.info("Connecting to DMM...")
                dmm = Multimeter(integration.dmm_visa_address)
                dmm.configure_dc_voltage()

                # Upload waveforms (once)
                widths = _generate_widths(
                    config.width_start, config.width_stop, config.width_step,
                    step_zones=config.step_zones,
                )

                def on_auto_upload(i: int, total: int) -> None:
                    progress.progress(
                        (i + 1) / total,
                        text=f"Uploading segments... [{i + 1}/{total}]",
                    )

                for ch in channels:
                    instrument.setup_arbitrary(config, widths, channel=ch, callback=on_auto_upload)

                # Settling phase (if configured)
                if config.settling_time > 0:
                    phase_status.info("Settling...")
                    t0 = time.time()
                    while (elapsed := time.time() - t0) < config.settling_time:
                        pct = elapsed / config.settling_time
                        progress.progress(
                            pct,
                            text=f"Settling... {elapsed:.1f}s / {config.settling_time:.1f}s",
                        )
                        time.sleep(0.2)

                # Cycle loop
                max_cycles = integration.num_cycles
                cycle = 0

                while max_cycles == 0 or cycle < max_cycles:
                    cycle += 1
                    label = f"{cycle}/{max_cycles}" if max_cycles > 0 else f"{cycle}/inf"
                    cycle_status.markdown(f"**Cycle {label}**")

                    # Phase A: Detect ramp start
                    phase_status.info("Waiting for ramp...")
                    progress.progress(0, text="Monitoring voltage...")

                    def on_ramp(voltage: float, phase: str) -> None:
                        if phase == "waiting_low":
                            voltage_display.metric(
                                "DMM Voltage", f"{voltage:.4f} V",
                                delta="waiting for low voltage",
                            )
                        elif phase == "waiting_trigger":
                            voltage_display.metric(
                                "DMM Voltage", f"{voltage:.4f} V",
                                delta="waiting for ramp start",
                            )
                        else:  # collecting
                            voltage_display.metric(
                                "DMM Voltage", f"{voltage:.4f} V",
                                delta="collecting fit data",
                            )
                            phase_status.info("Collecting ramp data for linear fit...")

                    prediction = detect_ramp_start(dmm, integration, callback=on_ramp)

                    # Show prediction results
                    voltage_display.empty()
                    phase_status.info(
                        f"Fit: slope={prediction.slope:.4f} V/s, "
                        f"R\u00b2={prediction.r_squared:.4f}, "
                        f"n={prediction.n_points} pts"
                    )

                    # Phase B: Wait for predicted sweep start time
                    now = time.time()
                    wait_seconds = max(0.0, prediction.sweep_start_time - now)
                    if wait_seconds > 0:
                        t0 = time.time()
                        while (elapsed := time.time() - t0) < wait_seconds:
                            pct = elapsed / wait_seconds
                            remaining = wait_seconds - elapsed
                            progress.progress(
                                pct,
                                text=f"Sweep starts in {remaining:.1f}s",
                            )
                            time.sleep(0.2)

                    # Restore USER mode before sweep (2nd cycle onward)
                    if cycle > 1:
                        for ch in channels:
                            instrument.restore_user_mode(config, channel=ch)

                    # Phase C: Sweep
                    phase_status.info(f"Sweeping (cycle {label})...")
                    voltage_display.empty()
                    sweep_start = time.time()

                    def on_auto_step(i: int, total: int) -> None:
                        pct = (i + 1) / total
                        elapsed = time.time() - sweep_start
                        rate = (i + 1) / elapsed if elapsed > 0 else 0
                        remaining = (total - i - 1) / rate if rate > 0 else 0
                        progress.progress(
                            pct,
                            text=(
                                f"Sweeping... {i + 1}/{total}"
                                f" ({elapsed:.1f}s elapsed, ~{remaining:.0f}s remaining)"
                            ),
                        )

                    run_sweep(config, instrument, callback=on_auto_step, channels=channels)
                    logger.info("Auto sweep cycle %s complete", label)

                    # Set DC 0V during wait (no pulses between cycles)
                    for ch in channels:
                        instrument.set_between_cycles_dc_zero(channel=ch)
                    phase_status.info("Waiting (0V output)...")

                # All cycles complete
                for ch in channels:
                    instrument.teardown(channel=ch)
                cycle_status.success(f"Auto sweep complete ({cycle} cycle(s))")
                phase_status.empty()
                voltage_display.empty()
                progress.progress(1.0, text="Done!")
                logger.info("Auto sweep finished (%d cycles)", cycle)

            except Exception as exc:
                st.error(f"Error: {exc}")
                logger.exception("Error during auto sweep")
            finally:
                if instrument is not None:
                    instrument.close()
                if dmm is not None:
                    dmm.close()

# ================================================================== #
#  Interval Sweep tab (pump-probe mode)
# ================================================================== #
with tab_isweep:
    if _active_output_tab is not None and _active_output_tab != "interval_sweep":
        _mode_label = "Simple Pulse" if _sp_running else "Pump-Probe"
        _chs = [str(ch) for ch in [1, 2]
                if st.session_state.get(f"ch{ch}_running")
                or st.session_state.get(f"pp_ch{ch}_running")]
        st.warning(
            f"{_mode_label} output is running (CH{', '.join(_chs)}). "
            "Stop output before switching modes."
        )
    else:
        is_col_range, is_col_timing, is_col_opts = st.columns(3)

        with is_col_range:
            st.text_input(
                "Pulse Width [s] (fixed)",
                value=format_si(_isw.get("pulse_width", 1e-8)),
                key="_w_interval_pulse_width",
            )
            st.text_input(
                "Interval Start [s]",
                value=format_si(_isw.get("interval_start", 1e-8)),
                key="_w_interval_start",
            )
            st.text_input(
                "Interval Stop [s]",
                value=format_si(_isw.get("interval_stop", 5e-8)),
                key="_w_interval_stop",
            )
            st.text_input(
                "Interval Step [s]",
                value=format_si(_isw.get("interval_step", 5e-9)),
                key="_w_interval_step",
            )

            # Variable step zones
            _is_var_step = st.checkbox(
                "Variable step zones", key="_w_interval_variable_step",
            )
            _is_step_zones: list[tuple[float, float]] | None = None
            if _is_var_step:
                _isz1_b = st.text_input("Zone 1 boundary [s]", key="_w_interval_step_zone1_boundary")
                _isz1_s = st.text_input("Zone 1 step [s]", key="_w_interval_step_zone1_step")
                _isz2_b = st.text_input("Zone 2 boundary [s]", key="_w_interval_step_zone2_boundary")
                _isz2_s = st.text_input("Zone 2 step [s]", key="_w_interval_step_zone2_step")

                _is_step_zones = []
                for b_str, s_str in [(_isz1_b, _isz1_s), (_isz2_b, _isz2_s)]:
                    if b_str and s_str:
                        try:
                            _is_step_zones.append((parse_si(b_str), parse_si(s_str)))
                        except ValueError:
                            pass
                if not _is_step_zones:
                    _is_step_zones = None

        with is_col_timing:
            st.text_input(
                "Wait Time [s]",
                value=format_si(_isw.get("wait_time", 1.0)),
                key="_w_interval_wait_time",
            )
            is_settling_time = st.number_input(
                "Settling Time [s]",
                value=_isw.get("settling_time", 0.0), min_value=0.0, step=1.0, format="%.1f",
                help="Wait time before sweep starts",
                key="_w_interval_settling_time",
            )
            is_channel = st.radio(
                "Channel", ["CH1", "CH2", "Both"], horizontal=True, key="_isweep_ch",
            )

        with is_col_opts:
            is_delay_mode = st.radio(
                "Delay Mode", ["Exponent", "Table"], key="_w_interval_delay_mode_radio",
            )
            _is_delay_mode_val = "exponent" if is_delay_mode == "Exponent" else "table"
            is_delay_exponent = 1.0
            _is_delay_stop_val = int(trigger_delay)

            if _is_delay_mode_val == "exponent":
                _is_delay_stop_val = st.number_input(
                    "Trigger Delay Stop [points] (×8)",
                    value=_isw.get("trigger_delay_stop", int(trigger_delay)),
                    min_value=0, step=8,
                    key="_w_interval_trigger_delay_stop",
                )
                is_delay_exponent = st.number_input(
                    "Delay Exponent",
                    value=_isw.get("delay_exponent", 1.0),
                    min_value=-4.0, max_value=4.0, step=0.25, format="%.2f",
                    help="delay = a × interval^n + b (1=linear, -1=1/interval)",
                    key="_w_interval_delay_exponent",
                )
            else:
                _pp_records = st.session_state.get("saved_pp_records", [])
                if len(_pp_records) < 2:
                    st.warning("Table mode requires ≥ 2 saved pump-probe records.")
                else:
                    with st.expander("Delay Lookup Table"):
                        import pandas as pd
                        _tbl_data = [
                            {"Pulse Interval [s]": r["pulse_interval"], "Trigger Delay [pts]": r["trigger_delay"]}
                            for r in _pp_records
                        ]
                        st.dataframe(pd.DataFrame(_tbl_data), hide_index=True)

        # Parse interval sweep fields
        is_parse_errors = list(common_parse_errors)
        is_parsed = dict(common_parsed)

        for name, key in [
            ("pulse_width", "_w_interval_pulse_width"),
            ("interval_start", "_w_interval_start"),
            ("interval_stop", "_w_interval_stop"),
            ("interval_step", "_w_interval_step"),
            ("wait_time", "_w_interval_wait_time"),
        ]:
            try:
                is_parsed[name] = parse_si(st.session_state.get(key, ""))
            except (ValueError, KeyError):
                is_parse_errors.append(
                    f"{name}: invalid value \"{st.session_state.get(key, '')}\""
                )

        # Build delay_table for interval sweep
        _is_delay_table: list[tuple[float, int]] | None = None
        if _is_delay_mode_val == "table":
            _pp_recs = st.session_state.get("saved_pp_records", [])
            if _pp_recs:
                _is_delay_table = [
                    (parse_si(r["pulse_interval"]), int(r["trigger_delay"]))
                    for r in _pp_recs
                ]

        # Build config
        interval_config_built: IntervalSweepConfig | None = None
        if not is_parse_errors:
            interval_config_built = IntervalSweepConfig(
                visa_address=visa_address,
                v_on=v_on,
                v_off=v_off,
                frequency=is_parsed["frequency"],
                trigger_delay=int(trigger_delay),
                resolution_n=int(resolution_n),
                pulse_width=is_parsed["pulse_width"],
                interval_start=is_parsed["interval_start"],
                interval_stop=is_parsed["interval_stop"],
                interval_step=is_parsed["interval_step"],
                wait_time=is_parsed["wait_time"],
                settling_time=is_settling_time,
                trigger_delay_stop=_is_delay_stop_val if _is_delay_stop_val != int(trigger_delay) else None,
                delay_exponent=is_delay_exponent,
                delay_mode=_is_delay_mode_val,
                delay_table=_is_delay_table,
                step_zones=_is_step_zones,
            )

        # Validation
        errors_isweep = list(is_parse_errors)
        if interval_config_built is not None:
            errors_isweep.extend(interval_config_built.validate())

        if errors_isweep:
            st.error("Configuration error:\n" + "\n".join(f"- {e}" for e in errors_isweep))
        else:
            st.success("Parameters OK")
            if interval_config_built is not None:
                intervals_preview = _generate_intervals(
                    interval_config_built.interval_start,
                    interval_config_built.interval_stop,
                    interval_config_built.interval_step,
                    step_zones=interval_config_built.step_zones,
                )
                try:
                    _is_sr, _is_pts = _calc_arb_params(
                        interval_config_built.frequency,
                        [interval_config_built.pulse_width],
                        intervals=intervals_preview,
                        resolution_n=resolution_n,
                    )
                    _is_tpp = 1.0 / interval_config_built.frequency / _is_pts
                    with st.expander("Arbitrary Waveform Details"):
                        st.json({
                            "segments": len(intervals_preview),
                            "points_per_period": _is_pts,
                            "sample_rate": f"{_is_sr:.3e} Sa/s",
                            "time_per_point": f"{format_si(_is_tpp)}s",
                            "delay_resolution (×8)": f"{format_si(8 * _is_tpp)}s",
                            "total_memory": f"{len(intervals_preview) * _is_pts:,} words",
                        })
                except Exception:
                    pass

        # Run interval sweep
        if st.button("Start Interval Sweep", disabled=bool(errors_isweep) or not visa_address,
                      type="primary", key="_btn_start_interval_sweep"):
            config = interval_config_built
            channels = _CHANNEL_MAP[is_channel]
            logger.info("Interval sweep started (channels=%s)", channels)
            progress = st.progress(0, text="Connecting...")

            instrument = None
            try:
                instrument = PulseInstrument(config.visa_address)
                progress.progress(0, text="Setting up instrument...")

                intervals_list = _generate_intervals(
                    config.interval_start, config.interval_stop, config.interval_step,
                    step_zones=config.step_zones,
                )

                def on_is_upload(i: int, total: int) -> None:
                    progress.progress(
                        (i + 1) / total,
                        text=f"Uploading segments... [{i + 1}/{total}]",
                    )

                for ch in channels:
                    instrument.setup_pump_probe_arbitrary(
                        config, config.pulse_width, intervals_list,
                        channel=ch, callback=on_is_upload,
                    )

                # Settling phase
                if config.settling_time > 0:
                    t0 = time.time()
                    while (elapsed := time.time() - t0) < config.settling_time:
                        pct = elapsed / config.settling_time
                        progress.progress(
                            pct,
                            text=f"Settling... {elapsed:.1f}s / {config.settling_time:.1f}s",
                        )
                        time.sleep(0.2)

                sweep_start = time.time()

                def on_is_step(i: int, total: int) -> None:
                    pct = (i + 1) / total
                    elapsed = time.time() - sweep_start
                    rate = (i + 1) / elapsed if elapsed > 0 else 0
                    remaining = (total - i - 1) / rate if rate > 0 else 0
                    progress.progress(
                        pct,
                        text=(
                            f"Sweeping... {i + 1}/{total}"
                            f" ({elapsed:.1f}s elapsed, ~{remaining:.0f}s remaining)"
                        ),
                    )

                run_interval_sweep(config, instrument, callback=on_is_step, channels=channels)

                for ch in channels:
                    instrument.teardown(channel=ch)

                progress.progress(1.0, text="Done!")
                logger.info("Interval sweep completed")

            except Exception as exc:
                st.error(f"Error: {exc}")
                logger.exception("Error during interval sweep")
            finally:
                if instrument is not None:
                    instrument.close()

        # ============================================================ #
        #  Auto Sweep (Voltage-Triggered) for Interval Sweep
        # ============================================================ #
        st.divider()
        st.text("Auto Sweep (Voltage-Triggered)")

        is_ig_mode_col, is_ig_common_col = st.columns([1, 2])

        with is_ig_mode_col:
            with st.expander(f"DMM Settings ({_ig.get('dmm_visa_address', DEFAULT_34401A_ADDRESS)})", expanded=False):
                st.text_input(
                    "DMM VISA Address",
                    value=_ig.get("dmm_visa_address", DEFAULT_34401A_ADDRESS),
                    key="_w_is_ig_dmm_address",
                )

        with is_ig_common_col:
            _isc1, _isc2 = st.columns(2)
            with _isc1:
                is_ig_poll = st.number_input(
                    "Poll Interval [s]",
                    value=_ig.get("poll_interval", 1.0),
                    min_value=0.1, step=0.5, format="%.1f",
                    key="_w_is_ig_poll_interval",
                )
            with _isc2:
                is_ig_cycles = st.number_input(
                    "Cycles (0 = infinite)",
                    value=_ig.get("num_cycles", 0),
                    min_value=0, step=1,
                    key="_w_is_ig_num_cycles",
                )

        _isr1, _isr2, _isr3 = st.columns(3)
        with _isr1:
            is_ig_trig_start = st.number_input(
                "Trigger Start [V]",
                value=_ig.get("trigger_start_voltage", -9.8),
                format="%.2f",
                key="_w_is_ig_trigger_start",
            )
        with _isr2:
            is_ig_trig_end = st.number_input(
                "Trigger End [V]",
                value=_ig.get("trigger_end_voltage", -9.2),
                format="%.2f",
                key="_w_is_ig_trigger_end",
            )
        with _isr3:
            is_ig_sweep_start = st.number_input(
                "Sweep Start [V]",
                value=_ig.get("sweep_start_voltage", -9.0),
                format="%.2f",
                key="_w_is_ig_sweep_start",
            )

        is_ig_config: IntegrationConfig | None = None
        is_ig_errors: list[str] = []

        if not errors_isweep and interval_config_built is not None:
            is_ig_config = IntegrationConfig(
                dmm_visa_address=st.session_state.get("_w_is_ig_dmm_address", DEFAULT_34401A_ADDRESS),
                trigger_start_voltage=float(is_ig_trig_start),
                trigger_end_voltage=float(is_ig_trig_end),
                sweep_start_voltage=float(is_ig_sweep_start),
                poll_interval=float(is_ig_poll),
                num_cycles=int(is_ig_cycles),
            )
            is_ig_errors = is_ig_config.validate()

        if is_ig_errors:
            st.error("Integration config error:\n" + "\n".join(f"- {e}" for e in is_ig_errors))

        can_start_auto_is = (
            not bool(errors_isweep)
            and not bool(is_ig_errors)
            and bool(visa_address)
            and interval_config_built is not None
            and is_ig_config is not None
        )

        if is_ig_cycles == 0:
            st.caption("Cycles=0: runs until page is refreshed.")

        if st.button(
            "Start Auto Interval Sweep",
            disabled=not can_start_auto_is,
            type="primary",
            key="_btn_start_auto_interval_sweep",
        ):
            config = interval_config_built
            integration = is_ig_config
            channels = _CHANNEL_MAP[is_channel]
            logger.info("Auto interval sweep started (channels=%s, cycles=%s)", channels, integration.num_cycles)

            cycle_status = st.empty()
            phase_status = st.empty()
            voltage_display = st.empty()
            progress = st.progress(0)

            instrument = None
            dmm = None
            try:
                phase_status.info("Connecting to AWG...")
                instrument = PulseInstrument(config.visa_address)

                phase_status.info("Connecting to DMM...")
                dmm = Multimeter(integration.dmm_visa_address)
                dmm.configure_dc_voltage()

                intervals_list = _generate_intervals(
                    config.interval_start, config.interval_stop, config.interval_step,
                    step_zones=config.step_zones,
                )

                def on_auto_is_upload(i: int, total: int) -> None:
                    progress.progress(
                        (i + 1) / total,
                        text=f"Uploading segments... [{i + 1}/{total}]",
                    )

                for ch in channels:
                    instrument.setup_pump_probe_arbitrary(
                        config, config.pulse_width, intervals_list,
                        channel=ch, callback=on_auto_is_upload,
                    )

                if config.settling_time > 0:
                    phase_status.info("Settling...")
                    t0 = time.time()
                    while (elapsed := time.time() - t0) < config.settling_time:
                        pct = elapsed / config.settling_time
                        progress.progress(
                            pct,
                            text=f"Settling... {elapsed:.1f}s / {config.settling_time:.1f}s",
                        )
                        time.sleep(0.2)

                max_cycles = integration.num_cycles
                cycle = 0

                while max_cycles == 0 or cycle < max_cycles:
                    cycle += 1
                    label = f"{cycle}/{max_cycles}" if max_cycles > 0 else f"{cycle}/inf"
                    cycle_status.markdown(f"**Cycle {label}**")

                    phase_status.info("Waiting for ramp...")
                    progress.progress(0, text="Monitoring voltage...")

                    def on_is_ramp(voltage: float, phase: str) -> None:
                        if phase == "waiting_low":
                            voltage_display.metric(
                                "DMM Voltage", f"{voltage:.4f} V",
                                delta="waiting for low voltage",
                            )
                        elif phase == "waiting_trigger":
                            voltage_display.metric(
                                "DMM Voltage", f"{voltage:.4f} V",
                                delta="waiting for ramp start",
                            )
                        else:
                            voltage_display.metric(
                                "DMM Voltage", f"{voltage:.4f} V",
                                delta="collecting fit data",
                            )
                            phase_status.info("Collecting ramp data for linear fit...")

                    prediction = detect_ramp_start(dmm, integration, callback=on_is_ramp)

                    voltage_display.empty()
                    phase_status.info(
                        f"Fit: slope={prediction.slope:.4f} V/s, "
                        f"R\u00b2={prediction.r_squared:.4f}, "
                        f"n={prediction.n_points} pts"
                    )

                    now = time.time()
                    wait_seconds = max(0.0, prediction.sweep_start_time - now)
                    if wait_seconds > 0:
                        t0 = time.time()
                        while (elapsed := time.time() - t0) < wait_seconds:
                            pct = elapsed / wait_seconds
                            remaining = wait_seconds - elapsed
                            progress.progress(pct, text=f"Sweep starts in {remaining:.1f}s")
                            time.sleep(0.2)

                    if cycle > 1:
                        for ch in channels:
                            instrument.restore_user_mode(config, channel=ch)

                    phase_status.info(f"Sweeping (cycle {label})...")
                    voltage_display.empty()
                    sweep_start = time.time()

                    def on_auto_is_step(i: int, total: int) -> None:
                        pct = (i + 1) / total
                        elapsed = time.time() - sweep_start
                        rate = (i + 1) / elapsed if elapsed > 0 else 0
                        remaining = (total - i - 1) / rate if rate > 0 else 0
                        progress.progress(
                            pct,
                            text=(
                                f"Sweeping... {i + 1}/{total}"
                                f" ({elapsed:.1f}s elapsed, ~{remaining:.0f}s remaining)"
                            ),
                        )

                    run_interval_sweep(config, instrument, callback=on_auto_is_step, channels=channels)
                    logger.info("Auto interval sweep cycle %s complete", label)

                    for ch in channels:
                        instrument.set_between_cycles_dc_zero(channel=ch)
                    phase_status.info("Waiting (0V output)...")

                for ch in channels:
                    instrument.teardown(channel=ch)
                cycle_status.success(f"Auto interval sweep complete ({cycle} cycle(s))")
                phase_status.empty()
                voltage_display.empty()
                progress.progress(1.0, text="Done!")
                logger.info("Auto interval sweep finished (%d cycles)", cycle)

            except Exception as exc:
                st.error(f"Error: {exc}")
                logger.exception("Error during auto interval sweep")
            finally:
                if instrument is not None:
                    instrument.close()
                if dmm is not None:
                    dmm.close()

# ================================================================== #
#  Delay Sweep tab
# ================================================================== #
with tab_delay:
    if _active_output_tab is not None and _active_output_tab != "delay_sweep":
        _mode_label = "Simple Pulse" if _sp_running else "Pump-Probe"
        _chs = [str(ch) for ch in [1, 2]
                if st.session_state.get(f"ch{ch}_running")
                or st.session_state.get(f"pp_ch{ch}_running")]
        st.warning(
            f"{_mode_label} output is running (CH{', '.join(_chs)}). "
            "Stop output before switching modes."
        )
    else:
        col_d1, col_d2, col_d3 = st.columns([2, 2, 1])

        with col_d1:
            st.text_input(
                "Pulse Width [s]",
                value=format_si(_ds.get("pulse_width", 1e-8)),
                key="_w_delay_pulse_width",
            )
            st.number_input(
                "Delay Start [points] (×8)",
                value=_ds.get("delay_start", 0), min_value=0, step=8,
                key="_w_delay_start",
            )
            st.number_input(
                "Delay Stop [points] (×8)",
                value=_ds.get("delay_stop", 80), min_value=0, step=8,
                key="_w_delay_stop",
            )

        with col_d2:
            st.number_input(
                "Delay Step [points] (×8)",
                value=_ds.get("delay_step", 8), min_value=8, step=8,
                key="_w_delay_step",
            )
            st.text_input(
                "Wait Time [s]",
                value=format_si(_ds.get("wait_time", 1.0)),
                key="_w_delay_wait_time",
            )
            delay_settling_time = st.number_input(
                "Settling Time [s]",
                value=_ds.get("settling_time", 0.0), min_value=0.0, step=1.0, format="%.1f",
                help="Wait time before sweep starts (for DUT to reach steady state)",
                key="_w_delay_settling_time",
            )

        delay_waveform_mode = "arbitrary"
        with col_d3:
            delay_channel = st.radio(
                "Channel", ["CH1", "CH2", "Both"], horizontal=True, key="_delay_ch",
            )

        # Parse delay-specific fields
        delay_parse_errors = list(common_parse_errors)
        delay_parsed = dict(common_parsed)

        try:
            delay_parsed["pulse_width"] = parse_si(st.session_state._w_delay_pulse_width)
        except (ValueError, KeyError):
            delay_parse_errors.append(
                f"pulse_width: invalid value \"{st.session_state.get('_w_delay_pulse_width', '')}\""
            )
        try:
            delay_parsed["wait_time"] = parse_si(st.session_state._w_delay_wait_time)
        except (ValueError, KeyError):
            delay_parse_errors.append(
                f"wait_time: invalid value \"{st.session_state.get('_w_delay_wait_time', '')}\""
            )

        delay_start_val = st.session_state.get("_w_delay_start", 0)
        delay_stop_val = st.session_state.get("_w_delay_stop", 80)
        delay_step_val = st.session_state.get("_w_delay_step", 8)

        # Build delay sweep config
        if not delay_parse_errors:
            delay_config_built = DelaySweepConfig(
                visa_address=visa_address,
                v_on=v_on,
                v_off=v_off,
                frequency=delay_parsed["frequency"],
                trigger_delay=int(delay_start_val),
                resolution_n=int(resolution_n),
                pulse_width=delay_parsed["pulse_width"],
                delay_start=int(delay_start_val),
                delay_stop=int(delay_stop_val),
                delay_step=int(delay_step_val),
                wait_time=delay_parsed["wait_time"],
                waveform_mode=delay_waveform_mode,
                settling_time=delay_settling_time,
            )

        # Validation
        errors_delay = list(delay_parse_errors)
        if delay_config_built is not None:
            errors_delay.extend(delay_config_built.validate())

        if errors_delay:
            st.error("Configuration error:\n" + "\n".join(f"- {e}" for e in errors_delay))
        else:
            st.success("Parameters OK")
            if delay_config_built is not None:
                _show_arb_info(delay_config_built.frequency, [delay_config_built.pulse_width], resolution_n=resolution_n)

        # Run delay sweep
        if st.button("Start Delay Sweep", disabled=bool(errors_delay) or not visa_address,
                      type="primary", key="_btn_start_delay_sweep"):
            config = delay_config_built
            channels = _CHANNEL_MAP[delay_channel]
            logger.info("Delay sweep started (channels=%s)", channels)
            progress = st.progress(0, text="Connecting...")

            instrument = None
            try:
                instrument = PulseInstrument(config.visa_address)
                progress.progress(0, text="Setting up instrument...")

                for ch in channels:
                    instrument.setup_arbitrary(
                        config, [config.pulse_width], channel=ch,
                    )

                # Settling phase
                if config.settling_time > 0:
                    t0 = time.time()
                    while (elapsed := time.time() - t0) < config.settling_time:
                        pct = elapsed / config.settling_time
                        progress.progress(
                            pct,
                            text=f"Settling... {elapsed:.1f}s / {config.settling_time:.1f}s",
                        )
                        time.sleep(0.2)

                sweep_start = time.time()

                def on_delay_step(i: int, total: int) -> None:
                    pct = (i + 1) / total
                    elapsed = time.time() - sweep_start
                    rate = (i + 1) / elapsed if elapsed > 0 else 0
                    remaining = (total - i - 1) / rate if rate > 0 else 0
                    progress.progress(
                        pct,
                        text=(
                            f"Sweeping... {i + 1}/{total}"
                            f" ({elapsed:.1f}s elapsed, ~{remaining:.0f}s remaining)"
                        ),
                    )

                run_delay_sweep(config, instrument, callback=on_delay_step, channels=channels)

                for ch in channels:
                    instrument.teardown(channel=ch)

                progress.progress(1.0, text="Done!")
                logger.info("Delay sweep completed")

            except Exception as exc:
                st.error(f"Error: {exc}")
                logger.exception("Error during delay sweep")
            finally:
                if instrument is not None:
                    instrument.close()


    # ================================================================== #
    #  Sidebar: unified TOML save (after all tabs are built)
    # ================================================================== #

def _build_toml_data() -> dict:
    """Build unified TOML dict from current widget state."""
    freq = common_parsed.get("frequency", 10_000_000.0)
    data: dict = {
        "save": {
            "save_dir": st.session_state.get("_w_save_dir", "configs"),
            "filename_format": st.session_state.get("_w_filename_format", ""),
        },
        "connection": {
            "visa_address": visa_address,
        },
        "common": {
            "v_on": v_on,
            "v_off": v_off,
            "frequency": freq,
            "period": 1.0 / freq if freq > 0 else 0.0,
            "trigger_delay": int(trigger_delay),
            "resolution_n": int(resolution_n),
        },
        "simple_pulse": {
            "pulse_width": pulse_width_val if pulse_width_val is not None else 1e-8,
            **({"saved_records": [
                [parse_si(r["pulse_width"]), float(r["trigger_delay"])]
                for r in st.session_state.get("saved_pulse_records", [])
            ]} if st.session_state.get("saved_pulse_records") else {}),
        },
    }

    # Width Sweep section
    ws_data: dict = {}
    for name in ("width_start", "width_stop", "width_step", "wait_time"):
        if name in sweep_parsed:
            ws_data[name] = sweep_parsed[name]
    ws_data["settling_time"] = float(st.session_state.get("_w_settling_time", 0.0))
    _tds = int(st.session_state.get("_w_trigger_delay_stop", 0))
    if _tds != int(trigger_delay):
        ws_data["trigger_delay_stop"] = _tds
    _de = float(st.session_state.get("_w_delay_exponent", 1.0))
    if _de != 1.0:
        ws_data["delay_exponent"] = _de
    # Delay mode + table
    _dm = st.session_state.get("_w_delay_mode_radio", "Exponent")
    _dm_val = "exponent" if _dm == "Exponent" else "table"
    if _dm_val != "exponent":
        ws_data["delay_mode"] = _dm_val
    if _dm_val == "table":
        _records = st.session_state.get("saved_pulse_records", [])
        if _records:
            ws_data["delay_table"] = [
                [parse_si(r["pulse_width"]), float(r["trigger_delay"])]
                for r in _records
            ]
    # Step zones
    if _step_zones:
        ws_data["step_zones"] = [list(row) for row in _step_zones]
    data["width_sweep"] = ws_data

    # Delay Sweep section
    ds_data: dict = {}
    pw = delay_parsed.get("pulse_width")
    if pw is not None:
        ds_data["pulse_width"] = pw
    wt = delay_parsed.get("wait_time")
    if wt is not None:
        ds_data["wait_time"] = wt
    ds_data["delay_start"] = int(st.session_state.get("_w_delay_start", 0))
    ds_data["delay_stop"] = int(st.session_state.get("_w_delay_stop", 80))
    ds_data["delay_step"] = int(st.session_state.get("_w_delay_step", 8))
    ds_data["settling_time"] = float(st.session_state.get("_w_delay_settling_time", 0.0))
    data["delay_sweep"] = ds_data

    # Pump-Probe section
    pp_data: dict = {}
    try:
        pp_data["pulse_width"] = parse_si(st.session_state.get("_w_pp_pulse_width", "10n"))
    except ValueError:
        pp_data["pulse_width"] = 1e-8
    try:
        pp_data["pulse_interval"] = parse_si(st.session_state.get("_w_pp_pulse_interval", "20n"))
    except ValueError:
        pp_data["pulse_interval"] = 2e-8
    if st.session_state.get("saved_pp_records"):
        pp_data["saved_records"] = [
            [parse_si(r["pulse_interval"]), float(r["trigger_delay"])]
            for r in st.session_state.get("saved_pp_records", [])
        ]
    data["pump_probe"] = pp_data

    # Interval Sweep section
    isw_data: dict = {}
    try:
        isw_data["pulse_width"] = parse_si(st.session_state.get("_w_interval_pulse_width", "10n"))
    except ValueError:
        isw_data["pulse_width"] = 1e-8
    for name, key in [
        ("interval_start", "_w_interval_start"),
        ("interval_stop", "_w_interval_stop"),
        ("interval_step", "_w_interval_step"),
        ("wait_time", "_w_interval_wait_time"),
    ]:
        try:
            isw_data[name] = parse_si(st.session_state.get(key, ""))
        except ValueError:
            pass
    isw_data["settling_time"] = float(st.session_state.get("_w_interval_settling_time", 0.0))
    _is_tds = int(st.session_state.get("_w_interval_trigger_delay_stop", 0))
    if _is_tds != int(trigger_delay):
        isw_data["trigger_delay_stop"] = _is_tds
    _is_de = float(st.session_state.get("_w_interval_delay_exponent", 1.0))
    if _is_de != 1.0:
        isw_data["delay_exponent"] = _is_de
    _is_dm = st.session_state.get("_w_interval_delay_mode_radio", "Exponent")
    _is_dm_val = "exponent" if _is_dm == "Exponent" else "table"
    if _is_dm_val != "exponent":
        isw_data["delay_mode"] = _is_dm_val
    if _is_dm_val == "table":
        _pp_recs = st.session_state.get("saved_pp_records", [])
        if _pp_recs:
            isw_data["delay_table"] = [
                [parse_si(r["pulse_interval"]), float(r["trigger_delay"])]
                for r in _pp_recs
            ]
    if _is_step_zones:
        isw_data["step_zones"] = [list(row) for row in _is_step_zones]
    data["interval_sweep"] = isw_data

    # Integration (Auto Sweep)
    data["integration"] = {
        "dmm_visa_address": st.session_state.get("_w_ig_dmm_address", DEFAULT_34401A_ADDRESS),
        "trigger_start_voltage": float(st.session_state.get("_w_ig_trigger_start", -9.8)),
        "trigger_end_voltage": float(st.session_state.get("_w_ig_trigger_end", -9.2)),
        "sweep_start_voltage": float(st.session_state.get("_w_ig_sweep_start", -9.0)),
        "poll_interval": float(st.session_state.get("_w_ig_poll_interval", 1.0)),
        "num_cycles": int(st.session_state.get("_w_ig_num_cycles", 0)),
    }

    return data


# Delay resolution display — fill placeholder after all tabs
_delay_res_text = ""
if "frequency" in common_parsed:
    _freq = common_parsed["frequency"]
    _res_n = int(resolution_n)
    # Pick the best available widths for calculation
    _arb_widths: list[float] | None = None
    if sweep_config_built is not None:
        _arb_widths = _generate_widths(
            sweep_config_built.width_start,
            sweep_config_built.width_stop,
            sweep_config_built.width_step,
            step_zones=sweep_config_built.step_zones,
        )
    elif delay_config_built is not None:
        _arb_widths = [delay_config_built.pulse_width]
    elif pulse_config is not None:
        _arb_widths = [pulse_config.pulse_width]

    _sr_over = False
    if _arb_widths is not None:
        try:
            _sr, _pts = _calc_arb_params(_freq, _arb_widths, resolution_n=_res_n)
            _tpp = 1.0 / _freq / _pts
            _delay_res_text = f"{format_si(8 * _tpp)}s"
            _sr_over = _sr > MAX_SAMPLE_RATE
        except Exception:
            _delay_res_text = "error"

with _delay_res_placeholder.container():
    st.text_input("Delay Resolution", value=_delay_res_text or "N/A", disabled=True)
    if _sr_over:
        st.warning("Sample rate exceeds 4.2 GSa/s. Reduce ×n.")


# Save button — rendered in sidebar placeholder (after subheader, before expander)
_all_parse_errors = common_parse_errors + [
    e for e in (pulse_parse_errors or []) if e not in common_parse_errors
] + [
    e for e in (sweep_parse_errors or []) if e not in common_parse_errors
] + [
    e for e in (delay_parse_errors or []) if e not in common_parse_errors
]
_save_dir = st.session_state.get("_w_save_dir", "").strip()
_fn_fmt = st.session_state.get("_w_filename_format", "").strip()

with _save_btn_placeholder.container():
    if st.button(
        "Save TOML", type="primary", use_container_width=True,
        disabled=bool(_all_parse_errors) or not _save_dir or not _fn_fmt,
    ):
        try:
            toml_data = _build_toml_data()
            path = next_save_path(_save_dir, _fn_fmt)
            save_unified_toml(path, toml_data)
            st.success(f"Saved: {path.resolve()}")
            logger.info("Config saved: %s", path)
        except Exception as exc:
            st.error(f"Save failed: {exc}")
            logger.exception("Config save error")
