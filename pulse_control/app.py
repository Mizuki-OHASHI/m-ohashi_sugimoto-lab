"""パルス幅掃引 Streamlit UI.

Usage:
    streamlit run pulse_control/app.py
"""

from __future__ import annotations

import tempfile
from logging import getLogger

import matplotlib.pyplot as plt
import streamlit as st

from config import DEFAULT_VISA_ADDRESS, SweepConfig
from core import PulseInstrument, run_sweep, save_results
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
    st.caption("Keysight M96 PXI SMU")

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
    center_delay = st.number_input(
        "center_delay [s]", value=cfg.center_delay, format="%.6f", step=0.001
    )
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
    st.subheader("測定パラメータ")
    trigger_count = st.number_input(
        "trigger_count", value=cfg.trigger_count, min_value=1, step=1
    )
    trigger_time = st.number_input(
        "trigger_time [s]", value=cfg.trigger_time, format="%.6f", step=0.001
    )
    aperture_time = st.number_input(
        "aperture_time [s]", value=cfg.aperture_time, format="%.6f", step=0.0001
    )
    sampling_points = st.number_input(
        "sampling_points", value=cfg.sampling_points, min_value=1, step=1
    )
    compliance_current = st.number_input(
        "compliance_current [A]",
        value=cfg.compliance_current,
        format="%.4f",
        step=0.01,
    )

    st.subheader("出力")
    output_dir = st.text_input("output_dir", value=cfg.output_dir)


# ------------------------------------------------------------------ #
#  UI の値から SweepConfig を構築するヘルパー
# ------------------------------------------------------------------ #
def _build_config_from_ui() -> SweepConfig:
    return SweepConfig(
        visa_address=visa_address,
        v_on=v_on,
        v_off=v_off,
        center_delay=center_delay,
        width_start=width_start,
        width_stop=width_stop,
        width_step=width_step,
        trigger_count=int(trigger_count),
        trigger_time=trigger_time,
        aperture_time=aperture_time,
        sampling_points=int(sampling_points),
        compliance_current=compliance_current,
        output_dir=output_dir,
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
    st.error("設定エラー:")
    for e in errors:
        st.write(f"- {e}")
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

        def on_step(i: int, total: int, _result: dict) -> None:
            pct = (i + 1) / total
            progress.progress(pct, text=f"測定中... {i + 1}/{total}")

        results = run_sweep(config, instrument, callback=on_step)
        instrument.teardown()
        instrument.close()

        progress.progress(1.0, text="保存中...")
        save_results(results, config, config.output_dir)
        progress.progress(1.0, text="完了!")
        logger.info("掃引完了: %d 件の結果を %s に保存", len(results), config.output_dir)

        st.session_state.results = results

    except Exception as exc:
        st.error(f"エラー: {exc}")
        logger.exception("掃引中にエラー発生")

# ================================================================== #
#  結果プロット
# ================================================================== #
if "results" in st.session_state:
    st.divider()
    st.subheader("結果")

    results = st.session_state.results

    for result in results:
        w = result["pulse_width"]
        fig, ax1 = plt.subplots(figsize=(8, 3))
        ax1.set_title(f"Pulse width = {w * 1e6:.1f} us")
        ax1.set_xlabel("Time [s]")
        ax1.set_ylabel("Voltage [V]", color="tab:blue")
        ax1.plot(result["timestamps"], result["voltage"], color="tab:blue", label="V")
        ax1.tick_params(axis="y", labelcolor="tab:blue")

        ax2 = ax1.twinx()
        ax2.set_ylabel("Current [A]", color="tab:red")
        ax2.plot(result["timestamps"], result["current"], color="tab:red", label="I")
        ax2.tick_params(axis="y", labelcolor="tab:red")

        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
