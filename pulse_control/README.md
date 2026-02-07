# Pulse Width Sweep — Agilent 81180A AWG

パルス幅（Duty Cycle）を掃引して Agilent 81180A Arbitrary Waveform Generator を制御するツール。
Square モードで周波数を固定し、Duty 可変でパルス幅を制御する。

## ドキュメント

- [81180A Arbitrary Waveform Generator User's Guide (Keysight)](https://www.keysight.com/us/en/assets/9018-03346/user-manuals/9018-03346.pdf)

## 動作環境

- **Windows** / **Linux** / **Mac**
- Python 3.10+
- Agilent 81180A AWG + TCP/IP 接続

> VISA バックエンドに `pyvisa-py` を使用するため、Keysight IO Libraries Suite のインストールは不要です。

## セットアップ

### Windows

```powershell
cd pulse_control
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Linux / Mac

```bash
cd pulse_control
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 使い方

### CLI

`sweep_config.toml` を編集してから実行:

```bash
python -m pulse_control sweep_config.toml
```

### Streamlit UI

```bash
streamlit run pulse_control/app.py
```

ブラウザで UI が開き、パラメータ入力・TOML インポート/エクスポート・掃引実行が可能。

## ファイル構成

```
pulse_control/
├── config.py          # 設定 dataclass, TOML 読み書き, バリデーション
├── core.py            # 装置通信 (PulseInstrument) + 掃引ロジック
├── main.py            # CLI エントリポイント
├── app.py             # Streamlit UI
├── sweep_config.toml  # 設定テンプレート
└── requirements.txt   # 依存パッケージ
```

## 設定パラメータ

| パラメータ | 説明 |
|---|---|
| `visa_address` | 81180A の VISA アドレス |
| `v_on` / `v_off` | パルス ON/OFF 電圧 [V] |
| `width_start` / `width_stop` / `width_step` | パルス幅の掃引範囲とステップ [s] |
| `frequency` / `period` | 周波数 [Hz] または 周期 [s]（TOML でどちらでも指定可） |
| `trigger_delay` | トリガー遅延 [サンプルポイント数]（8 の倍数） |
| `wait_time` | 掃引ステップ間の待ち時間 [s] |

## Lint / Format

```bash
ruff check pulse_control/
ruff format pulse_control/
```
