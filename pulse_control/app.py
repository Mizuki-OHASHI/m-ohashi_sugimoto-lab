"""パルス幅掃引 Streamlit UI（Agilent 81180A AWG 用）.

Usage:
    streamlit run pulse_control/app.py
"""

from __future__ import annotations

import tempfile
from logging import getLogger

import streamlit as st

from config import DEFAULT_VISA_ADDRESS, SweepConfig
from core import PulseInstrument, run_sweep
from log_setup import setup_logging

setup_logging()
logger = getLogger(__name__)

st.set_page_config(page_title="Pulse Width Sweep", layout="wide")

# ================================================================== #
#  時間単位
# ================================================================== #
UNIT_FACTORS: dict[str, float] = {
    "s": 1.0,
    "ms": 1e-3,
    "μs": 1e-6,
    "ns": 1e-9,
}

# ================================================================== #
#  セッション初期化
# ================================================================== #
if "config" not in st.session_state:
    st.session_state.config = SweepConfig()
if "_frequency" not in st.session_state:
    st.session_state._frequency = st.session_state.config.frequency
if "_prev_time_unit" not in st.session_state:
    st.session_state._prev_time_unit = "s"

cfg: SweepConfig = st.session_state.config


# ================================================================== #
#  コールバック: 時間単位・周波数/周期の相互同期
# ================================================================== #
def _on_unit_change() -> None:
    """時間単位変更 → 全時間フィールドの表示値を新しい単位に変換."""
    new_unit = st.session_state._w_time_unit
    old_unit = st.session_state._prev_time_unit
    ratio = UNIT_FACTORS[old_unit] / UNIT_FACTORS[new_unit]
    for key in ("_w_width_start", "_w_width_stop", "_w_width_step", "_w_wait_time"):
        if key in st.session_state:
            st.session_state[key] *= ratio
    freq = st.session_state._frequency
    if freq > 0 and "_w_period" in st.session_state:
        st.session_state._w_period = (1.0 / freq) / UNIT_FACTORS[new_unit]
    st.session_state._prev_time_unit = new_unit


def _on_freq_change() -> None:
    """周波数入力 → 周期を再計算."""
    freq = st.session_state._w_freq
    st.session_state._frequency = freq
    f = UNIT_FACTORS[st.session_state.get("_w_time_unit", "s")]
    if freq > 0 and "_w_period" in st.session_state:
        st.session_state._w_period = (1.0 / freq) / f


def _on_period_change() -> None:
    """周期入力 → 周波数を再計算."""
    f = UNIT_FACTORS[st.session_state.get("_w_time_unit", "s")]
    p = st.session_state._w_period
    if p > 0:
        freq = 1.0 / (p * f)
        st.session_state._frequency = freq
        if "_w_freq" in st.session_state:
            st.session_state._w_freq = freq


def _load_config_to_widgets(new_cfg: SweepConfig) -> None:
    """SweepConfig の値をウィジェットの session state に反映する."""
    # TOML に時間単位が含まれていればそれを使い、なければ現在の単位を維持
    unit = new_cfg.time_unit if new_cfg.time_unit in UNIT_FACTORS else "s"
    f = UNIT_FACTORS[unit]
    st.session_state.config = new_cfg
    st.session_state._frequency = new_cfg.frequency
    st.session_state._w_time_unit = unit
    st.session_state._prev_time_unit = unit
    st.session_state._w_width_start = new_cfg.width_start / f
    st.session_state._w_width_stop = new_cfg.width_stop / f
    st.session_state._w_width_step = new_cfg.width_step / f
    st.session_state._w_wait_time = new_cfg.wait_time / f
    st.session_state._w_freq = new_cfg.frequency
    if new_cfg.frequency > 0:
        st.session_state._w_period = (1.0 / new_cfg.frequency) / f


# ================================================================== #
#  サイドバー: タイトル + 接続 + TOML インポート/エクスポート
# ================================================================== #
with st.sidebar:
    st.header("Pulse Width Sweep")
    st.caption("Agilent 81180A AWG")

    st.divider()
    st.subheader("接続")
    visa_address = st.text_input("VISA アドレス", value=cfg.visa_address)
    if st.button("デフォルトに戻す"):
        cfg.visa_address = DEFAULT_VISA_ADDRESS
        st.rerun()

    if st.button("接続チェック"):
        with st.spinner("接続中..."):
            try:
                idn = PulseInstrument.check_connection(visa_address)
                st.success(f"OK: {idn}")
                logger.info("接続チェック成功: %s", idn)
            except Exception as exc:
                st.error(f"接続失敗: {exc}")
                logger.error("接続チェック失敗: %s", exc)

    st.divider()
    st.subheader("TOML 設定")

    # インポート
    uploaded = st.file_uploader("TOML インポート", type=["toml"])
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
#  時間単位セレクタ
# ================================================================== #
time_unit = st.radio(
    "時間の表示単位", list(UNIT_FACTORS.keys()),
    horizontal=True, index=0,
    key="_w_time_unit", on_change=_on_unit_change,
)
factor = UNIT_FACTORS[time_unit]

# ================================================================== #
#  メイン: パラメータ入力
# ================================================================== #
col1, col2 = st.columns(2)

with col1:
    st.subheader("パルス形状")
    v_on = st.number_input("V_on [V]", value=cfg.v_on, format="%.4f")
    v_off = st.number_input("V_off [V]", value=cfg.v_off, format="%.4f")

    st.subheader("掃引パラメータ")
    st.number_input(
        f"width_start [{time_unit}]",
        value=cfg.width_start / factor, format="%.4f", step=1.0,
        key="_w_width_start",
    )
    st.number_input(
        f"width_stop [{time_unit}]",
        value=cfg.width_stop / factor, format="%.4f", step=1.0,
        key="_w_width_stop",
    )
    st.number_input(
        f"width_step [{time_unit}]",
        value=cfg.width_step / factor, format="%.4f", step=1.0,
        key="_w_width_step",
    )
    width_start = st.session_state._w_width_start * factor
    width_stop = st.session_state._w_width_stop * factor
    width_step = st.session_state._w_width_step * factor

with col2:
    st.subheader("信号生成")
    freq_col, period_col = st.columns(2)
    with freq_col:
        st.number_input(
            "frequency [Hz]",
            value=st.session_state._frequency,
            format="%.4f", step=100.0,
            key="_w_freq",
            on_change=_on_freq_change,
        )
    with period_col:
        st.number_input(
            f"period [{time_unit}]",
            value=(1.0 / st.session_state._frequency) / factor,
            format="%.4f", step=1.0,
            min_value=1e-9 / factor,
            key="_w_period",
            on_change=_on_period_change,
        )
    frequency = st.session_state._frequency

    st.subheader("トリガー")
    trigger_delay = st.number_input(
        "trigger_delay [points]（8 の倍数）",
        value=cfg.trigger_delay, min_value=0, step=8,
    )

    st.subheader("掃引制御")
    st.number_input(
        f"wait_time [{time_unit}]",
        value=cfg.wait_time / factor, format="%.4f", step=1.0,
        key="_w_wait_time",
    )
    wait_time = st.session_state._w_wait_time * factor


# ------------------------------------------------------------------ #
#  UI の値から SweepConfig を構築するヘルパー
# ------------------------------------------------------------------ #
def _build_config_from_ui() -> SweepConfig:
    return SweepConfig(
        visa_address=visa_address,
        v_on=v_on,
        v_off=v_off,
        width_start=width_start,
        width_stop=width_stop,
        width_step=width_step,
        frequency=frequency,
        trigger_delay=int(trigger_delay),
        wait_time=wait_time,
        time_unit=time_unit,
    )


# ================================================================== #
#  TOML エクスポート
# ================================================================== #
with st.sidebar:
    export_config = _build_config_from_ui()
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as tmp:
        export_config.to_toml(tmp.name)
        with open(tmp.name) as f:
            toml_str = f.read()
    st.download_button(
        "TOML エクスポート",
        data=toml_str,
        file_name="sweep_config.toml",
        mime="text/plain",
    )

# ================================================================== #
#  バリデーション
# ================================================================== #
current_config = _build_config_from_ui()
errors = current_config.validate()

st.divider()
if errors:
    msg = "設定エラー:\n" + "\n".join(f"- {e}" for e in errors)
    st.error(msg)
else:
    st.success("パラメータ OK")

# ================================================================== #
#  実行
# ================================================================== #
st.divider()
if st.button("掃引開始", disabled=bool(errors) or not visa_address):
    config = _build_config_from_ui()
    logger.info("掃引開始")
    progress = st.progress(0, text="接続中...")

    try:
        instrument = PulseInstrument(config.visa_address)
        progress.progress(0, text="装置セットアップ中...")
        instrument.setup(config)

        def on_step(i: int, total: int) -> None:
            pct = (i + 1) / total
            progress.progress(pct, text=f"掃引中... {i + 1}/{total}")

        run_sweep(config, instrument, callback=on_step)
        instrument.teardown()
        instrument.close()

        progress.progress(1.0, text="完了!")
        logger.info("掃引完了")

    except Exception as exc:
        st.error(f"エラー: {exc}")
        logger.exception("掃引中にエラー発生")
