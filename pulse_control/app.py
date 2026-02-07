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
#  セッション初期化
# ================================================================== #
if "config" not in st.session_state:
    st.session_state.config = SweepConfig()

cfg: SweepConfig = st.session_state.config

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
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp.flush()
            st.session_state.config = SweepConfig.from_toml(tmp.name)
            st.rerun()

# ================================================================== #
#  メイン: パラメータ入力
# ================================================================== #
col1, col2 = st.columns(2)

with col1:
    st.subheader("パルス形状")
    v_on = st.number_input("V_on [V]", value=cfg.v_on, format="%.4f")
    v_off = st.number_input("V_off [V]", value=cfg.v_off, format="%.4f")

    st.subheader("掃引パラメータ")
    width_start = st.number_input(
        "width_start [s]", value=cfg.width_start, format="%.6f", step=0.001
    )
    width_stop = st.number_input(
        "width_stop [s]", value=cfg.width_stop, format="%.6f", step=0.001
    )
    width_step = st.number_input(
        "width_step [s]", value=cfg.width_step, format="%.6f", step=0.001
    )

with col2:
    st.subheader("信号生成")
    freq_mode = st.radio(
        "周波数の入力方法", ["周波数 [Hz]", "周期 [s]"], horizontal=True
    )
    if freq_mode == "周波数 [Hz]":
        frequency = st.number_input(
            "frequency [Hz]", value=cfg.frequency, format="%.1f", step=100.0
        )
    else:
        period_val = st.number_input(
            "period [s]", value=cfg.period, format="%.6f",
            step=0.0001, min_value=1e-9,
        )
        frequency = 1.0 / period_val

    st.subheader("トリガー")
    trigger_delay = st.number_input(
        "trigger_delay [points]（8 の倍数）",
        value=cfg.trigger_delay, min_value=0, step=8,
    )

    st.subheader("掃引制御")
    wait_time = st.number_input(
        "wait_time [s]", value=cfg.wait_time, format="%.2f", step=0.1
    )


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
