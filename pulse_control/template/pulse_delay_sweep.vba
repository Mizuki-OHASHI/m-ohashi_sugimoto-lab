Sub ConnectionTest()

Dim rm As VisaComLib.ResourceManager
Dim awg As VisaComLib.FormattedIO488
Dim imsg As IMessage
Dim idname As String
Dim SICL As String

SICL = Range("C2")

Set rm = New VisaComLib.ResourceManager
Set awg = New VisaComLib.FormattedIO488
Set awg.IO = rm.Open(SICL)

Set imsg = awg.IO
imsg.TerminationCharacter = Asc(vbLf)
imsg.TerminationCharacterEnabled = True
awg.WriteString "*IDN?" & vbLf
idname = awg.ReadString()

Range("C3") = idname
Range("B3") = "Ú‘±’†"

MsgBox "Agilent81180A‚Æ’ÊMOK@ "

'awg.WriteString "*RST"
awg.IO.Close
Set awg = Nothing
Set rm = Nothing

End Sub
Sub SweepTau()

'’ÊMˆ—?
Dim rm As VisaComLib.ResourceManager
Dim awg As VisaComLib.FormattedIO488
Dim imsg As IMessage
Dim idname As String
Dim SICL As String

'’ÊMˆ—?
SICL = Range("C2")
Set rm = New VisaComLib.ResourceManager
Set awg = New VisaComLib.FormattedIO488
Set awg.IO = rm.Open(SICL)
Set imsg = awg.IO
imsg.TerminationCharacter = Asc(vbLf)
imsg.TerminationCharacterEnabled = True

'•Ï”’è‹`
Dim n As Long 'For`Next ƒ‹[ƒv‚ð‰ñ‚·ƒJƒEƒ“ƒ^
Dim i As Long 'For`Next ƒ‹[ƒv‚ð‰ñ‚·ƒJƒEƒ“ƒ^
Dim trgdly As Long 'ƒgƒŠƒKƒfƒBƒŒƒC‚Ì’lAƒ|ƒCƒ“ƒg”
Dim trgdly_step As Long '‡™ƒÑAƒ|ƒCƒ“ƒg”
Dim trgdly_int As Long 'ƒÑ‚Ì‰Šú’lAƒ|ƒCƒ“ƒg”
Dim wait As Single 'Sleep ŽžŠÔ’·@’PˆÊms
Dim step As Long 'Step”
Dim awg_2ch_v As Integer 'DCo—Í“dˆ³‚Ì•Ï”
Dim backward_on As Integer '‘|ˆø•ûŒüŒˆ’èƒpƒ‰ƒ[ƒ^
Dim keep_dly As String '‘|ˆøŒã‚ÌÝ’è”»’è
Dim sweep_num As Long

'CH2‚ðDCƒ‚[ƒh‚ÉØ‚è‘Ö‚¦‚é
awg.WriteString ":INST CH2"
awg.WriteString ":FUNCtion:SHAPe DC"
awg.WriteString ":INST CH1"

'ƒfƒBƒŒƒC‚Ì‰Šúó‘Ô•Û‘¶A‚¨‚æ‚Ñ‰Šú’lÝ’è
awg.WriteString ":TRIGger:DELay ?"
trgdly_int = awg.ReadString()

'‘|ˆøðŒŽæ“¾
backward_on = Range("I21")
keep_dly = Range("I22")
step = Range("D19")
wait = Range("D20")
trgdly_step = Range("D21")
sweep_num = Range("D26")

'ƒGƒ‰[ƒƒbƒZ[ƒW‚Ì•\Ž¦
If trgdly < 0 Or trgdly + trgdly_step * step < 0 Then
    MsgBox "‘ª’è‚Å‚«‚Ü‚¹‚ñ ! Trigger delay ‚Ì‰Šú’l,ÅI’l‚ð0ˆÈã‚É‚µ‚Ä‚­‚¾‚³‚¢ "
    End
End If

'ƒ‹[ƒv‚Åtau‚ð‘m‰@
For i = 1 To sweep_num
    trgdly = Range("D22")  'ƒgƒŠƒKƒfƒBƒŒƒC’l‚Ì‰Šú’l
    awg_2ch_v = 0 'DC“dˆ³‚Ì‰Šú’l
    'Forward‘|ˆø
    For n = 1 To step
        trgdly = trgdly + trgdly_step
        awg_2ch_v = awg_2ch_v + 1 / step
        Sleep (wait)
        awg.WriteString ":INST CH1"
        awg.WriteString ":TRIGger:DELay " & Str$(trgdly)
        awg.WriteString ":INST CH2"
        awg.WriteString "DC" & Str$(awg_2ch_v)
    Next n
    'Backward‘|ˆø
    If backward_on = 2 Then
        For n = 1 To step
            trgdly = trgdly - trgdly_step
            awg_2ch_v = awg_2ch_v - 1 / step
            Sleep (wait)
            awg.WriteString ":INST CH1"
            awg.WriteString ":TRIGger:DELay " & Str$(trgdly)
            awg.WriteString ":INST CH2"
            awg.WriteString "DC" & Str$(awg_2ch_v)
        Next n
    End If

Next i
Sleep (wait)  'I—¹Œã‘Ò‹@

'CH1I—¹ì‹Æ
awg.WriteString ":INST CH1"
Select Case keep_dly
    Case Is = False
        awg.WriteString ":TRIGger:DELay " & Str$(trgdly_int)
    Case Is = True
        awg.WriteString ":TRIGger:DELay " & Str$(trgdly)
        Range("D16") = trgdly
End Select
'CH2I—¹ì‹Æ
awg_2ch_v = 0
awg.WriteString ":INST CH2"
awg.WriteString "DC" & Str$(awg_2ch_v)

awg.WriteString ":INST CH1" '•Ö‹XãCH1‚É–ß‚µ‚Ä‚¨‚­

'awg.WriteString "*RST"
awg.IO.Close
Set awg = Nothing
Set rm = Nothing
End Sub
Sub UpdateSQR()

'’ÊMˆ—?
Dim rm As VisaComLib.ResourceManager
Dim awg As VisaComLib.FormattedIO488
Dim imsg As IMessage
Dim idname As String
Dim SICL As String

'’ÊMˆ—?
SICL = Range("C2")
Set rm = New VisaComLib.ResourceManager
Set awg = New VisaComLib.FormattedIO488
Set awg.IO = rm.Open(SICL)
Set imsg = awg.IO
imsg.TerminationCharacter = Asc(vbLf)
imsg.TerminationCharacterEnabled = True
awg.WriteString ":INST CH1"

'•Ï”’è‹`
Dim freq As Single 'frequency (Hz)
Dim sclk As Single 'sample clock (Sa/s)
Dim dcycle As Single 'Dcycle
Dim Vfb As Single
Dim Vp As Single
Dim ampl As Single 'pulse Amplitude (V)
Dim offs As Single 'pulse Offset (V)
Dim inv As String 'CH1 OutPut ‚Ì‹É«ON/OFF
Dim link_dc As String
Dim trglvl As String
Dim trgslp As String
Dim trgdly As String

'•Ï”Žæ“¾
freq = Range("D6")
dcycle = Range("D8")
Vfb = Range("D10")
Vp = Range("D11")
inv = Range("I8")
link_dc = Range("I9")
set_trgdly = Range("I10")
set_trglvl = Range("I11")
set_trgdly_at_Vp = Range("I12")

'Pulse‚ÌAmplitude‚ÆOffset‚ÉŠÖ‚·‚é•Ï”‚ðŽæ“¾(inv ON/OFFŽž)
If inv = "False" Then
    ampl = (Vp - Vfb) / 2
    offs = (Vp + Vfb) / 4
End If
If inv = "True" Then
    ampl = (-Vp + Vfb) / 2
    offs = (Vp + Vfb) / 4
End If

'CH1‚ðDCƒ‚[ƒh‚ÉØ‚è‘Ö‚¦‚é
'awg.WriteString ":INST CH1"
'awg.WriteString ":FUNCtion:SHAPe SQUare"

'•Ï”‚ðƒpƒ‹ƒX”­¶Ší‚Ö‘—M
awg.WriteString ":INST CH1"
awg.WriteString ":FREQuency" & freq
awg.WriteString ":SQUare:DCYCle" & dcycle
awg.WriteString ":VOLT:AMPLitude" & Str$(ampl)
awg.WriteString ":VOLT:OFFSet" & offs

'Trigger Delay‚ð•ÏX‚·‚éê‡‚Ì“®ì(Set Trigger Level‚Ìƒ`ƒFƒbƒNƒ{ƒbƒNƒX‚ªON‚Ì‚Æ‚«)
If set_trgdly = "True" Then
    trgdly = Range("D16")
    awg.WriteString "TRIGger:DELay" & trgdly
End If
'•Ï”Žæ“¾ƒgƒŠƒK[ƒfƒBƒŒƒC
awg.WriteString ":INST CH1"
awg.WriteString "TRIGger:DELay ?"
trgdly = awg.ReadString()

'Trigger Level‚ð•ÏX‚·‚éê‡‚Ì“®ì(Set Trigger Level‚Ìƒ`ƒFƒbƒNƒ{ƒbƒNƒX‚ªON‚Ì‚Æ‚«)
If set_trglvl = "True" Then
    trglvl = Range("D14")
    awg.WriteString "TRIGger:LEVel" & trglvl
End If
'•Ï”Žæ“¾ƒgƒŠƒK[ƒŒƒxƒ‹
awg.WriteString "TRIGger:LEVel ?"
trglvl = awg.ReadString()

'•Ï”Žæ“¾ƒgƒŠƒK[ƒXƒ[ƒv
awg.WriteString "TRIGger:SLOPe ?"
trgslp = awg.ReadString()


'•Ï”Žæ“¾ƒTƒ“ƒvƒ‹ƒNƒƒbƒN
awg.WriteString ":INST CH1"
awg.WriteString ":FREQuency:RASTer:FIX ?" 'standard mode‚Å‚ÌƒTƒ“ƒvƒ‹ƒŒ[ƒg“Ç‚Ýž‚Ý
sclk = awg.ReadString()
Range("D7") = sclk

'XVƒpƒ‰ƒ[ƒ^‚ð•\Ž¦
Range("D12") = ampl
Range("D13") = offs
Range("D14") = trglvl
Range("D15") = trgslp
Range("D16") = trgdly

'Link Trigger Delay to Vp Sweep‚ªOn‚Ì‚Æ‚«ASweep Vp‚Ìdelay‚à•ÏX
If set_trgdly_at_Vp = "True" Then
Range("D36") = trgdly
End If

If link_dc = True Then Range("M6") = Vfb

'ƒGƒ‰[ƒƒbƒZ[ƒW
If dcycle < 0.1 Or dcycle > 99.9 Then
    MsgBox "ƒGƒ‰[! Dcycle‚ðŒ©’¼‚µ‚Ä‚­‚¾‚³‚¢"
    End
End If
If ampl < 0.05 Or ampl > 2 Then
    MsgBox "ƒGƒ‰[! AmplitudeA‚Ü‚½‚ÍOut inv‚ðƒ`ƒFƒbƒN‚µ‚Ä‚­‚¾‚³‚¢"
    End
End If
If Abs(offs) > 1.5 Then
    MsgBox "ƒGƒ‰[! Offset‚ðŒ©’¼‚µ‚Ä‚­‚¾‚³‚¢"
    End
End If

awg.IO.Close
Set awg = Nothing
Set rm = Nothing

End Sub
Sub SweepVp()

'’ÊMˆ—?
Dim rm As VisaComLib.ResourceManager
Dim awg As VisaComLib.FormattedIO488
Dim imsg As IMessage
Dim idname As String
Dim SICL As String

'’ÊMˆ—?
SICL = Range("C2")
Set rm = New VisaComLib.ResourceManager
Set awg = New VisaComLib.FormattedIO488
Set awg.IO = rm.Open(SICL)
Set imsg = awg.IO
imsg.TerminationCharacter = Asc(vbLf)
imsg.TerminationCharacterEnabled = True

'•Ï”’è‹`
Dim n As Integer 'For`Next ƒ‹[ƒv‚ð‰ñ‚·ƒJƒEƒ“ƒ^
Dim i As Integer 'For`Next ƒ‹[ƒv‚ð‰ñ‚·ƒJƒEƒ“ƒ^
Dim backward_on As Integer '‰•œƒXƒLƒƒƒ“‚ð‚·‚é‚©‚Ç‚¤‚©‚Ì”»’è
Dim Vfb As Single 'Vfb
Dim Vp As Single 'Vp
Dim Vp_initial As Single 'Vp‰Šú’l
Dim Vp_final As Single  'VpÅI’l
Dim Vp_ItoF As Single 'Vp•Ï‰»‘—Ê
Dim Vp_step As Single 'ƒ¢VpAƒ|ƒCƒ“ƒg”
Dim step As Integer 'Step”
Dim wait As Single 'Sleep ŽžŠÔ’·@’PˆÊms
Dim wait_initial As Single '‰Šú‘Ò‹@ŽžŠÔ
Dim ampl_int As Single  '‘ª’è‘O‚ÌApmlitude
Dim offs_int As Single '‘ª’è‘O‚ÌOffset
Dim ampl As Single  'Apmlitude
Dim offs As Single 'Offset
Dim awg_2ch_v As Single 'DCo—Í“dˆ³‚Ì•Ï”
Dim inv As String 'invðŒ
Dim add_offs As Single '•â³€
Dim add_offs_step As Single  '•â³€ƒXƒeƒbƒv
Dim ch2_out_type As Integer 'ch2o—Í”»’è
Dim trgdly_int As Integer 'ƒgƒŠƒK[ƒfƒBƒŒƒC‰Šú’l
Dim trgdly As Integer 'ƒgƒŠƒK[ƒfƒBƒŒƒC
Dim sweep_num As Integer '‘|ˆø‰ñ”
Dim set_trgdly As String  'ƒgƒŠƒK[ƒfƒBƒŒƒCÝ’èON/OFF”»’è
Dim keep_trgdly As String  '‘ª’èŒã‚ÌƒgƒŠƒK[ƒfƒBƒŒƒCŒÅ’èON/OFF”»’è

'•Ï”Žæ“¾
inv = Range("I8")
ampl_int = Range("D12") 'amplitude‚Ì‰Šú’lA‘ª’èŒã‚ÌÝ’è’l‚ðŽæ“¾
offs_int = Range("D13") 'offset‚Ì‰Šú’lA‘ª’èŒã‚ÌÝ’è’l‚ðŽæ“¾
Vfb = Range("D29")  'V0‚ðŽæ“¾
Vp_initial = Range("D30")  'Vp-sweep‚Ì‰Šú’l‚ðŽæ“¾
Vp_final = Range("D31") 'Vp-sweepÅI’l‚ðŽæ“¾
Vp_ItoF = Vp_final - Vp_initial
wait_initial = Range("D32")
wait = Range("D33")
Vp_step = Range("D34") * Vp_ItoF / Abs(Vp_ItoF)
step = Abs(Vp_ItoF / Vp_step)
add_offs_step = Range("D35") / step
sweep_num = Range("D37")
ch2_out_type = Range("I31")
backward_on = Range("I32")
set_trgdly = Range("I33")
keep_trgdly = Range("I34")

'CH2‚ðDCƒ‚[ƒh‚ÉØ‚è‘Ö‚¦‚é
awg.WriteString ":INST CH2"
awg.WriteString ":FUNCtion:SHAPe DC"
awg.WriteString ":INST CH1"

'ƒgƒŠƒK[ƒfƒBƒŒƒC‚ÌÝ’è
awg.WriteString ":INST CH1"
awg.WriteString ":TRIGger:DELay ?"
trgdly_int = awg.ReadString()  'Œ³X‚ÌƒgƒŠƒK[ƒfƒBƒŒƒC‚Ì’l‚ðŠm•Û

If set_trgdly = True Then
    trgdly = Range("D36")
    awg.WriteString ":TRIGger:DELay " & Str$(trgdly)
    If keep_trgdly = True Then Range("D16") = trgdly
End If

'Vp‘|ˆø(ƒ‹[ƒv)invOFFŽž
If inv = "False" Then
    For i = 1 To sweep_num
        '‰Šúó‘Ô
        Vp = Vp_initial
        add_offs = 0
        ampl = (Vp - Vfb) / 2
        offs = (Vp + Vfb) / 4 + add_offs / 2
        If ch2_out_type = 1 Then awg_2ch_v = (2 * offs + ampl) / 2
        If ch2_out_type = 2 Then awg_2ch_v = ampl
        '‘•’u‚Öƒpƒ‰ƒ[ƒ^‘—M
        awg.WriteString ":INST CH1"
        awg.WriteString ":VOLT:AMPLitude" & Str$(ampl)
        awg.WriteString ":VOLT:OFFSet" & offs
        awg.WriteString ":INST CH2"
        awg.WriteString "DC" & awg_2ch_v
        Sleep (wait_initial) '‰Šú‘Ò‹@
      
        'forward sweep
        For n = 1 To step
            Vp = Vp + Vp_step
            add_offs = add_offs + add_offs_step
            ampl = (Vp - Vfb) / 2
            offs = (Vp + Vfb) / 4 + add_offs / 2
            If ch2_out_type = 1 Then awg_2ch_v = (2 * offs + ampl) / 2
            If ch2_out_type = 2 Then awg_2ch_v = ampl
            '‘•’u‚Öƒpƒ‰ƒ[ƒ^‘—M
            awg.WriteString ":INST CH1"
            awg.WriteString ":VOLT:AMPLitude" & Str$(ampl)
            awg.WriteString ":VOLT:OFFSet" & offs
            awg.WriteString ":INST CH2"
            awg.WriteString "DC" & awg_2ch_v
            Sleep (wait)
            'ƒGƒ‰[ƒƒbƒZ[ƒW
            If ampl < 0.05 Or ampl > 2 Then
                MsgBox "‘ª’è’†Ž~@Amplitude‚ªŒÀŠE’l‚ð’´‚¦‚Ü‚µ‚½"
                End
            End If
            If Abs(offs) > 1.5 Then
                MsgBox "‘ª’è’†Ž~@Offset‚ªŒÀŠE’l‚ð’´‚¦‚Ü‚µ‚½"
                End
            End If
            If Abs(awg_2ch_v) > 1.56 Then
                MsgBox "‘ª’è’†Ž~@DCo—Í‚Í3VˆÈ“à‚ÉÝ’è‚µ‚Ä‚­‚¾‚³‚¢"
                End
            End If
        Next n
        
       'backward sweep
        If backward_on = 2 Then
            For n = 1 To step
                Vp = Vp - Vp_step
                add_offs = add_offs - add_offs_step
                ampl = (Vp - Vfb) / 2
                offs = (Vp + Vfb) / 4 + add_offs / 2
                If ch2_out_type = 1 Then awg_2ch_v = (2 * offs + ampl) / 2
                If ch2_out_type = 2 Then awg_2ch_v = ampl
                '‘•’u‚Öƒpƒ‰ƒ[ƒ^‘—M
                awg.WriteString ":INST CH1"
                awg.WriteString ":VOLT:AMPLitude" & Str$(ampl)
                awg.WriteString ":VOLT:OFFSet" & offs
                awg.WriteString ":INST CH2"
                awg.WriteString "DC" & awg_2ch_v
                Sleep (wait)
            Next n
        End If
    Next i
End If

'Vp‘|ˆøinvONŽž
If inv = "True" Then
    For i = 1 To sweep_num
        '‰Šúó‘ÔÝ’è
        Vp = Vp_initial
        add_offs = 0
        ampl = (-Vp + Vfb) / 2
        offs = (Vp + Vfb) / 4 + add_offs / 2
        If ch2_out_type = 1 Then awg_2ch_v = (2 * offs - ampl) / 2
        If ch2_out_type = 2 Then awg_2ch_v = -ampl
        '‘•’u‚Öƒpƒ‰ƒ[ƒ^‘—M
        awg.WriteString ":INST CH1"
        awg.WriteString ":VOLT:AMPLitude" & Str$(ampl)
        awg.WriteString ":VOLT:OFFSet" & offs
        awg.WriteString ":INST CH2"
        awg.WriteString "DC" & awg_2ch_v
        Sleep (wait_initial) '‰Šú‘Ò‹@
        'forward sweep
        For n = 1 To step
            Vp = Vp + Vp_step
            add_offs = add_offs + add_offs_step
            ampl = (-Vp + Vfb) / 2
            offs = (Vp + Vfb) / 4 + add_offs / 2
            If ch2_out_type = 1 Then awg_2ch_v = (2 * offs - ampl) / 2
            If ch2_out_type = 2 Then awg_2ch_v = -ampl
            '‘•’u‚Öƒpƒ‰ƒ[ƒ^‘—M
            awg.WriteString ":INST CH1"
            awg.WriteString ":VOLT:AMPLitude" & Str$(ampl)
            awg.WriteString ":VOLT:OFFSet" & offs
            awg.WriteString ":INST CH2"
            awg.WriteString "DC" & awg_2ch_v
            Sleep (wait)
           
           'ƒGƒ‰[ƒƒbƒZ[ƒW
            If ampl < 0.05 Or ampl > 2 Then
                MsgBox "‘ª’è’†Ž~@Amplitude‚ªŒÀŠE’l‚ð’´‚¦‚Ü‚µ‚½"
                End
            End If
            If Abs(offs) > 1.5 Then
                MsgBox "‘ª’è’†Ž~@Offset‚ªŒÀŠE’l‚ð’´‚¦‚Ü‚µ‚½"
                End
            End If
            If Abs(awg_2ch_v) > 1.5 Then
                MsgBox "‘ª’è’†Ž~@DCo—Í‚Í3VˆÈ“à‚ÉÝ’è‚µ‚Ä‚­‚¾‚³‚¢"
                End
            End If
        Next n
        'backward sweep
        If backward_on = 2 Then
            For n = 1 To step
                Vp = Vp - Vp_step
                add_offs = add_offs - add_offs_step
                ampl = (-Vp + Vfb) / 2
                offs = (Vp + Vfb) / 4 + add_offs / 2
                If ch2_out_type = 1 Then awg_2ch_v = (2 * offs - ampl) / 2
                If ch2_out_type = 2 Then awg_2ch_v = -ampl
                '‘•’u‚Öƒpƒ‰ƒ[ƒ^‘—M
                awg.WriteString ":INST CH1"
                awg.WriteString ":VOLT:AMPLitude" & Str$(ampl)
                awg.WriteString ":VOLT:OFFSet" & offs
                awg.WriteString ":INST CH2"
                awg.WriteString "DC" & awg_2ch_v
                Sleep (wait)
           Next n
       End If
    Next i
End If

Sleep (wait) 'ˆ—Œã‘Ò‹@

'I—¹ì‹Æ(ƒgƒŠƒK[ƒfƒBƒŒƒC,CH1,CH2‚ðÝ’è)
awg.WriteString ":INST CH1"
If set_trgdly = True And keep_trgdly = False Then
    awg.WriteString ":TRIGger:DELay " & Str$(trgdly_int)
End If
awg.WriteString ":VOLT:AMPLitude" & ampl_int
awg.WriteString ":VOLT:OFFSet" & offs_int
awg_2ch_v = 0
awg.WriteString ":INST CH2"
awg.WriteString "DC" & Str$(awg_2ch_v)
awg.WriteString ":INST CH1" '•Ö‹XãCH1‚É–ß‚µ‚Ä‚¨‚­

awg.IO.Close
Set awg = Nothing
Set rm = Nothing
End Sub
Sub WaveForm()

'’ÊMˆ—?
Dim rm As VisaComLib.ResourceManager
Dim awg As VisaComLib.FormattedIO488
Dim imsg As IMessage
Dim idname As String
Dim SICL As String

'’ÊMˆ—?
SICL = Range("C2")
Set rm = New VisaComLib.ResourceManager
Set awg = New VisaComLib.FormattedIO488
Set awg.IO = rm.Open(SICL)
Set imsg = awg.IO
imsg.TerminationCharacter = Asc(vbLf)
imsg.TerminationCharacterEnabled = True

'•Ï”’è‹`
Dim sqr_active As String
Dim ampl As Single
Dim offs As Single
Dim Vdc As Single
Dim Vfb As Single

'•Ï”Žæ“¾
sqr_active = Range("D5")
ampl = Range("D12")
offs = Range("D13")
Vdc = Range("M6") / 2

'Square/DCØ‘Ö
awg.WriteString ":INST CH1"
Select Case sqr_active
Case ""
    awg.WriteString ":FUNCtion:SHAPe SQUare"
    awg.WriteString ":VOLT:AMPLitude" & ampl
    awg.WriteString ":VOLT:OFFSet" & offs
    Range("D5") = "Active"
    Range("M5").ClearContents
Case "Active"
    awg.WriteString ":FUNCtion:SHAPe DC"
    awg.WriteString ":DC:OFFSet" & Vdc
    Range("D5").ClearContents
    Range("M5") = "Active"
End Select

awg.IO.Close
Set awg = Nothing
Set rm = Nothing

End Sub
Sub ChangePorlarligy()

'’ÊMˆ—?
Dim rm As VisaComLib.ResourceManager
Dim awg As VisaComLib.FormattedIO488
Dim imsg As IMessage
Dim idname As String
Dim SICL As String

'’ÊMˆ—?
SICL = Range("C2")
Set rm = New VisaComLib.ResourceManager
Set awg = New VisaComLib.FormattedIO488
Set awg.IO = rm.Open(SICL)
Set imsg = awg.IO
imsg.TerminationCharacter = Asc(vbLf)
imsg.TerminationCharacterEnabled = True

'•Ï”’è‹`
Dim Vfb As Single
Dim Vp As Single
Dim Vfb_sweep As Double
Dim Vp_initial As Single
Dim Vp_final As Single
Dim add_offs As Single '•â³€
Dim inv As String 'OutPut inv‚Ìƒ`ƒFƒbƒNƒ{ƒbƒNƒX

'•Ï”Žæ“¾
Vfb = Range("D10")
Vp = Range("D11")
Vfb_sweep = Range("D29")
Vp_initial = Range("D30")
Vp_final = Range("D31")
add_offs = Range("D35")
inv = Range("I8")

'ƒpƒ‹ƒX‚Ì‹É«‚ð•Ï‚¦‚é
Vp = Vfb - (Vp - Vfb)
Vp_initial = Vfb_sweep - (Vp_initial - Vfb_sweep)
Vp_final = Vfb_sweep - (Vp_final - Vfb_sweep)
add_offs = -add_offs

'•\‹L
Range("D11") = Vp
Range("D30") = Vp_initial
Range("D31") = Vp_final
Range("D35") = add_offs

'Out inverse‚ÌØ‚è‘Ö‚¦
If inv = "True" Then Range("I8") = "False"
If inv = "False" Then Range("I8") = "True"

awg.IO.Close
Set awg = Nothing
Set rm = Nothing

End Sub
Sub UpdateDC()
'’ÊMˆ—?
Dim rm As VisaComLib.ResourceManager
Dim awg As VisaComLib.FormattedIO488
Dim imsg As IMessage
Dim idname As String
Dim SICL As String

'’ÊMˆ—?
SICL = Range("C2")
Set rm = New VisaComLib.ResourceManager
Set awg = New VisaComLib.FormattedIO488
Set awg.IO = rm.Open(SICL)
Set imsg = awg.IO
imsg.TerminationCharacter = Asc(vbLf)
imsg.TerminationCharacterEnabled = True

'•Ï”’è‹`
Dim Vdc As Single

'•Ï”Žæ“¾
Vdc = Range("M6") / 2

'ƒGƒ‰[ƒƒbƒZ[ƒW
If Abs(Vdc) > 1.5 Then
    MsgBox "ƒGƒ‰[! Vdc‚Í-3V`3V‚É‚µ‚Ä‚­‚¾‚³‚¢"
    End
End If

'•Ï”‚ðƒpƒ‹ƒX”­¶Ší‚Ö‘—M
awg.WriteString ":DC:OFFSet" & Vdc

awg.IO.Close
Set awg = Nothing
Set rm = Nothing
End Sub
Sub SweepVdc()

'’ÊMˆ—?
Dim rm As VisaComLib.ResourceManager
Dim awg As VisaComLib.FormattedIO488
Dim imsg As IMessage
Dim idname As String
Dim SICL As String

'’ÊMˆ—?
SICL = Range("C2")
Set rm = New VisaComLib.ResourceManager
Set awg = New VisaComLib.FormattedIO488
Set awg.IO = rm.Open(SICL)
Set imsg = awg.IO
imsg.TerminationCharacter = Asc(vbLf)
imsg.TerminationCharacterEnabled = True

'•Ï”’è‹`
Dim n As Integer 'For`Next ƒ‹[ƒv‚ð‰ñ‚·ƒJƒEƒ“ƒ^
Dim i As Integer 'For`Next ƒ‹[ƒv‚ð‰ñ‚·ƒJƒEƒ“ƒ^
Dim backward_on As Integer
Dim Vdc_int As Single
Dim Vdc As Single
Dim Vdc_initial As Single
Dim Vdc_final As Single
Dim Vdc_ItoF As Single
Dim Vdc_step As Single
Dim step As Integer
Dim wait_initial As Single
Dim wait As Single
Dim sweep_num As Integer
Dim awg_2ch_v_int As Single
Dim awg_2ch_v As Single

'•Ï”Žæ“¾
backward_on = Range("R13")
Vdc_int = Range("M6") / 2
awg_2ch_v_int = 0
Vdc_initial = Range("M10") / 2
Vdc_final = Range("M11") / 2
Vdc_ItoF = Vdc_final - Vdc_initial
Vdc_step = (Range("M12") / 2) * Vdc_ItoF / Abs(Vdc_ItoF) '‹É«‚àl—¶‚µ‚Ä‚¢‚é
wait_initial = Range("M13")
wait = Range("M14")
step = Abs(Vdc_ItoF / Vdc_step)
sweep_num = Range("M15")

'ƒGƒ‰[ƒƒbƒZ[ƒW
If Abs(Vdc_final) > 3 Or Abs(Vdc_initial) > 3 Then
    MsgBox "‘ª’è’†Ž~ Vdc initial‚ÆVdc final ‚Í3VˆÈ“à‚É‚µ‚Ä‚­‚¾‚³‚¢"
    End
End If

For i = 1 To sweep_num '‘|ˆø‰ñ”
    '‰ŠúðŒ
    Vdc = Vdc_initial
    awg_2ch_v = Vdc
    '‘•’u‚Öƒpƒ‰ƒ[ƒ^‘—M
    awg.WriteString ":INST CH1"
    awg.WriteString ":DC:OFFSet" & Vdc
    awg.WriteString ":INST CH2"
    awg.WriteString "DC" & awg_2ch_v
    Sleep (wait_initial) '‰Šú‘Ò‹@
    'Vdc‘|ˆø(ƒ‹[ƒv)
    For n = 1 To step
        Vdc = Vdc + Vdc_step
        awg_2ch_v = Vdc
        '‘•’u‚Öƒpƒ‰ƒ[ƒ^‘—M
        awg.WriteString ":INST CH1"
        awg.WriteString ":DC:OFFSet" & Vdc
        awg.WriteString ":INST CH2"
        awg.WriteString "DC" & awg_2ch_v
        Sleep (wait)
    Next n
    If backward_on = 2 Then
        For n = 1 To step
            Vdc = Vdc - Vdc_step
            awg_2ch_v = Vdc
            '‘•’u‚Öƒpƒ‰ƒ[ƒ^‘—M
            awg.WriteString ":INST CH1"
            awg.WriteString ":DC:OFFSet" & Vdc
            awg.WriteString ":INST CH2"
            awg.WriteString "DC" & awg_2ch_v
            Sleep (wait)
        Next n
    End If
Next i
Sleep (wait) 'ˆ—Œã‘Ò‹@

'I—¹ì‹Æ
awg.WriteString ":INST CH1"
awg.WriteString ":DC:OFFSet" & Vdc_int
awg.WriteString ":INST CH2"
awg.WriteString "DC" & awg_2ch_v_int
awg.WriteString ":INST CH1" '•Ö‹XãCH1‚É–ß‚µ‚Ä‚¨‚­

awg.IO.Close
Set awg = Nothing
Set rm = Nothing
End Sub
