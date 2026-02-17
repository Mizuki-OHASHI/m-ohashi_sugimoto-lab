# Agilent 81180A User's Guide - Programming Reference

> Source: *Agilent Arbitrary Waveform Generator 81180A User's Guide*
> パルス波形制御に必要な SCPI コマンドを網羅。

---

## 4.12.1 Channel & Group Control Commands

チャンネル選択とチャンネル間同期の制御。
81180A-264 (2ch モデル) では、コマンド送信前に必ず `INST:SEL` でチャンネルを選択する必要がある。

### Commands Summary (Table 4-2)

| Keyword | Parameter Form | Default | Notes |
|---------|---------------|---------|-------|
| `:INSTrument[:SELect]` | `CH1 \| CH2 \| 1 \| 2` | CH1 | Select channel |
| `:INSTrument:COUPle:OFFSet` | 0 to n-128 | 0 | Coarse offset [points] |
| `:INSTrument:COUPle:SKEW` | -3e-9 to 3e-9 | 0 | Fine skew [s] |
| `:INSTrument:COUPle:STATe` | `OFF \| ON \| 0 \| 1` | 0 | Channel sync |

### `:INSTrument{CH1|CH2|1|2}(?)`

Set the active channel for subsequent commands.

| Range | Type | Default | Description |
|-------|------|---------|-------------|
| CH1-CH2 or 1-2 | Discrete | 1 | Active channel for programming |

### `:INSTrument:COUPle:OFFSet{<ch_offset>}(?)`

When couple state is ON, set the coarse phase offset between CH1 (master) and CH2 (slave).

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<ch_offset>` | 0 to n-128 | Numeric (integer) | 0 | Offset in waveform points. Increment = 8 SCLK periods. Both channels must have same waveform length. |

### `:INSTrument:COUPle:SKEW{<ch_skew>}(?)`

When couple state is ON, set fine skew between channels. Applied to CH2 relative to CH1.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<ch_skew>` | -3e-9 to 3e-9 | Numeric | 0 | CH2 skew relative to CH1 [s]. |

### `:INSTrument:COUPle:STATe{OFF|ON|0|1}(?)`

Set the couple state of synchronized channels. When ON, CH1 sample clock feeds CH2 and start phases are locked.

| Range | Type | Default |
|-------|------|---------|
| 0-1 | Discrete | 0 |

---

## 4.12.2 Run Mode Commands

トリガ、ゲート、バースト、有効化の制御。

### Commands Summary (Table 4-3)

| Keyword | Parameter Form | Default | Notes |
|---------|---------------|---------|-------|
| `:ABORt` | | | Unconditional abort |
| `:ARM[:SEQuence]:ECL` | | | Sets ECL level |
| `:ARM[:SEQuence]:LEVel` | -5 to +5 | 1.6 | Event input threshold |
| `:ARM[:SEQuence]:SLOPe` | `POSitive \| NEGative \| EITHer` | POS | Event input edge |
| `:ARM[:SEQuence]:TTL` | | | Sets TTL threshold |
| `:ENABle` | | | Unconditional enable |
| `:INITiate:CONTinuous[:STATe]` | `OFF \| ON \| 0 \| 1` | 1 | Continuous/triggered mode |
| `:INITiate:CONTinuous:ENABle` | `SELF \| ARMed` | SELF | Enable mode |
| `:INITiate:CONTinuous:ENABle:SOURce` | `BUS \| EVENt \| TRIGger` | BUS | Enable source |
| `:INITiate:GATE[:STATe]` | `OFF \| ON \| 0 \| 1` | 0 | Gated mode |
| `:TRIGger[:IMMediate]` | | | Software trigger (= `*TRG`) |
| `:TRIGger:COUNt` | 1 to 1,048,576 | 1 | Burst count |
| `:TRIGger:DELay` | 0 to 8e6 (integer, x8) | 0 | Trigger delay [points] |
| `:TRIGger:ECL` | | | Sets ECL level |
| `:TRIGger:FILTer:HPASs:WIDTh` | 10e-9 to 2 | 1e-3 | High pass width [s] |
| `:TRIGger:FILTer:HPASs[:STATe]` | `OFF \| ON \| 0 \| 1` | 0 | |
| `:TRIGger:FILTer:LPASs:WIDTh` | 10e-9 to 2 | 1e-3 | Low pass width [s] |
| `:TRIGger:FILTer:LPASs[:STATe]` | `OFF \| ON \| 0 \| 1` | 0 | |
| `:TRIGger:HOLDoff` | 0, 100e-9 to 2 | 100e-3 | Holdoff period [s] |
| `:TRIGger:HOLDoff[:STATe]` | `OFF \| ON \| 0 \| 1` | 0 | |
| `:TRIGger:LEVel` | -5 to +5 | 1.6 | Trigger threshold [V] |
| `:TRIGger:MODE` | `NORMal \| OVERride` | NORM | Normal/retriggerable |
| `:TRIGger:SLOPe` | `POSitive \| NEGative \| EITHer` | POS | Trigger edge |
| `:TRIGger:SOURce[:ADVance]` | `EXTernal \| BUS \| TIMer \| EVENt` | EXT | Trigger source |
| `:TRIGger:TIMer:MODE` | `TIME \| DELay` | TIME | Timer mode |
| `:TRIGger:TIMer:DELay` | 152 to 8e6 (integer, x8) | 152 | End-to-start delay [points] |
| `:TRIGger:TIMer:TIME` | 100e-9 to 20 | 15e-6 | Start-to-start period [s] |
| `:TRIGger:TTL` | | | Sets TTL threshold |

### `:ABORt`

Immediate and unconditional termination of the output waveform. Effective in continuous+armed mode and all triggered modes. Output returns to idle state (DC, first sequence segment, etc.).

### `:ENABle`

Immediate and unconditional generation of the selected output waveform. Requires continuous+armed mode (`INIT:CONT:ENAB ARM`). No effect in triggered mode.

### `:INITiate:CONTinuous{1|0|ON|OFF}(?)`

Set run mode.

| Value | Description |
|-------|-------------|
| `1` (ON) | **Continuous** — waveforms generated continuously. |
| `0` (OFF) | **Triggered** — waveforms generated only on valid trigger signal. |

### `:INITiate:CONTinuous:ENABle{SELF|ARMed}(?)`

Set enable mode (effective in continuous mode only).

| Name | Type | Default | Description |
|------|------|---------|-------------|
| SELF | Discrete | SELF | Waveforms generated as soon as selected. |
| ARMed | Discrete | | Requires `ENAB` command to start generation. Use `ABOR` to stop. |

### `:INITiate:CONTinuous:ENABle:SOURce{BUS|EVENt|TRIGger}(?)`

Select the source of the enable signal (continuous mode only).

| Name | Description |
|------|-------------|
| BUS | Remote command (USB/LAN/GPIB). |
| EVENt | Event input connector. |
| TRIGger | Front panel trigger input connector. |

### `:INITiate:GATE{0|1|OFF|ON}(?)`

Set gated run mode.

| Value | Description |
|-------|-------------|
| `0` (OFF) | Continuous mode. |
| `1` (ON) | Gated — output only while gate signal is valid. Signal applied to trigger input. |

### `:TRIGger`

Software trigger from remote computer. Same as `*TRG`. Requires triggered mode (`INIT:CONT 0`) with source BUS.

### `:TRIGger:COUNt<burst>(?)`

Set burst count. Effective only in triggered mode (`INIT:CONT 0`).

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<burst>` | 1 to 1,048,576 | Numeric (integer) | 1 | Number of waveform cycles per trigger. |

### `:TRIGger:DELay<interval>(?)`

Set trigger delay — interval from valid trigger to first output waveform. Requires triggered mode (`INIT:CONT 0`).

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<interval>` | 0 to 8e6 | Numeric (integer) | 0 | Delay in **sample clock period increments**. `0` = OFF. **Must be divisible by 8.** Delay time changes if sample clock is modified. |

### `:TRIGger:FILTer:HPASs:WIDTh<width>(?)`

Set high pass filter width for trigger signal. Signals with pulse width below this value are rejected.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<width>` | 10e-9 to 2 | Numeric | 1e-3 | High pass threshold [s]. |

### `:TRIGger:FILTer:HPASs{OFF|ON|0|1}(?)`

Enable/disable high pass filter. Default: 0 (OFF).

### `:TRIGger:FILTer:LPASs:WIDTh<width>(?)`

Set low pass filter width for trigger signal. Signals with pulse width above this value are rejected.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<width>` | 10e-9 to 2 | Numeric | 1e-3 | Low pass threshold [s]. |

### `:TRIGger:FILTer:LPASs{OFF|ON|0|1}(?)`

Enable/disable low pass filter. Default: 0 (OFF).

> Note: If both HP and LP filters are ON, signals within the window (HP < width < LP) trigger the generator.

### `:TRIGger:HOLDoff<holdoff>(?)`

Set trigger holdoff period. All triggers within this period after a valid trigger are ignored.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<holdoff>` | 0, 100e-9 to 2 | Numeric | 100e-3 | Holdoff period [s]. |

### `:TRIGger:HOLDoff{OFF|ON|0|1}(?)`

Enable/disable holdoff filter. Default: 0 (OFF).

### `:TRIGger:LEVel<level>(?)`

Set threshold level for the trigger input.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<level>` | -5 to 5 | Numeric | 1.6 | Threshold [V]. |

### `:TRIGger:MODE{NORMal|OVERride}(?)`

Set trigger mode.

| Name | Description |
|------|-------------|
| NORMal (default) | First trigger activates, consecutive triggers ignored until waveform completes. |
| OVERride | Consecutive triggers restart the waveform immediately. |

### `:TRIGger:SLOPe{POSitive|NEGative|EITHer}(?)`

Set trigger edge.

| Name | Description |
|------|-------------|
| POSitive (default) | Positive going edge. |
| NEGative | Negative going edge. |
| EITHer | Both edges. |

### `:TRIGger:SOURce:ADVance{EXTernal|BUS|TIMer|EVENt}(?)`

Select trigger source. Requires triggered mode (`INIT:CONT 0`).

| Name | Description |
|------|-------------|
| EXTernal (default) | TRIG IN connector (or front panel MANUAL button). |
| BUS | Remote command only. |
| TIMer | Built-in internal trigger generator. |
| EVENt | Event IN connector. |

### `:TRIGger:TIMer:MODE{TIME|DELay}(?)`

Set internal trigger timer mode.

| Name | Description |
|------|-------------|
| TIME (default) | Start-to-start triggers (period in seconds). |
| DELay | End-to-start triggers (delay in waveform points). |

### `:TRIGger:TIMer:DELay<timer>(?)`

Set end-to-start delay of internal delayed trigger generator.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<timer>` | 152 to 8e6 | Numeric | 152 | Delay [waveform points]. **Must be divisible by 8.** |

### `:TRIGger:TIMer:TIME<timer>(?)`

Set period of internal timed trigger generator.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<timer>` | 100e-9 to 20 | Numeric | 15e-6 | Period [s]. Start-to-start. |

### `:ARM:LEVel<level>(?)`

Set threshold level for the **event** input.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<level>` | -5 to 5 | Numeric | 1.6 | Threshold [V]. |

### `:ARM:SLOPe{POSitive|NEGative|EITHer}(?)`

Set edge for the **event** input.

---

## 4.12.3 Analog Output Control Commands

出力波形の特性を制御。OUTPut サブシステム (出力端子) と SOURce サブシステム (波形形状, 周波数, レベル) の 2 系統。

3 つの出力パス:
- **DC**: 高振幅パルス応答に最適化 (帯域は狭い)
- **DAC**: 最高帯域幅 (振幅は低い)
- **AC**: RF アプリケーション向け (DC オフセット制御なし)

### Commands Summary (Table 4-4)

| Keyword | Parameter Form | Default | Notes |
|---------|---------------|---------|-------|
| `:OUTPut:COUPling` | `DC \| DAC \| AC` | DC | Output path selection |
| `:OUTPut[:STATe]` | `OFF \| ON \| 0 \| 1` | 0 | Output on/off |
| `:OUTPut:SYNC:FUNCtion` | `PULSe \| WCOMplete` | PULS | Sync shape |
| `:OUTPut:SYNC:POSition[:POINt]` | 0 to 16e6-32 | 0 | Sync position [points] |
| `:OUTPut:SYNC:WIDTh` | 32 to n-32 | 32 | Sync width [points] |
| `:OUTPut:SYNC:SOURce` | `CH1 \| CH2` | CH1 | Sync source |
| `:OUTPut:SYNC[:STATe]` | `OFF \| ON \| 0 \| 1` | 0 | Sync on/off |
| `:FREQuency[:CW]` | 10e-3 to 250e6 | 10e6 | Standard waveform freq [Hz] |
| `:FREQuency:RASTer` | 10e6 to 4.2e9 | 1e9 | Arb sample clock [Sa/s] |
| `:FREQuency:RASTer:SOURce` | `INTernal \| EXTernal` | INT | Clock source |
| `:FREQuency:RASTer:DIVider` | 1 to 256 (2^n) | 1 | External clock divider |
| `FUNCtion:MODE` | `FIXed \| USER \| SEQuence \| ASEQuence \| MODulation \| PULSe` | FIX | Function type |
| `:POWer[:LEVel][:AMPLitude]` | -5 to 5 | 0 | AC power [dBm] |
| `:ROSCillator:SOURce` | `INTernal \| EXTernal` | INT | 10 MHz reference source |
| `:ROSCillator[:EXTernal]:FREQuency` | 10e6 to 100e6 | 100e6 | External ref freq |
| `:VOLTage[:LEVel][:AMPLitude]` | 50e-3 to 2 | 500e-3 | DC amplitude [V] |
| `:VOLTage:DAC` | 50e-3 to 500e-3 | 500e-3 | DAC amplitude [V] |
| `:VOLTage:OFFSet` | -1.5 to 1.5 | 0 | DC offset [V] |

### `:OUTPut:COUPling{DC|DAC|AC}(?)`

Set the output amplifier path.

| Name | Type | Default | Description |
|------|------|---------|-------------|
| DC | Discrete | DC | DC-coupled amplifier. Use `VOLT` and `VOLT:OFFS` for control. |
| DAC | Discrete | | Direct DAC path (highest bandwidth, low amplitude). Use `VOLT:DAC` and `VOLT:OFFS`. |
| AC | Discrete | | AC-coupled (RF). Use `POW` for control. No DC offset available. |

### `:OUTPut{OFF|ON|0|1}(?)`

Set the output state. **Defaults to OFF after power-on** (safety). OFF state leaves output connected to amplifier path but no signal is generated.

### `:OUTPut:SYNC:FUNCtion{PULSe|WCOMplete}(?)`

Set sync output shape.

| Name | Description |
|------|-------------|
| PULSe (default) | Programmable position and width (min 32 SCLK periods, increments of 32). |
| WCOMplete | Waveform complete pulse. High at waveform start, low after cycle completes. Width/position not adjustable. |

### `:OUTPut:SYNC:POSition<position>(?)`

Set sync position. Active in **USER (arbitrary) mode only**.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<position>` | 0 to 16e6-32 | Numeric (integer) | 0 | Position [waveform points]. Increment = 32. Must be divisible by 32. |

### `:OUTPut:SYNC:WIDTh<width>(?)`

Set sync width. Active in **USER (arbitrary) mode only**.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<width>` | 32 to n-32 | Numeric (integer) | 32 | Width [waveform points]. Increment = 32. n = segment length. |

### `:OUTPut:SYNC:SOURce{CH1|CH2|1|2}(?)`

Select sync output source channel. Only one sync output connector exists on front panel.

### `:OUTPut:SYNC{OFF|ON|0|1}(?)`

Set sync output state. Defaults to OFF after power-on.

### `:FREQuency{<freq>|MINimum|MAXimum}(?)`

Set frequency of **standard waveforms** [Hz]. **No effect on arbitrary waveforms.**

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<freq>` | 10e-3 to 250e6 | Numeric | 10e6 | Frequency [Hz]. Resolution up to 8 digits. |
| `MINimum` | | Discrete | | 10e-3 Hz |
| `MAXimum` | | Discrete | | 250e6 Hz |

### `:FREQuency:RASTer{<sclk>|MINimum|MAXimum}(?)`

Set sample clock frequency of **arbitrary waveforms** [Sa/s]. **No effect on standard waveforms.**

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<sclk>` | 10e6 to 4.2e9 | Numeric | 1e9 | Sample clock [Sa/s]. Resolution up to 8 digits. |
| `MINimum` | | Discrete | | 10e6 Sa/s |
| `MAXimum` | | Discrete | | 4.2e9 Sa/s |

### `:FREQuency:RASTer:SOURce{INTernal|EXTernal}(?)`

Select sample clock source.

| Name | Type | Default | Description |
|------|------|---------|-------------|
| INTernal | Discrete | INT | Internal clock generator (unique per channel). |
| EXTernal | Discrete | | External clock input (shared between channels). |

### `:FREQuency:RASTer:DIVider<divider>(?)`

Set external sample clock divider (for different sample rates per channel).

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<divider>` | 1 to 256 | Numeric (integer) | 1 | Divider. Must be 2^n (except 1 = no divider). Each channel can have different value. |

### `FUNCtion:MODE{FIXed|USER|SEQuence|ASEQuence|MODulation|PULSe}(?)`

Set the waveform type at the output.

| Name | Type | Default | Description |
|------|------|---------|-------------|
| **FIXed** | Discrete | FIX | Standard waveform shapes (built-in). |
| **USER** | Discrete | | **Arbitrary waveform**. Must be loaded to memory first. |
| **SEQuenced** | Discrete | | Sequenced waveform. Download segments first, then build sequence table. |
| **ASEQuenced** | Discrete | | Advanced sequencing. |
| **MODulated** | Discrete | | Modulated waveforms (built-in or custom). |
| **PULSe** | Discrete | | Digital pulse function (digitally constructed from arbitrary memory). |

**Response**: Returns `FIX`, `USER`, `SEQ`, `ASEQ`, `MOD`, or `PULS`.

> **重要**: `ARB` は有効な引数ではない。Arbitrary モードは `USER` を使う。

### `:POWer{<power>|MINimum|MAXimum}(?)`

Set output power. **AC output path only** (`OUTP:COUP AC`). Calibrated for 50 ohm load.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<power>` | -5 to 5 | Numeric | 0 | RF power [dBm]. |

### `:ROSCillator:SOURce{INTernal|EXTernal}(?)`

Set 10 MHz reference source.

| Name | Type | Default | Description |
|------|------|---------|-------------|
| INTernal | Discrete | INT | TCXO, 1 ppm accuracy. |
| EXTernal | Discrete | | External reference input. Must be connected. |

### `:ROSCillator:FREQuency<frequency>(?)`

Set frequency range for external reference PLL.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<frequency>` | 10e6 to 100e6 | Numeric | 100e6 | PLL lock frequency [Hz]. |

### `:VOLTage{<voltage>|MINimum|MAXimum}(?)`

Set amplitude (DC output path). Use `OUTP:COUP DC`. Calibrated for 50 ohm load.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<voltage>` | 50e-3 to 2 | Numeric | 500e-3 | Amplitude [V] on 50 ohm. |

> Constraint: `|offset + amplitude/2|` must not exceed the specified voltage window.

### `:VOLTage:DAC{<voltage>|MINimum|MAXimum}(?)`

Set amplitude (DAC output path). Use `OUTP:COUP DAC`.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<voltage>` | 50e-3 to 500e-3 | Numeric | 500e-3 | DAC amplitude [V] on 50 ohm. |

### `:VOLTage:OFFSet{<offset>|MINimum|MAXimum}(?)`

Set DC offset. Affects DAC and DC output paths.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<offset>` | -1.5 to 1.5 | Numeric | 0 | Offset [V] on 50 ohm. |

> Constraint: `|offset + amplitude/2|` must not exceed the specified voltage window.

---

## 4.12.5 Standard Waveforms Control Commands

Standard waveform の形状とパラメータの制御。
`FUNC:MODE FIX` が選択されている場合のみ有効。
波形はコマンド送信のたびに再計算されるため、小さな遅延が発生する。

### Commands Summary (Table 4-6)

| Keyword | Parameter Form | Default | Notes |
|---------|---------------|---------|-------|
| `:FUNCtion:SHAPe` | `SINusoid \| TRIangle \| SQUare \| RAMP \| SINC \| GAUSsian \| EXPonential \| NOISe \| DC` | SIN | Standard function shape |
| `:SINusoid:PHASe` | 0 to 360 | 0 | Start phase [deg] |
| `:TRIangle:PHASe` | 0 to 360 | 0 | Start phase [deg] |
| `:SQUare:DCYCle` | 0 to 99.99 | 50 | Duty cycle [%] |
| `:RAMP:DELay` | 0 to 99.99 | 10 | Ramp delay [%] |
| `:RAMP:TRANsition[:LEADing]` | 0 to 99.99 | 60 | Rise time [%] |
| `:RAMP:TRANsition:TRAiling` | 0 to 99.99 | 30 | Fall time [%] |
| `:SINC:NCYCle` | 4 to 100 | 10 | Zero-crossings |
| `:GAUSsian:EXPonent` | 1 to 200 | 10 | Exponent |
| `:EXPonential:EXPonent` | -100 to 100 | -10 | Exponent |
| `:DC[:OFFSet]` | -1.5 to 1.5 | 0 | DC offset [V] |

### `FUNCtion:SHAPe{SINusoid|TRIangle|SQUare|RAMP|SINC|GAUSsian|EXPonential|DC|NOISe}(?)`

Set waveform shape. Only effective when `FUNC:MODE FIX` is selected.

| Name | Type | Default | Description |
|------|------|---------|-------------|
| SINusoid | Discrete | SIN | Sine waveform |
| TRIangle | Discrete | | Triangular waveform |
| SQUare | Discrete | | Square waveform |
| RAMP | Discrete | | Ramp waveform |
| SINC | Discrete | | Sinc waveform |
| EXPonential | Discrete | | Exponential waveform |
| GAUSsian | Discrete | | Gaussian waveform |
| DC | Discrete | | DC waveform |
| NOISe | Discrete | | Noise waveform |

**Response**: Returns `SIN`, `TRI`, `SQU`, `SPUL`, `RAMP`, `SINC`, `GAUS`, `EXP`, `DC`, or `NOIS`.

### `SINusoid:PHASe<phase>(?)`

Set start phase for sine waveform.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<phase>` | 0 to 360 | Numeric | 0 | Start phase [degrees]. Resolution 0.01 (limited at high freq). |

### `TRIangle:PHASe<phase>(?)`

Set start phase for triangular waveform.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<phase>` | 0 to 360 | Numeric | 0 | Start phase [degrees]. Resolution 0.01. |

### `SQUare:DCYCle<duty_cycle>(?)`

Set duty cycle of square waveform.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<duty_cycle>` | 0 to 99.99 | Numeric | 50 | Duty cycle [%]. Resolution 0.01%. |

> **注意**: SQUare モードでは `:PHASe` コマンドは効果がない (実機で確認済み)。
> また、振幅の符号は無視される (abs 処理される)。
> → V_ON < V_OFF のパルスは Square モードでは実現不可。Arbitrary (USER) モードを使用すること。

### `RAMP:DELay<delay>(?)`

Set delay from waveform start to first ramp transition.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<delay>` | 0 to 99.99 | Numeric | 10 | Delay [%]. |

### `RAMP:TRANsition[:LEADing]<rise>(?)`

Set ramp rise time (low to high).

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<rise>` | 0 to 99.99 | Numeric | 60 | Rise time [%]. |

### `RAMP:TRANsition:TRAiling<fall>(?)`

Set ramp fall time (high to low).

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<fall>` | 0 to 99.99 | Numeric | 30 | Fall time [%]. |

### `SINC:NCYCle<N_cycles>(?)`

Set number of zero-crossings for SINC waveform.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<N_cycles>` | 4 to 100 | Numeric (integer) | 10 | Zero-crossings. |

### `GAUSsian:EXPonent<exp>(?)`

Set exponent for Gaussian waveform.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<exp>` | 1 to 200 | Numeric (integer) | 10 | Exponent. |

### `EXPonential:EXPonent<exp>(?)`

Set exponent for exponential waveform.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<exp>` | -100 to 100 | Numeric (integer) | -10 | Exponent. |

### `DC[:OFFSet]<offset>(?)`

Set DC function offset.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<offset>` | -1.5 to 1.5 | Numeric | 0 | DC offset [V]. Output path is automatically set to DC. |

---

## 4.12.6 Arbitrary Waveforms Control Commands

Arbitrary 波形のメモリ管理、セグメント定義、波形データダウンロード。

- メモリ容量: 16M words (standard) / 64M words (optional)
- セグメント数: 最大 32,000
- **最小セグメント長: 320 points**
- **セグメント増分: 32 points**
- DAC 分解能: 12-bit (0 ~ 4095)

### Commands Summary (Table 4-7)

| Keyword | Parameter Form | Default | Notes |
|---------|---------------|---------|-------|
| `:TRACe[:DATA]` | `#<header><binary_block>` | | Waveform data array |
| `:TRACe:DEFine` | `<segment_#>, <320 to 16(64)e6>` | | Segment and length |
| `:TRACe:DELete[:NAME]` | 1 to 32,000 | | Delete one segment |
| `:TRACe:DELete:ALL` | | | Delete all segments |
| `:TRACe:POINts?` | | | Query waveform length |
| `:TRACe:SELect` | 1 to 32,000 | 1 | Active segment |
| `:TRACe:SELect:SOURce` | `BUS \| EXTernal` | BUS | Segment control source |
| `:TRACe:SELect:TIMing` | `COHerent \| IMMediate` | COH | Segment transition timing |
| `:SEGMent[:DATA]` | `#<header><binary_block>` | | Segment table data |

### `:TRACe#<header><binary_block>`

Download waveform data using IEEE-STD-488.2 high-speed binary transfer.

Example (1,024 points):

```
TRACe#42048<binary_block>
```

Header:
- `#` — start of binary data block
- `4` — number of digits that follow
- `2048` — number of bytes (= 2 x 1024 points)

**16-bit integers**, sent as **two-byte words**. Total bytes = 2 x number of data points.

> Transfer must terminate with the EOI bit set.

### 16-bit Data Point Format

```
Low byte:  D0  D1  D2  D3  D4  D5  D6  D7
High byte: D8  D9  D10 D11 D12 D13 D14 D15
```

| Bits | Function | Notes |
|------|----------|-------|
| D0-D11 | Waveform data (12-bit) | 0x000 = -2V, 0xFFF = +2V. 2048 = 0V. |
| D12 | Marker 1 | |
| D13 | Marker 2 | |
| D14 | Stop bit | All 32 words in group must have same value. |
| D15 | Reserved | Must be 0. |

**Notes:**
1. データは **32 words** 単位でグループ化される → セグメント長は **32 の倍数**。
2. Stop bit (D14): `0` = 通常, `1` = セグメント末端 (グループ内全 32 words 同値)。
3. D15 は常に `0`。
4. Marker (D12, D13): グループ内の最初の 24 words は don't-care, 最後の 8 words にマーカー位置データ。解像度 = 4 SCLK cycles。
5. DAC MUX の制約により、マーカー配置は 24 points オフセットされる。

### `:TRACe:DEFine<segment_#>,<length>`

Define segment size.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<segment_#>` | 1 to 16k | Numeric (integer) | 1 | Segment number. |
| `<length>` | **320** to n | Numeric (integer) | | Segment size. **Minimum = 320 points. Increment = 32 points.** |

> 81180A は interlaced mode (32 memory cells → 1 byte)。セグメントサイズは **32 で割り切れる** 必要がある。
> 例: 2112 → OK, 2110 → エラー。

### `:TRACe:DELete<segment_#>`

Delete one segment.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<segment_#>` | 1 to 32,000 | Numeric (integer) | 1 | Segment to delete. |

> 最後のセグメントを削除した場合、新しいセグメントのサイズは残りメモリまで。
> 最後でないセグメントを削除した場合、新しいセグメントは削除されたサイズ以下でなければならない。

### `:TRACe:DELete:ALL`

Delete all segments and clear entire waveform memory.

> メモリ全体のデフラグにも使用。波形を一から構築する前に必ず実行すること。

### `:TRACe:POINts?`

Query active waveform length [points].

### `:TRACe:SELect<segment_#>(?)`

Set active waveform segment. 2 つの機能:
1. 以降の `TRAC` コマンドがこのセグメントに作用する。
2. SYNC 出力がこのセグメントに割り当てられる。

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<segment_#>` | 1 to 32,000 | Numeric (integer) | 1 | Active segment. |

### `:TRACe:SELect:SOURce{BUS|EXTernal}(?)`

Select segment control source.

| Name | Description |
|------|-------------|
| BUS (default) | Remote command only. |
| EXTernal | Rear panel connector (8-bit parallel, up to 256 segments). |

### `:TRACe:SELect:TIMing{COHerent|IMMediate}(?)`

Set segment transition timing.

| Name | Description |
|------|-------------|
| COHerent (default) | Current waveform completes before jumping to next. |
| IMMediate | Current waveform aborted; new waveform starts immediately. |

### `SEGMent#<header><binary_block>`

高速一括メモリセグメント定義。32-bit integers, 4 bytes per segment.

Example (3 segments):

```
SEGment#212<binary_block>
```

**Notes:**
1. 各チャンネルに独自のセグメントテーブル。`INST:SEL` で先にチャンネル選択が必要。
2. `SEGM#` は既存のセグメント定義を上書き (`TRAC:DEL:ALL` と同等)。
3. セグメント数: 1 ~ 32,000。
4. バイト数は 4 で割り切れる必要がある。

**Combined download approach:**
1 つの大きな波形をダウンロードしてから `SEGM#` で分割できる。
2 番目以降のセグメントには、先頭に **32 dummy points** (= そのセグメントの最初の値) を追加する必要がある。

---

## 4.13 Programming Considerations

### データの種類

81180A が受け付けるデータ:

1. **コマンド** — 機能/パラメータの設定 (SCPI)
2. **クエリ** — 現在の状態の問い合わせ
3. **波形データ** — Arbitrary 波形用バイナリ
4. **テーブルデータ** — シーケンス、メモリセグメンテーション

### コマンドバッファ

- SCPI コマンドの解析は数ミリ秒。
- 入力バッファサイズ = **256 文字**。
- 256 文字を超えるコマンドチェーンはバッファを溢れさせる可能性あり。

**推奨**: コマンドは 1 つずつ、または短い文字列で送信:

```
Inst:sel 1
Func:mode user
trac:def 1,10240;def 2, 20480;def 3, 348; sel 1
volt 1.250;offs -0.350;:outp 1
```

> **重要**: 制御コマンドと波形データ転送を混在させないこと。
> バイナリダウンロード中に割り込むとインターフェースがロックアウトし、**電源再投入でのみ復旧**する。

### `*RST` コマンド

- 全設定をリセット (数百の設定にアクセス)。
- 完了まで **1-2 秒** の固定遅延が必要。
- または STB レジスタでレディ状態を確認。

### クエリのベストプラクティス

連続クエリはタイムアウトの原因になる。推奨パターン:

```
*sre16          (MAV bit で SRE 有効化)
Query?
ReadSTB         (応答が 16 になるまで待機)
Read response
```

### 波形データのダウンロード

2 段階プロセス:

1. **SCPI コマンドで準備** (セグメント選択/定義)
2. **バイナリ形式で波形データ転送**

```
func:mode user
trac:sel 1
trac:def 1, 2048
```

`trac#<data_array>` コマンドの構造:
1. **ヘッダー** — ASCII, `#` で区切り、転送バイト数を指定
2. **波形データ** — バイナリ, 直接 arbitrary waveform memory にルーティング

> CPU はバイナリ転送中はインターフェースを制御できない。全データが転送されるまで他のコマンドは受け付けない。

### 終端文字

- **CR** (`\r`): 不要。81180A が受信しても無視される。
- **NL** (`\n`): **全インターフェース (USB, LAN, GPIB) で推奨**。
- コマンド送信: `\n` で終端。
- 応答受信: `\n` で終端されることを期待。

### タイムアウト

プログラム内のタイムアウト値は操作に応じて適切に設定すること。特に:
- `*RST` 後: 1-2 秒
- 波形ダウンロード: データサイズに応じた十分な時間
- クエリ: STB レジスタ確認による適切な待機

---

## C# Example: Creating and Downloading an Arbitrary Waveform

(User's Guide pp.275-279)

```csharp
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;
using System.IO;
using System.Collections.ObjectModel;
using Ivi.Visa.Interop;
using IO488Extensions;


namespace downloadArbitraryWaveform
{
    public partial class Form1 : Form
    {
        ResourceManagerClass rm = new ResourceManagerClass();
        FormattedIO488Class fIO = new FormattedIO488Class();

        public Form1()
        {
            InitializeComponent();
            this.StartPosition = FormStartPosition.CenterScreen;
            textBox1.Text = "GPIB0::5::INSTR";
        }


        private void DownloadWaveformButton_Click(object sender, EventArgs e)
        {
            try
            {
                // Prepare the coordinates of an Arbitrary Waveform (sinewave)
                int iWaveLength = Convert.ToInt32(WaveLengthTextBox.Text);
                Collection<float> dataPoints = calculateSinusoidWaveform
                                            (iWaveLength, 1.5, 0);

                // Connect and identify the instrument
                string addressString = textBox1.Text;
                fIO.IO = (IMessage)rm.Open(addressString, AccessMode.NO_LOCK, 0,
                                           "Timeout = 10000");

                if (fIO.IO.HardwareInterfaceName == "GPIB" ||
                    fIO.IO.HardwareInterfaceName == "USB")
                {
                    // Enable the MAV bit in the SRE of IEEE 488.2
                    fIO.WriteString("*CLS;*SRE16\n", true);
                }
                else if (fIO.IO.HardwareInterfaceName == "TCPIP")
                    fIO.IO.TerminationCharacterEnabled = true;

                // Reset the instrument
                fIO.WriteString("*RST\n", true);

                // Read identification string
                string strDevID = fIO.QueryString("*IDN?\n", true);

                fIO.WriteString(":INST:SEL 1", true);
                // Set the ARBITRARY mode for channel 1
                fIO.WriteString(":FUNC:MODE USER", true);

                // Program the sample clock frequency
                fIO.WriteString(":FREQ:RAST 1.5E+08", true);
                // Program the amplitude
                fIO.WriteString(":VOLT 2", true);
                // Program the offset
                fIO.WriteString(":VOLT:OFFS 0", true);
                // Delete the segment table
                fIO.WriteString(":TRAC:DEL:ALL", true);
                // Download the Arbitrary Waveform as binary block
                SendDataToInstrument(dataPoints.ToArray(), 1);

                fIO.WriteString(":OUTP ON", true);

                fIO.IO.Close();
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }

        private void SendDataToInstrument(float[] fDataPts, int segmentNumber)
        {
            // Define a segment
            fIO.WriteString(":TRAC:DEF " + segmentNumber.ToString()
                            + "," + fDataPts.Length.ToString(), true);

            // Select the pre-defined segment
            fIO.WriteString(":TRAC:SEL " + segmentNumber.ToString(), true);

            // DAC Values Conversion
            short[] dacValues = new short[fDataPts.Length];

            float fMin = fDataPts.Min();
            float fMax = fDataPts.Max();
            float fDiff = Math.Abs(fMax - fMin);
            byte[] bArray = new byte[fDataPts.Length * sizeof(short)];
            int cnt = 0;

            for (int i = 0; i < fDataPts.Length; i++)
            {
                if (fDiff == 0)
                    fDataPts[i] = 0.0f;
                else
                    fDataPts[i] = ((fDataPts[i] - fMin) / fDiff * 2) - 1;

                dacValues[i] = (short)Math.Floor((fDataPts[i] * 2047) + 2048.5);

                // Convert DAC Values to Bytes (little-endian)
                byte[] temp = BitConverter.GetBytes(dacValues[i]);
                bArray[cnt++] = temp[0];  // low byte
                bArray[cnt++] = temp[1];  // high byte
            }

            // Download data (binary block)
            fIO.WriteIEEEBlock(":TRACe:DATA ", bArray);
        }

        private Collection<float> calculateSinusoidWaveform(long lPoints,
        double dCycles, double dStartPhase)
        {
            double omega, phase;
            Collection<float> dataPoints = new Collection<float>();

            phase = dStartPhase * Math.PI / 180.0;
            omega = 1.0 / lPoints * Math.PI * 2 * dCycles;

            for (long i = 0; i < lPoints; i++)
                dataPoints.Add((float)Math.Sin((omega * (double)i) + phase));

            return dataPoints;
        }
    }
}
```

### IO488 Extension Classes

```csharp
using System;
using System.Collections.Generic;
using Ivi.Visa.Interop;


namespace IO488Extensions
{
    public static class IO488QueryExtension
    {
        private const short MAV = 0x10;
        private const long TIMEOUT = 8000; // 8s

        public static string QueryString(this FormattedIO488Class io,
        string format, bool flushAndEND)
        {
            io.WriteString(format, flushAndEND);
            return ReadString(io, true);
        }

        public static string ReadString(this FormattedIO488Class io,
        bool CheckMAVBit)
        {
            if (CheckMAVBit &&
                (io.IO.HardwareInterfaceName == "GPIB" ||
                io.IO.HardwareInterfaceName == "USB"))
            {
                short stb = 0;
                long endMs, startMs = DateTime.Now.Ticks /
                    TimeSpan.TicksPerMillisecond;
                do
                {
                    endMs = DateTime.Now.Ticks / TimeSpan.TicksPerMillisecond;
                    if ((endMs - startMs) > TIMEOUT)
                        throw new Exception(
                            "IO488QueryExtension: A timeout occurred");
                    stb = io.IO.ReadSTB();
                } while ((stb & MAV) != MAV);
            }
            return io.ReadString();
        }
    }


    public static class IO488WriteIEEEBlockExtension
    {
        private const int CHUNK_LENGTH = 32000;
        private const string OPERATION_COMPLETED = "1";

        public static void WriteIEEEBlock(this FormattedIO488Class io,
        string Command, object data)
        {
            if (io.IO.HardwareInterfaceName == "GPIB" ||
                io.IO.HardwareInterfaceName == "USB")
            {
                string answer = io.QueryString("*OPC?\n", true).TrimEnd('\n');
                if (answer.Equals(OPERATION_COMPLETED))
                {
                    byte[] BinaryBlock = (byte[])data;
                    string Digits = String.Format("{0}", BinaryBlock.Length);
                    byte[] Header = ToByteArray(String.Format("{0} #{1}{2}",
                        Command, Digits.Length, Digits));

                    if (io.IO.Write(ref Header, Header.Length) == Header.Length)
                    {
                        byte[] Chunk = new byte[CHUNK_LENGTH];
                        for (int Start = 0; Start < BinaryBlock.Length;
                            Start += Chunk.Length)
                        {
                            int Length = Math.Min(Chunk.Length,
                                BinaryBlock.Length - Start);
                            System.Buffer.BlockCopy(BinaryBlock,
                                Start, Chunk, 0, Length);
                            if (io.IO.Write(ref Chunk, Length) != Length)
                                throw new Exception(
                                    "WriteIEEEBlock: Buffer not transmitted");
                        }
                    }
                    else
                        throw new Exception(
                            "WriteIEEEBlock: Buffer not transmitted");
                }
                else
                    throw new Exception(
                        "WriteIEEEBlock: Device not ready");
            }
            else if (io.IO.HardwareInterfaceName == "TCPIP")
            {
                io.WriteString("*OPC?\n", true);
                string answer = io.ReadString().TrimEnd('\n');
                if (answer.Equals(OPERATION_COMPLETED))
                    io.WriteIEEEBlock(Command, data, true);
                else
                    throw new Exception(
                        "WriteIEEEBlock: Device not ready");
            }
            else
                io.WriteIEEEBlock(Command, data, true);
        }

        private static byte[] ToByteArray(string str)
        {
            return new System.Text.ASCIIEncoding().GetBytes(str);
        }
    }
}
```

---

## 実装ノート (本プロジェクト固有)

### DAC 変換

C# example の `SendDataToInstrument` における DAC 値変換:

1. 入力値を `-1.0` ~ `+1.0` に正規化:
   ```
   normalized = ((value - min) / (max - min) * 2) - 1
   ```
2. DAC 値 (0-4095) に変換:
   ```
   dacValue = Floor(normalized * 2047 + 2048.5)
   ```
   - `-1.0` → **1** (≒ 最小)
   - `0.0` → **2048** (中点)
   - `+1.0` → **4095** (最大)

3. バイトオーダー: **Little-endian** (low byte first)

### SCPI コマンド実行順序 (Arbitrary モード)

```
:INST CH{channel}              // チャンネル選択
:FUNC:MODE USER                // Arbitrary モード (★ "ARB" ではない)
:TRAC:DEL:ALL                  // 全セグメント削除
:FREQ:RAST {sample_rate}       // サンプルクロック設定
:TRAC:DEF {seg}, {length}      // セグメント定義
:TRAC:SEL {seg}                // セグメント選択
:TRACe:DATA <binary_block>     // 波形データダウンロード
:TRAC:SEL 1                    // 最初のセグメント選択
:VOLT:AMPLitude {ampl}         // 振幅設定
:VOLT:OFFSet {offs}            // オフセット設定
:TRIGger:DELay {delay}         // トリガ遅延
:OUTPut ON                     // 出力ON
*OPC?                          // 完了確認
```

### Square モードの制約

- 81180A は振幅の符号を無視する (`abs` 処理)
- `:PHASe` コマンドは Square 波形に効果なし (実機確認済み)
- → **V_ON < V_OFF のパルスは Square モードでは実現不可**
- → Arbitrary (USER) モードで inverted DAC 値を使用すること

### 高インピーダンス負荷の計算

81180A の SCPI 値は 50 ohm 基準。高インピーダンス (Hi-Z) 負荷では出力が 2 倍になる:

```
ampl_scpi = abs(v_on - v_off) / 2    # 50 ohm reference
offs_scpi = (v_on + v_off) / 4       # 50 ohm reference
```

出力電圧 (Hi-Z):
```
V_high = (offs_scpi + ampl_scpi/2) * 2 = v_on
V_low  = (offs_scpi - ampl_scpi/2) * 2 = v_off
```
