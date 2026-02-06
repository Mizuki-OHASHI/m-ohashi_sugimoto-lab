import pyvisa
import time
import numpy as np
from matplotlib import pyplot as plt

# input here the VISA address of the M96.
Instr_VISA = ""
# in order to find the VISA address of your PXI SMU, see knowledge base article:
# https://support.keysight.com/KeysightdCX/s/knowledge-article-detail?keyid=How-Can-I-Send-SCPI-Commands-to-my-PXI-SMU-M96xxA

rm = pyvisa.ResourceManager()
instr = rm.open_resource(Instr_VISA)
instr.read_termination = "\n"  # type: ignore
instr.write_termination = "\n"  # type: ignore


def instrQ(cmd: str):
    return instr.query(cmd)  # type: ignore


def instrW(cmd: str):
    instr.write(cmd)  # type: ignore


IDinstru = instrQ("*IDN?")
print("IDinstru:", {IDinstru})

voltage_peak = 0.5  # [V]
trigger_count = 2  # 1 number of triggers for measurements to repeat
trigger_time = 0.01  # launches a trigger every 10ms
pulse_width = 0.001  # pulse width in second. here 1ms
pulse_delay = round(trigger_time / 2, 5)
# rounds at the 5th decimal the time at which to place the delay
# for the pulse w.r.t measurement trigger start.
# By default at half the wtrigger time
aperture_time = 0.0001  ### aperture impacts the measurement precision.
sampling_points = 20  ### sets the number of samples taken during the pulse sweep
# sampling_time = aperture_time * sampling_points

instrQ("*IDN?")
instrQ("SYST:ERR:COUN?")
instrW("*CLS")  ## clears the status byte register
instrW("SOUR1:WAIT:AUTO ON")  ## wait time for transient event, i.e. output event
instrW("SENS1:WAIT:AUTO ON")  ## wait time for measurement event
instrW("SOUR1:SWE:RANG BEST")
# sweep range sets automatically to cover the whole range
instrW("SOUR1:VOLT:RANG:AUTO ON")
# sets the voltage range automatically for the output signal
# instrW("SOUR1:CURR:RANG:AUTO ON")
instrW("SOUR1:FUNC PULS")  ## sets the pulse function
instrW("SOUR1:VOLT 0")  ## sets the base voltage of the peak
# instrW("SOUR1:CURR 0")


instrW(f"SOUR1:VOLT:TRIG {str(voltage_peak)}")  ## sets the voltage of the peak

instrW(f"SOUR1:PULS:DEL {str(pulse_delay)}")
# sets the delay for the pulse from trigger

instrW(f"SOUR1:PULS:WIDT {str(pulse_width)}")
# sets the pulse width, in seconds

instrW("SENS1:CURR:PROT 0.1")  ## compliance current
# instrW("SENS1:VOLT:PROT 0.1") ## compliance voltage

instrW("SOUR1:FUNC:MODE VOLT")  ## sets ON the voltage sourcing mode
# instrW("SOUR1:FUNC:MODE CURR") ## sets ON the current sourcing mode

instrW(
    "SOUR1:VOLT:MODE FIX"
)  ## sets the voltage sourcing mode. Can be fixed, a list or a sweep.
# instrW("SOUR1:CURR:MODE FIX")

instrW("TRIG1:TRAN:DEL 0")  ## sets a 0 time delay between measurement and trigger

instrW("FORM REAL,64")  ## sets the format to binary format, double precision

instrW("FORM:BORD NORM")  ## sets the format of the output numbers for communication

instrW(
    "FORM:ELEM:SENS VOLT,CURR,TIME,SOUR"
)  ### the output order will ALWAYS be VOLT, CURR, RES, TIME, STAT, SOUR, RDV, or RTV
# includes whichever data you asked with the command, but in this order


instrW("SENS1:FUNC:OFF:ALL")  ## turns off all other functions for measurement

instrW('SENS1:FUNC:ON "VOLT"')  ## sets ON the voltage measurement

instrW("SENS1:VOLT:APER:AUTO OFF")  ## sets OFF the auto aperture time

instrW("SENS1:VOLT:APER {}".format(str(aperture_time)))  ## sets aperture time in s

instrW(
    "SENS1:VOLT:RANG:UPP {}".format(str(voltage_peak))
)  ## sets the expected measurement value, and sets the voltage measurement range accordingly

instrW("SENS1:VOLT:RANG:AUTO:LLIM MIN")  ###
# instrW("TRIG1:ACQ:DEL 0.0005") ## sets a delay in acquisition

instrW('SENS1:FUNC:ON "CURR"')  ## turns ON current measurement

instrW("SENS1:CURR:APER:AUTO OFF")  ## sets OFF the auto aperture time

instrW(
    "SENS1:CURR:APER {}".format(str(aperture_time))
)  ## sets the aperture time manually

instrW(
    "SENS1:CURR:RANG:UPP {}".format(str(voltage_peak / 50))
)  ## sets the expected measurement value, and sets the range accordingly.

instrW("SENS1:CURR:RANG:AUTO:LLIM 1e-3")  ###

### now ask the instrument to enter SAMPLING or also known as DIGITIZER mode
instrW("SENS1:FUNC:MODE SAMPling")

instrW(
    "SENS1:SAMP:POINts {}".format(str(sampling_points))
)  ### sets a  digitizer points measurement

# instrW("SENS1:SAMP:TIME {}".format(str(sampling_time)))  ## the sampling time is set accordingly automatically


instrW("SOUR1:FUNC:TRIG:CONT OFF")  ## turns oFF the continuous trigger mode

instrW("ARM1:ALL:COUN 1")  ## sets the number of ARM counts

instrW("ARM1:ALL:DEL 0")  ## turns the delay to 0 for the ARM

instrW("ARM1:ALL:SOUR AINT")  ## sets the ARM source to internal
instrW("ARM1:ALL:TIM MIN")  ## sets the ARM source to timer
instrW(
    "TRIG1:ALL:COUN {}".format(str(trigger_count))
)  ## sets the number of trigger count

instrW("TRIG1:ALL:SOUR TIM")  ## sets the trigger source to timer

instrW("TRIG1:ALL:TIM {}".format(str(trigger_time)))  ## sets the timer for the trigger

instrW("SOUR1:WAIT OFF")  ## used to calculate the sourcing offset time

instrW("SENS1:WAIT OFF")  ## used to calculate the measurement offset time

instrW("OUTP1:STAT ON")  ##  enables the source ouput

instrW("STAT:OPER:PTR 7020")  ## register operation

instrW("STAT:OPER:NTR 7020")  ## register operation

instrW("STAT:OPER:ENAB 7020")  ## register operation

instrW("*SRE 128")  ## register operation

instrW(
    "SYST:TIME:TIM:COUN:RES:AUTO ON"
)  ## automatically resets the time counter when an INIT action occurs

instrW("SOUR1:VOLT 0")  ## sets the source voltage to 0
# instrW("SOUR1:CURR 0")

instrW(
    "SOUR1:VOLT:TRIG {}".format(str(voltage_peak))
)  ## sets the peak value of the output voltage
# instrW("SOUR1:CURR:TRIG {}".format(str(voltage_peak)))
instrQ("*OPC?")  ## allows synchronizing commands, asks if the operation is complete
instrW("INIT")  ## launches the sweep
instrQ("*OPC?")  ## allows synchronizing commands
values = instr.query_binary_values("SENS1:DATA?", datatype="d", is_big_endian=True)  # type: ignore
# binary values query is slightly faster

instrQ("*OPC?")  ## allows synchronizing

instrW("SOUR1:VOLT 0.0")  ## sets back the instrument to 0 output
instrW("SOUR1:CURR 0.0")  ## sets back the instrument to 0 output

instrW(
    "SENS1:VOLT:PROT 100e-6"
)  ## sets back the instrument to 0 output, extra protective layer
