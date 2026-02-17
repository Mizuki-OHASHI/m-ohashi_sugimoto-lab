# Agilent 81180A User's Guide - Programming Reference (抜粋)

> Source: *Agilent Arbitrary Waveform Generator 81180A User's Guide*
> Sections: 4.12.5, 4.12.6, 4.13 (Programming Considerations & C# Example)

---

## 4.12.5 Standard Waveforms Control Commands (抜粋)

### `:FREQuency{<freq>|MINimum|MAXimum}(?)`

Use this command to set or query the frequency of the standard waveforms in units of hertz (Hz).
**This parameter has no effect on arbitrary waveforms.**

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<freq>` | 10e-3 to 250e6 | Numeric | 10e6 | Frequency of the standard waveform [Hz]. Resolution up to 8 digits. |
| `MINimum` | | Discrete | | Lowest possible frequency (10e-3). |
| `MAXimum` | | Discrete | | Highest possible frequency (250e6). |

### `:FREQuency:RASTer{<sclk>|MINimum|MAXimum}(?)`

Use this command to set or query the sample clock frequency of the arbitrary waveform in units of samples per second (Sa/s).
**This parameter has no effect on standard waveforms.**

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<sclk>` | 10e6 to 4.2e9 | Numeric | 1e9 | Sample clock frequency [Sa/s]. Resolution up to 8 digits. |
| `MINimum` | | Discrete | | Lowest possible frequency (10e6). |
| `MAXimum` | | Discrete | | Highest possible frequency (4.2e9). |

### `:FREQuency:RASTer:SOURce{INTernal|EXTernal}(?)`

Use this command to select or query the source of the sample clock generator.

- **INTernal** (default): Selects the internal clock generator.
- **EXTernal**: Activates the external sample clock input. A valid signal must be applied.

> Note: The internal sample clock generator is unique for each channel. When external clock is selected, the same source is applied to both channels.

### `:FREQuency:RASTer:DIVider<divider>(?)`

Set or query the sample clock frequency divider.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<sclk>` | 1 to 256 | Numeric (integer only) | 1 | External sample clock divider. Except 1 (no divider), all values must be 2^n. Each channel may have a different divider. |

### `FUNCtion:MODE{FIXed|USER|SEQuence|ASEQuence|MODulation|PULSe}(?)`

Use this command to set or query the type of waveform at the output connector.

| Name | Type | Default | Description |
|------|------|---------|-------------|
| **FIXed** | Discrete | FIX | Standard waveform shapes (built-in). |
| **USER** | Discrete | | Arbitrary waveform shapes. Must be loaded to memory first. |
| **SEQuenced** | Discrete | | Sequenced waveform output. Download segments first, then build sequence table. |
| **ASEQuenced** | Discrete | | Advanced sequencing. Download segments, build sequences, then build advanced sequence table. |
| **MODulated** | Discrete | | Modulated waveforms (built-in or custom). |
| **PULSe** | Discrete | | Digital pulse function. Digitally constructed from arbitrary memory. |

**Response**: Returns `FIX`, `USER`, `SEQ`, `ASEQ`, `MOD`, or `PULS`.

### `:VOLTage{<voltage>|MINimum|MAXimum}(?)`

Set or query the amplitude of the waveform (DC output path).
Use `outp:coup dc` to set dc-coupled. Calibrated for 50 ohm load.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<voltage>` | 50e-3 to 2 | Numeric | 500e-3 | Amplitude [V] on 50 ohm. |
| `MINimum` | | Discrete | | 50e-3 |
| `MAXimum` | | Discrete | | 2 |

### `:VOLTage:OFFSet{<offset>|MINimum|MAXimum}(?)`

Set or query the DC offset.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<offset>` | -1.5 to 1.5 | Numeric | 0 | Offset [V] on 50 ohm. |

> Constraint: `|offset + amplitude/2|` must not exceed the specified voltage window.

---

## 4.12.6 Arbitrary Waveforms Control Commands

Waveforms are created using small sections of the arbitrary memory.
The memory can be partitioned into smaller segments (up to 16k) and different waveforms can be loaded into each segment.

**Minimum segment size is 320 points and can be increased by increments of 32 points.**

### Commands Summary

| Keyword | Parameter Form | Default | Notes |
|---------|---------------|---------|-------|
| `:TRACe` | | | |
| `[:DATA]` | `#<header><binary_block>` | | Waveform data array |
| `:DEFine` | `<segment_#>, <320 to 16(64)e6>` | | Segment and length |
| `:DELete[:NAME]` | 1 to 32,000 | | Delete one segment |
| `:DELete:ALL` | | | Delete all segments |
| `:POINts?` | | | Query waveform length |
| `:SELect` | 1 to 32,000 | 1 | |
| `:SELect:SOURce` | `BUS \| EXTernal` | BUS | Toggle control source |
| `:SELect:TIMing` | `COHerent \| IMMediate` | COH | Select timing |
| `:SEGMent[:DATA]` | `#<header><binary_block>` | | Segment data array |

### `:TRACe#<header><binary_block>`

Download waveform data to the 81180A waveform memory using high-speed binary transfer (IEEE-STD-488.2).

Example: download 1,024 points:

```
TRACe#42048<binary_block>
```

Header interpretation:
- `#` — start of binary data block
- `4` — number of digits that follow
- `2048` — number of bytes to follow (= 2 x 1024 points)

The generator accepts waveform samples as **16-bit integers** sent in **two-byte words**.
Total number of bytes = 2 x number of data points.

**Binary block data format:**

```
"#"  |  non-zero ASCII digit  |  ASCII digit(s)  |  low byte (binary)  |  high byte (binary)
      Number of digits         Byte count          2 bytes per data point
```

> Transfer must terminate with the EOI bit set.

### 16-bit Data Point Format

Waveform data is 16-bit words:

```
Low byte:  D7  D6  D5  D4  D3  D2  D1  D0
High byte: D8  D9  D10 D11 D12 D13 D14 D15
                        MSB
```

- **D0-D11**: Waveform data (12-bit). Range: 0x000 to 0xFFF (0 to 4095).
  - 0x000 = -2V, 0xFFF = +2V
  - 4095 = full-scale amplitude, 2048 = 0V amplitude
- **D12**: Marker 1
- **D13**: Marker 2
- **D14**: Stop bit (all 32 words in a group must have same value)
- **D15**: Must be 0 (all words)

**Notes:**
1. Each group of data contains **32 words**. Waveform data is programmed in **multiples of 32 words**.
2. Stop bit (D14): `0` = normal, `1` = end of waveform segment (all 32 words in group must match).
3. D15 must be `0` for all words.
4. Marker data (D12, D13): First 24 words in a group are don't-care; last 8 words contain marker position data. Marker resolution = 4 sample clock cycles.
5. Due to DAC multiplexing, marker placement is offset by 24 points.

### `:TRACe:DEFine<segment_#>,<length>`

Define the size of a specific memory segment.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<segment_#>` | 1 to 16k | Numeric (integer) | 1 | Segment number |
| `<length>` | 320 to n | Numeric (integer) | | Segment size. **Minimum = 320 points**. Maximum limited by installed memory. **Increment = 32 points**. |

> The 81180A operates in interlaced mode where 32 memory cells generate one byte of data.
> Segment size must be evenly divisible by 32.
> Example: 2112 is acceptable. 2110 is not (not a multiple of 32).

### `:TRACe:DELete<segment_#>`

Delete a predefined segment from working memory.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<segment_#>` | 1 to 32,000 | Numeric (integer) | 1 | Segment to delete |

> If the deleted segment is the last segment, the replacement size is limited only by remaining memory.
> If not the last segment, the replacement must be equal or smaller.

### `:TRACe:DELete:ALL`

Delete all predefined segments and clear the entire waveform memory space.

> Particularly important for defragmenting the entire waveform memory.

### `:TRACe:POINts?`

Query the number of points used for the active waveform.

### `:TRACe:SELect<segment_#>(?)`

Set or query the active waveform segment at the output connector. Selecting a segment:
1. Successive `TRAC` commands will affect the selected segment.
2. The SYNC output will be assigned to the selected segment.

| Name | Range | Type | Default | Description |
|------|-------|------|---------|-------------|
| `<segment_#>` | 1 to 32,000 | Numeric (integer) | 1 | Active segment number |

### `:TRACe:SELect:SOURce{BUS|EXTernal}(?)`

Set or query the source of the segment select command.

- **BUS** (default): Segments switched only by remote command.
- **EXTernal**: Control transferred to rear panel connector (8-bit parallel, up to 256 segments).

### `:TRACe:SELect:TIMing{COHerent|IMMediate}(?)`

Set or query transition timing from waveform to waveform.

- **COHerent** (default): Current waveform completes before jumping to next.
- **IMMediate**: Current waveform is aborted; new waveform starts immediately.

### `SEGMent#<header><binary_block>`

Partition waveform memory using high-speed binary transfer.
Segment table data = 32-bit integers, 4 bytes per segment.

Example (3 segments):

```
SEGment#212<binary_block>
```

- `#` — start of binary block
- `2` — 2 digits follow
- `12` — 12 bytes (= 3 segments x 4 bytes)

**Notes:**
1. Each channel has its own segment table buffer. Select correct channel with `INST:SEL` first.
2. `SEGM#` command overrides segment definitions (similar to `TRAC:DEL:ALL`).
3. Segment count: 1 to 32,000.
4. Maximum segment size depends on installed option (basic: 16M).
5. Number of bytes must be divisible by 4.

**Combined download approach:**
When using `SEGM#`, you can download one combined waveform and then split with segment table.
Each segment after the first must have **32 dummy points** prepended (value = first point of that segment).

Example (3 segments: 400 + 3000 + 5000 points):
- Combined length: 400 + 3000 + 5000 + 64 (dummy) = 12,064 points
- Header: `TRACe#624128<binary_block>` (24128 = 12064 x 2 bytes)

---

## 4.13 Programming Considerations

### Data Types

The 81180A accepts four types of data from any remote interface:

1. **Commands** that set and program functions and parameters
2. **Queries** that interrogate current status or settings
3. **Waveform data** for arbitrary waveforms
4. **Table data** for sequences and memory segmentation

### Command Buffer

- SCPI commands are parsed in a few milliseconds.
- Input buffer size = **256 characters**.
- Command chains exceeding 256 characters may overload the buffer.

**Recommended practice** — send commands one at a time or in short strings:

```
Inst:sel 1
Func:mode user
trac:def 1,10240;def 2, 20480;def 3, 348; sel 1
volt 1.250;offs -0.350;:outp 1
Inst:sel 2
Func:mode user
trac:def 1,10240;def 2, 20480;def 3, 348; sel 1
volt 1.250;offs -0.350;:outp 1
```

### `*RST` Command

- Resets hundreds of settings; generator is not ready for commands until complete.
- Fixed delay of **1-2 seconds** is sufficient.
- Alternatively, use STB register to check readiness.

### Query Best Practice

Do not send multiple queries without pauses. Recommended pattern:

```
*sre16          (enable SRE on MAV bit)
Query?
ReadSTB         (wait until response is 16)
Read response
```

### Waveform Data Download

Two-phase process:

1. **Prepare** with ASCII SCPI commands (select/define segment)
2. **Download** waveform data in binary format

```
func:mode user
trac:sel 1
trac:def 1, 2048
```

> **Critical**: Do not mix control commands with waveform data transfer.
> Interrupting binary download will lock out the interface — only power cycling will recover.

The `trac#<data_array>` command has two parts:
1. **Header** — ASCII, tells generator how many bytes to expect (delimited by `#`)
2. **Waveform data** — binary, routed directly to arbitrary waveform memory

### Termination Characters

- **CR** (`\r`): Not required, ignored by 81180A.
- **NL** (`\n`): Recommended for all interfaces (USB, LAN, GPIB).
- Terminate commands with `\n` and expect responses terminated with `\n`.

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
                    // Enable the MAV bit in the Service Request Enable
                    // Register (SRE) of IEEE 488.2
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

                // Program instrument Parameters

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
                if (i < fDataPts.Length)
                {
                    if (fDiff == 0)
                        fDataPts[i] = 0.0f;
                    else
                        fDataPts[i] = ((fDataPts[i] - fMin) / fDiff * (1 * 2)) - 1;

                    dacValues[i] = (short)Math.Floor((fDataPts[i] * 2047) + 2048.5);
                }
                else
                    dacValues[i] = 2048;

                // Convert DAC Values to Bytes
                byte[] temp = new byte[2];
                temp = BitConverter.GetBytes(dacValues[i]);

                // SWAPPING OF BYTES
                bArray[cnt++] = temp[0];
                bArray[cnt++] = temp[1];
            }

            // Download data (binary block) using the WriteIEEEBlock method.
            // This is an extension method for FormattedIO488Class class and
            // is implemented in the IO488WriteIEEEBlockExtension class.
            fIO.WriteIEEEBlock(":TRACe:DATA ", bArray);
        }

        private Collection<float> calculateSinusoidWaveform(long lPoints,
        double dCycles, double dStartPhase)
        {
            double omega, phase, cycle;
            Collection<float> dataPoints = new Collection<float>();

            cycle = (double)(lPoints) / dCycles;

            // Calculate the start phase
            phase = (double)((double)(dStartPhase) * Math.PI / (double)180.0);

            // Calculate Omega
            omega = (double)(1.0 / lPoints * Math.PI * 2 * dCycles);

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
        private const long TIMEOUT = 8000; // 8s by default

        /// <summary>
        /// Query the MAV string
        /// </summary>
        public static string QueryString(this FormattedIO488Class io,
        string format, bool flushAndEND)
        {
            io.WriteString(format, flushAndEND);
            return ReadString(io, true);
        }

        /// <summary>
        /// Read the MAV string
        /// </summary>
        public static string ReadString(this FormattedIO488Class io,
        bool CheckMAVBit)
        {
            if (CheckMAVBit &&
                (io.IO.HardwareInterfaceName == "GPIB" ||
                io.IO.HardwareInterfaceName == "USB"))
            {
                short stb = 0;
                long endMilliseconds, startMilliseconds = DateTime.Now.Ticks /
                TimeSpan.TicksPerMillisecond;

                do
                {
                    endMilliseconds = DateTime.Now.Ticks /
                    TimeSpan.TicksPerMillisecond;
                    if ((endMilliseconds - startMilliseconds) > TIMEOUT)
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

        /// <summary>
        /// WriteIEEEBlock
        /// </summary>
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

                    // Make the binary block prefix
                    string Digits = String.Format("{0}", BinaryBlock.Length);
                    byte[] Header = ToByteArray(String.Format("{0} #{1}{2}",
                    Command, Digits.Length, Digits));

                    // Write prefix of binary block to formatted I/O write buffer
                    if (io.IO.Write(ref Header, Header.Length) == Header.Length)
                    {
                        byte[] Chunk = new byte[CHUNK_LENGTH];
                        int Length;

                        for (int Start = 0; Start < BinaryBlock.Length;
                        Start += Chunk.Length)
                        {
                            Length = Math.Min(Chunk.Length,
                                BinaryBlock.Length - Start);

                            System.Buffer.BlockCopy(BinaryBlock,
                            Start, Chunk, 0, Length);
                            if (io.IO.Write(ref Chunk, Length) != Length)
                            {
                                throw new Exception(
                                    "IO488WriteIEEEBlockExtension: "
                                    + "A buffer is not transmitted correctly");
                            }
                        }
                    }
                    else
                        throw new Exception(
                            "IO488WriteIEEEBlockExtension: "
                            + "A buffer is not transmitted correctly");
                }
                else
                    throw new Exception(
                        "IO488WriteIEEEBlockExtension: "
                        + "A device is not ready for the next command");
            }
            else if (io.IO.HardwareInterfaceName == "TCPIP")
            {
                io.WriteString("*OPC?\n", true);
                string answer = io.ReadString().TrimEnd('\n');

                if (answer.Equals(OPERATION_COMPLETED))
                    io.WriteIEEEBlock(Command, data, true);
                else
                    throw new Exception(
                        "IO488WriteIEEEBlockExtension: "
                        + "A device is not ready for the next command");
            }
            else
                io.WriteIEEEBlock(Command, data, true);
        }

        private static byte[] ToByteArray(string str)
        {
            System.Text.ASCIIEncoding enc = new System.Text.ASCIIEncoding();
            return enc.GetBytes(str);
        }
    }
}
```

### DAC 変換の要点

C# example の `SendDataToInstrument` メソッドにおける DAC 値変換:

1. 入力値を `-1.0` ~ `+1.0` の範囲に正規化:
   ```
   normalized = ((value - min) / (max - min) * 2) - 1
   ```
2. DAC 値 (0-4095) に変換:
   ```
   dacValue = Floor(normalized * 2047 + 2048.5)
   ```
   - `-1.0` → `Floor(-2047 + 2048.5)` = `Floor(1.5)` = **1** (≒ 最小)
   - `0.0` → `Floor(0 + 2048.5)` = **2048** (中点)
   - `+1.0` → `Floor(2047 + 2048.5)` = `Floor(4095.5)` = **4095** (最大)

3. バイトオーダー: **Little-endian** (low byte first)
   - `BitConverter.GetBytes()` は little-endian を返す
   - `bArray[cnt++] = temp[0]` (low byte), `bArray[cnt++] = temp[1]` (high byte)

### SCPI コマンド実行順序 (C# example から)

```
*RST                         // 機器リセット
*IDN?                        // 識別確認
:INST:SEL 1                  // チャンネル選択
:FUNC:MODE USER              // Arbitrary モード設定 (★ "ARB" ではない)
:FREQ:RAST 1.5E+08           // サンプルクロック設定
:VOLT 2                      // 振幅設定
:VOLT:OFFS 0                 // オフセット設定
:TRAC:DEL:ALL                // 全セグメント削除
:TRAC:DEF 1,<length>         // セグメント定義
:TRAC:SEL 1                  // セグメント選択
:TRACe:DATA <binary_block>   // 波形データダウンロード
:OUTP ON                     // 出力ON
```

> **重要**: `FUNCtion:MODE` の有効な引数は `FIXed | USER | SEQuence | ASEQuence | MODulation | PULSe` のみ。`ARB` は存在しない。
