"""Pulse Control Streamlit UI (Agilent 81180A AWG).

Usage:
    streamlit run pulse_control/app.py
"""

from __future__ import annotations

import re
import tempfile
import time
from logging import getLogger
from pathlib import Path

import streamlit as st

from config import DEFAULT_VISA_ADDRESS, DelaySweepConfig, PulseConfig, SweepConfig
from core import PulseInstrument, _generate_widths, run_delay_sweep, run_sweep
from log_setup import setup_logging

DEFAULT_CONFIG = Path("sweep_config.toml")

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


_CHANNEL_MAP = {"CH1": [1], "CH2": [2], "Both": [1, 2]}


# ================================================================== #
#  Session initialisation
# ================================================================== #
if "sweep_config" not in st.session_state:
    st.session_state.sweep_config = SweepConfig.from_toml(DEFAULT_CONFIG)

sweep_cfg: SweepConfig = st.session_state.sweep_config


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


def _load_config_to_widgets(new_cfg: SweepConfig) -> None:
    """Push SweepConfig values into widget session state."""
    st.session_state.sweep_config = new_cfg
    # Common fields
    st.session_state._w_v_on = new_cfg.v_on
    st.session_state._w_v_off = new_cfg.v_off
    st.session_state._w_freq = format_si(new_cfg.frequency)
    if new_cfg.frequency > 0:
        st.session_state._w_period = format_si(1.0 / new_cfg.frequency)
    st.session_state._w_trigger_delay = new_cfg.trigger_delay
    # Sweep-specific fields
    st.session_state._w_width_start = format_si(new_cfg.width_start)
    st.session_state._w_width_stop = format_si(new_cfg.width_stop)
    st.session_state._w_width_step = format_si(new_cfg.width_step)
    st.session_state._w_wait_time = format_si(new_cfg.wait_time)
    # Pulse width defaults to width_start
    st.session_state._w_pulse_width = format_si(new_cfg.width_start)


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
        if config.waveform_mode == "arbitrary":
            inst.setup_arbitrary(config, [config.pulse_width], channel=channel)
        else:
            inst.setup(config, config.pulse_width, channel=channel)
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
    other = 2 if channel == 1 else 1
    if not st.session_state.get(f"ch{other}_running"):
        if st.session_state.get("live_connection"):
            _close_live_connection()
            st.session_state._w_live_connection = False


# ================================================================== #
#  Sidebar: title + connection + DC 0V + TOML import
# ================================================================== #
with st.sidebar:
    st.header("Pulse Control")
    st.caption("Agilent 81180A AWG")

    # st.divider()
    # st.markdown("**Connection**")
    st.subheader("Connection")
    visa_address = st.text_input("VISA Address", value=sweep_cfg.visa_address)

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("Reset", use_container_width=True):
            sweep_cfg.visa_address = DEFAULT_VISA_ADDRESS
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
    # st.divider()
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

    # st.divider()
    # st.markdown("**TOML Config**")
    st.subheader("TOML Config")

    uploaded = st.file_uploader("Import TOML", type=["toml"])
    if uploaded is not None:
        upload_id = f"{uploaded.name}_{uploaded.size}"
        if st.session_state.get("_last_upload_id") != upload_id:
            st.session_state._last_upload_id = upload_id
            with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as tmp:
                tmp.write(uploaded.read())
                tmp.flush()
                try:
                    _load_config_to_widgets(SweepConfig.from_toml(tmp.name))
                    st.rerun()
                except Exception as exc:
                    st.error(f"Import failed: {exc}")


# ================================================================== #
#  Main: Common parameters (always visible)
# ================================================================== #
col_volt, col_timing = st.columns(2)

with col_volt:
    v_on = st.number_input("V_on [V]", value=sweep_cfg.v_on, format="%.4f", key="_w_v_on")
    v_off = st.number_input("V_off [V]", value=sweep_cfg.v_off, format="%.4f", key="_w_v_off")

with col_timing:
    freq_col, period_col = st.columns(2)
    with freq_col:
        st.text_input(
            "Frequency [Hz]",
            value=format_si(sweep_cfg.frequency),
            key="_w_freq",
            on_change=_on_freq_change,
        )
    with period_col:
        st.text_input(
            "Period [s]",
            value=format_si(1.0 / sweep_cfg.frequency),
            key="_w_period",
            on_change=_on_period_change,
        )
    trigger_delay = st.number_input(
        "Trigger Delay [points] (multiple of 8)",
        value=sweep_cfg.trigger_delay, min_value=0, step=8,
        key="_w_trigger_delay",
    )

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

tab_pulse, tab_sweep, tab_delay = st.tabs(["Simple Pulse", "Width Sweep", "Delay Sweep"])

# ================================================================== #
#  Simple Pulse tab
# ================================================================== #
with tab_pulse:
    _p_col1, _p_col2 = st.columns(2)
    with _p_col1:
        st.text_input(
            "Pulse Width [s]",
            value=format_si(sweep_cfg.width_start),
            key="_w_pulse_width",
        )
    with _p_col2:
        _PULSE_WAVEFORM_LABELS = {"square": "Square", "arbitrary": "Arbitrary"}
        pulse_waveform_mode = st.radio(
            "Waveform Mode",
            ["square", "arbitrary"],
            format_func=lambda x: _PULSE_WAVEFORM_LABELS[x],
            horizontal=True,
            key="_pulse_waveform_mode",
        )

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

    # Per-channel Start/Stop buttons
    ch1_running = st.session_state.get("ch1_running", False)
    ch2_running = st.session_state.get("ch2_running", False)
    can_start = not bool(errors_pulse) and bool(visa_address)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        start_ch1 = st.button(
            "Start CH1", disabled=not can_start or ch1_running,
            type="primary", use_container_width=True,
        )
    with c2:
        stop_ch1 = st.button(
            "Stop CH1", disabled=not ch1_running,
            use_container_width=True,
        )
    with c3:
        start_ch2 = st.button(
            "Start CH2", disabled=not can_start or ch2_running,
            type="primary", use_container_width=True,
        )
    with c4:
        stop_ch2 = st.button(
            "Stop CH2", disabled=not ch2_running,
            use_container_width=True,
        )

    # Start CH1
    if start_ch1 and pulse_config is not None:
        try:
            _pulse_start(pulse_config, channel=1)
            st.session_state.ch1_running = True
            logger.info("Pulse CH1 started via UI (%s)", pulse_config.waveform_mode)
            st.rerun()
        except Exception as exc:
            st.error(f"Error: {exc}")
            logger.exception("Error starting pulse CH1")

    # Start CH2
    if start_ch2 and pulse_config is not None:
        try:
            _pulse_start(pulse_config, channel=2)
            st.session_state.ch2_running = True
            logger.info("Pulse CH2 started via UI (%s)", pulse_config.waveform_mode)
            st.rerun()
        except Exception as exc:
            st.error(f"Error: {exc}")
            logger.exception("Error starting pulse CH2")

    # Stop CH1
    if stop_ch1 and ch1_running:
        try:
            _pulse_stop(visa_address, channel=1)
        except Exception as exc:
            logger.error("Teardown CH1 error: %s", exc)
        logger.info("Pulse CH1 stopped via UI")
        st.rerun()

    # Stop CH2
    if stop_ch2 and ch2_running:
        try:
            _pulse_stop(visa_address, channel=2)
        except Exception as exc:
            logger.error("Teardown CH2 error: %s", exc)
        logger.info("Pulse CH2 stopped via UI")
        st.rerun()

    # Live Connection toggle
    st.divider()
    st.toggle(
        "Live Connection",
        value=st.session_state.get("live_connection", False),
        key="_w_live_connection",
        help="Keep connection open for instant Trigger Delay changes. "
             "Front panel will be locked in REMOTE mode while active.",
    )

    # Live connection state management
    prev_live = st.session_state.get("live_connection", False)
    curr_live = st.session_state.get("_w_live_connection", False)

    if curr_live and not prev_live:
        # Toggle turned ON: open connection
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
        except Exception as exc:
            st.error(f"Live connection failed: {exc}")
            st.session_state.live_connection = False
            st.session_state._w_live_connection = False
            logger.exception("Live connection error")

    elif not curr_live and prev_live:
        # Toggle turned OFF: close connection
        _close_live_connection()

    elif curr_live and prev_live:
        # Toggle stays ON: check for trigger delay changes
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
                    st.session_state._w_live_connection = False

    st.session_state.live_connection = curr_live

    # Status
    if st.session_state.get("live_connection"):
        st.warning("Live Connection: ON (front panel locked in REMOTE mode)")
    if ch1_running:
        st.info("CH1: Pulse output is ON.")
    if ch2_running:
        st.info("CH2: Pulse output is ON.")


# ================================================================== #
#  Width Sweep tab
# ================================================================== #
with tab_sweep:
    col_range, col_timing, col_opts = st.columns([2, 2, 1])

    with col_range:
        st.text_input(
            "Width Start [s]",
            value=format_si(sweep_cfg.width_start),
            key="_w_width_start",
        )
        st.text_input(
            "Width Stop [s]",
            value=format_si(sweep_cfg.width_stop),
            key="_w_width_stop",
        )
        st.text_input(
            "Width Step [s]",
            value=format_si(sweep_cfg.width_step),
            key="_w_width_step",
        )

    with col_timing:
        st.text_input(
            "Wait Time [s]",
            value=format_si(sweep_cfg.wait_time),
            key="_w_wait_time",
        )
        sweep_settling_time = st.number_input(
            "Settling Time [s]",
            value=0.0, min_value=0.0, step=1.0, format="%.1f",
            help="Wait time before sweep starts (for DUT to reach steady state)",
            key="_w_settling_time",
        )
        sweep_trigger_delay_stop = st.number_input(
            "Trigger Delay Stop [points] (×8)",
            value=int(trigger_delay), min_value=0, step=8,
            help="End value for trigger delay sweep. "
                 "Set equal to Trigger Delay for fixed delay.",
            key="_w_trigger_delay_stop",
        )
        st.info("Pulse center is fixed at the middle of the period during sweep.")

    with col_opts:
        _WAVEFORM_LABELS = {"square": "Square", "arbitrary": "Arbitrary"}
        waveform_mode = st.radio(
            "Waveform Mode",
            ["square", "arbitrary"],
            format_func=lambda x: _WAVEFORM_LABELS[x],
            horizontal=True,
        )
        sweep_channel = st.radio(
            "Channel", ["CH1", "CH2", "Both"], horizontal=True, key="_sweep_ch",
        )

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

    # Build sweep config
    if not sweep_parse_errors:
        _delay_stop_val = int(sweep_trigger_delay_stop)
        sweep_config_built = SweepConfig(
            visa_address=visa_address,
            v_on=v_on,
            v_off=v_off,
            width_start=sweep_parsed["width_start"],
            width_stop=sweep_parsed["width_stop"],
            width_step=sweep_parsed["width_step"],
            frequency=sweep_parsed["frequency"],
            trigger_delay=int(trigger_delay),
            wait_time=sweep_parsed["wait_time"],
            waveform_mode=waveform_mode,
            settling_time=sweep_settling_time,
            trigger_delay_stop=_delay_stop_val if _delay_stop_val != int(trigger_delay) else None,
        )

    # Validation
    errors_sweep = list(sweep_parse_errors)
    if sweep_config_built is not None:
        errors_sweep.extend(sweep_config_built.validate())

    if errors_sweep:
        st.error("Configuration error:\n" + "\n".join(f"- {e}" for e in errors_sweep))
    else:
        st.success("Parameters OK")

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

            for ch in channels:
                if config.waveform_mode == "arbitrary":
                    widths = _generate_widths(
                        config.width_start, config.width_stop, config.width_step,
                    )
                    instrument.setup_arbitrary(config, widths, channel=ch)
                else:
                    instrument.setup(config, config.width_start, channel=ch)

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


# ================================================================== #
#  Delay Sweep tab
# ================================================================== #
with tab_delay:
    col_d1, col_d2, col_d3 = st.columns([2, 2, 1])

    with col_d1:
        st.text_input(
            "Pulse Width [s]",
            value=format_si(sweep_cfg.width_start),
            key="_w_delay_pulse_width",
        )
        st.number_input(
            "Delay Start [points] (×8)",
            value=0, min_value=0, step=8,
            key="_w_delay_start",
        )
        st.number_input(
            "Delay Stop [points] (×8)",
            value=80, min_value=0, step=8,
            key="_w_delay_stop",
        )

    with col_d2:
        st.number_input(
            "Delay Step [points] (×8)",
            value=8, min_value=8, step=8,
            key="_w_delay_step",
        )
        st.text_input(
            "Wait Time [s]",
            value=format_si(sweep_cfg.wait_time),
            key="_w_delay_wait_time",
        )
        delay_settling_time = st.number_input(
            "Settling Time [s]",
            value=0.0, min_value=0.0, step=1.0, format="%.1f",
            help="Wait time before sweep starts (for DUT to reach steady state)",
            key="_w_delay_settling_time",
        )

    with col_d3:
        _DELAY_WAVEFORM_LABELS = {"square": "Square", "arbitrary": "Arbitrary"}
        delay_waveform_mode = st.radio(
            "Waveform Mode",
            ["square", "arbitrary"],
            format_func=lambda x: _DELAY_WAVEFORM_LABELS[x],
            horizontal=True,
            key="_delay_waveform_mode",
        )
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
                if config.waveform_mode == "arbitrary":
                    instrument.setup_arbitrary(
                        config, [config.pulse_width], channel=ch,
                    )
                else:
                    instrument.setup(config, config.pulse_width, channel=ch)

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
#  Sidebar: TOML export (after configs are built)
# ================================================================== #
with st.sidebar:
    st.text("Export TOML")
    _exp_cols = st.columns(3)

    with _exp_cols[0]:
        if pulse_config is not None:
            with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as tmp:
                pulse_config.to_toml(tmp.name)
                with open(tmp.name) as f:
                    toml_str = f.read()
            st.download_button(
                "Pulse",
                data=toml_str,
                file_name="pulse_config.toml",
                mime="text/plain",
                key="_export_pulse",
            )

    with _exp_cols[1]:
        if sweep_config_built is not None:
            with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as tmp:
                sweep_config_built.to_toml(tmp.name)
                with open(tmp.name) as f:
                    toml_str = f.read()
            st.download_button(
                "Width",
                data=toml_str,
                file_name="sweep_config.toml",
                mime="text/plain",
                key="_export_sweep",
            )

    with _exp_cols[2]:
        if delay_config_built is not None:
            with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as tmp:
                delay_config_built.to_toml(tmp.name)
                with open(tmp.name) as f:
                    toml_str = f.read()
            st.download_button(
                "Delay",
                data=toml_str,
                file_name="delay_sweep_config.toml",
                mime="text/plain",
                key="_export_delay",
            )
