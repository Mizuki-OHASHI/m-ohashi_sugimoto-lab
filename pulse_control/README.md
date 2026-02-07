# Pulse Width Sweep — Keysight M96 PXI SMU

パルス幅を掃引しながら電圧・電流を測定するツール。
パルスの中心位置 (`center_delay`) を固定し、幅を変えても中心が動かないように制御する。

## 動作環境

- **Windows** または **Linux** (Agilent IO Libraries / Keysight IO Libraries が必要)
- Python 3.10+
- Keysight M96 PXI SMU + VISA 接続

> Mac は Agilent/Keysight IO Libraries Suite 非対応のため使用不可。

## セットアップ

### Keysight IO Libraries Suite のインストール

VISA 通信に必要な **Keysight IO Libraries Suite** を事前にインストールしてください。

1. [IO Libraries Suite Downloads](https://www.keysight.com/us/en/lib/software-detail/computer-software/io-libraries-suite-downloads-2175637.html) にアクセス
2. **「Download Windows x64 IOLS」** をクリックしてダウンロード
3. ダウンロードしたインストーラーを実行してインストール

### Windows

```powershell
cd pulse_control
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Linux

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

ブラウザで UI が開き、パラメータ入力・TOML インポート/エクスポート・掃引実行・結果プロットが可能。

## ファイル構成

```
pulse_control/
├── config.py          # 設定 dataclass, TOML 読み書き, バリデーション
├── core.py            # 装置通信 (PulseInstrument) + 掃引ロジック + データ保存
├── main.py            # CLI エントリポイント
├── app.py             # Streamlit UI
├── sweep_config.toml  # 設定テンプレート
└── requirements.txt   # 依存パッケージ
```

## 設定パラメータ

| パラメータ | 説明 |
|---|---|
| `visa_address` | M96 の VISA アドレス |
| `v_on` / `v_off` | パルス ON/OFF 電圧 [V] |
| `center_delay` | パルス中心のトリガーからの遅延 [s] |
| `width_start` / `width_stop` / `width_step` | パルス幅の掃引範囲とステップ [s] |
| `trigger_count` | 各幅でのトリガー繰り返し数 |
| `trigger_time` | トリガー間隔 [s] |
| `aperture_time` | アパーチャ時間 [s] |
| `sampling_points` | サンプリング点数 |
| `compliance_current` | コンプライアンス電流 [A] |
| `output_dir` | CSV 保存先ディレクトリ |

## Lint / Format

```bash
ruff check pulse_control/
ruff format pulse_control/
```
