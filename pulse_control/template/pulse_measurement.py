# -*- coding: utf-8 -*-
"""
Created on Mon Feb  6 10:46:04 2023

@author: Kevin Rosenziveig
KTAS Engineer
"""
#### tests for connecting to M96 PXI SMU from Keysight over LAN and doing pulse sourcing, while measuring all the way through the pulse.
import pyvisa

# import time
import numpy as np
from matplotlib import pyplot as plt

Instr_VISA = ""  ### input here the VISA address of the M96.
# in order to find the VISA address of your PXI SMU, see knowledge base article:
# https://support.keysight.com/KeysightdCX/s/knowledge-article-detail?keyid=How-Can-I-Send-SCPI-Commands-to-my-PXI-SMU-M96xxA
rm = pyvisa.ResourceManager()
instr = rm.open_resource(Instr_VISA)
instr.read_termination = "\n"
instr.write_termination = "\n"
IDinstru = instr.query("*IDN?")
print("IDinstru:", {IDinstru})

### parameters for the pulse sweep
voltage_peak = 0.5  ## V
# current_peak = 0.5 ## A
trigger_count = 2  # number of triggers for measurements to repeat
trigger_time = 0.01  # launches a trigger every 10ms
pulse_width = 0.001  # pulse width in second. here 1ms
pulse_delay = round(
    trigger_time / 2, 5
)  ## rounds at the 5th decimal the time at which to place the delay for the pulse w.r.t measurement trigger start. By default at half the wtrigger time
aperture_time = 0.0001  ### aperture impacts the measurement precision.
sampling_points = 20  ### sets the number of samples taken during the pulse sweep
# sampling_time = aperture_time * sampling_points

instr.query("*IDN?")

instr.query("SYST:ERR:COUN?")

instr.write("*CLS")  ## clears the status byte register

instr.write("SOUR1:WAIT:AUTO ON")  ## wait time for transient event, i.e. output event

instr.write("SENS1:WAIT:AUTO ON")  ## wait time for measurement event

instr.write(
    "SOUR1:SWE:RANG BEST"
)  ## sweep range sets automatically to cover the whole range

instr.write(
    "SOUR1:VOLT:RANG:AUTO ON"
)  ## sets the voltage range automatically for the output signal
# instr.write("SOUR1:CURR:RANG:AUTO ON")

instr.write("SOUR1:FUNC PULS")  ## sets the pulse function

instr.write("SOUR1:VOLT 0")  ## sets the base voltage of the peak
# instr.write("SOUR1:CURR 0")

instr.write(
    "SOUR1:VOLT:TRIG {}".format(str(voltage_peak))
)  ## sets the voltage of the peak
# instr.write("SOUR1:CURR:TRIG {}".format(str(current_peak)))

instr.write(
    "SOUR1:PULS:DEL {}".format(str(pulse_delay))
)  ## sets the delay for the pulse from trigger

instr.write(
    "SOUR1:PULS:WIDT {}".format(str(pulse_width))
)  ## sets the pulse width, in seconds

instr.write("SENS1:CURR:PROT 0.1")  ## compliance current
# instr.write("SENS1:VOLT:PROT 0.1") ## compliance voltage

instr.write("SOUR1:FUNC:MODE VOLT")  ## sets ON the voltage sourcing mode
# instr.write("SOUR1:FUNC:MODE CURR") ## sets ON the current sourcing mode

instr.write(
    "SOUR1:VOLT:MODE FIX"
)  ## sets the voltage sourcing mode. Can be fixed, a list or a sweep.
# instr.write("SOUR1:CURR:MODE FIX")

instr.write("TRIG1:TRAN:DEL 0")  ## sets a 0 time delay between measurement and trigger

instr.write("FORM REAL,64")  ## sets the format to binary format, double precision

instr.write(
    "FORM:BORD NORM"
)  ## sets the format of the output numbers for communication

instr.write(
    "FORM:ELEM:SENS VOLT,CURR,TIME,SOUR"
)  ### the output order will ALWAYS be VOLT, CURR, RES, TIME, STAT, SOUR, RDV, or RTV
# includes whichever data you asked with the command, but in this order


instr.write("SENS1:FUNC:OFF:ALL")  ## turns off all other functions for measurement

instr.write('SENS1:FUNC:ON "VOLT"')  ## sets ON the voltage measurement

instr.write("SENS1:VOLT:APER:AUTO OFF")  ## sets OFF the auto aperture time

instr.write("SENS1:VOLT:APER {}".format(str(aperture_time)))  ## sets aperture time in s

instr.write(
    "SENS1:VOLT:RANG:UPP {}".format(str(voltage_peak))
)  ## sets the expected measurement value, and sets the voltage measurement range accordingly

instr.write("SENS1:VOLT:RANG:AUTO:LLIM MIN")  ###
# instr.write("TRIG1:ACQ:DEL 0.0005") ## sets a delay in acquisition

instr.write('SENS1:FUNC:ON "CURR"')  ## turns ON current measurement

instr.write("SENS1:CURR:APER:AUTO OFF")  ## sets OFF the auto aperture time

instr.write(
    "SENS1:CURR:APER {}".format(str(aperture_time))
)  ## sets the aperture time manually

instr.write(
    "SENS1:CURR:RANG:UPP {}".format(str(voltage_peak / 50))
)  ## sets the expected measurement value, and sets the range accordingly.

instr.write("SENS1:CURR:RANG:AUTO:LLIM 1e-3")  ###

### now ask the instrument to enter SAMPLING or also known as DIGITIZER mode
instr.write("SENS1:FUNC:MODE SAMPling")

instr.write(
    "SENS1:SAMP:POINts {}".format(str(sampling_points))
)  ### sets a  digitizer points measurement

# instr.write("SENS1:SAMP:TIME {}".format(str(sampling_time)))  ## the sampling time is set accordingly automatically


instr.write("SOUR1:FUNC:TRIG:CONT OFF")  ## turns oFF the continuous trigger mode

instr.write("ARM1:ALL:COUN 1")  ## sets the number of ARM counts

instr.write("ARM1:ALL:DEL 0")  ## turns the delay to 0 for the ARM

instr.write("ARM1:ALL:SOUR AINT")  ## sets the ARM source to internal
instr.write("ARM1:ALL:TIM MIN")  ## sets the ARM source to timer
instr.write(
    "TRIG1:ALL:COUN {}".format(str(trigger_count))
)  ## sets the number of trigger count

instr.write("TRIG1:ALL:SOUR TIM")  ## sets the trigger source to timer

instr.write(
    "TRIG1:ALL:TIM {}".format(str(trigger_time))
)  ## sets the timer for the trigger

instr.write("SOUR1:WAIT OFF")  ## used to calculate the sourcing offset time

instr.write("SENS1:WAIT OFF")  ## used to calculate the measurement offset time

instr.write("OUTP1:STAT ON")  ##  enables the source ouput

instr.write("STAT:OPER:PTR 7020")  ## register operation

instr.write("STAT:OPER:NTR 7020")  ## register operation

instr.write("STAT:OPER:ENAB 7020")  ## register operation

instr.write("*SRE 128")  ## register operation

instr.write(
    "SYST:TIME:TIM:COUN:RES:AUTO ON"
)  ## automatically resets the time counter when an INIT action occurs

instr.write("SOUR1:VOLT 0")  ## sets the source voltage to 0
# instr.write("SOUR1:CURR 0")

instr.write(
    "SOUR1:VOLT:TRIG {}".format(str(voltage_peak))
)  ## sets the peak value of the output voltage
# instr.write("SOUR1:CURR:TRIG {}".format(str(voltage_peak)))
instr.query(
    "*OPC?"
)  ## allows synchronizing commands, asks if the operation is complete
instr.write("INIT")  ## launches the sweep
instr.query("*OPC?")  ## allows synchronizing commands
values = instr.query_binary_values(
    "SENS1:DATA?", datatype="d", is_big_endian=True
)  ## binary values query is slightly faster

instr.query("*OPC?")  ## allows synchronizing

instr.write("SOUR1:VOLT 0.0")  ## sets back the instrument to 0 output
instr.write("SOUR1:CURR 0.0")  ## sets back the instrument to 0 output

instr.write(
    "SENS1:VOLT:PROT 100e-6"
)  ## sets back the instrument to 0 output, extra protective layer

############ data processing

values = np.array(
    values, dtype="float"
)  ## sets a numpy array made from the list obtained from the measurement
timestamps = np.zeros(
    sampling_points * trigger_count
)  ## timestamp numpy array with measurement times
meas_volt = np.zeros(
    sampling_points * trigger_count
)  ## voltages numpy array with measured voltage
meas_curr = np.zeros(
    sampling_points * trigger_count
)  ## current numpy array with measured currents
source_volt = np.zeros(
    sampling_points * trigger_count
)  ## voltage numpy array with set voltages
### the output order will ALWAYS be
# VOLT, CURR, RES, TIME, STAT, SOUR, RDV, or RTV
# so, asking for 4 parameters here, we fill the array like so:
for n in range(sampling_points * trigger_count):
    timestamps[n] = values[4 * n + 2]
    meas_volt[n] = values[4 * n]
    meas_curr[n] = values[4 * n + 1]
    source_volt = values[4 * n + 3]

figure, axes1 = plt.subplots()  ## gets the figure and axes objects
plotmeasvolt = axes1.plot(
    timestamps, meas_volt, label="meas. volt"
)  ## plots the measured voltage against time
axes2 = axes1.twinx()  ## creates a twin X axis to plot on another Y axis
axes2._get_lines.prop_cycler = (
    axes1._get_lines.prop_cycler
)  ## insures the color cycle is the same for new axes object
plotmeascurr = axes2.plot(
    timestamps, meas_curr, label="meas. curr"
)  ## plots the measured current
allplots = plotmeasvolt + plotmeascurr  ## allows retrieving the labels
labs = [l.get_label() for l in allplots]  ## retrieves labels
axes2.legend(allplots, labs, loc=0)  ## places the labels
plt.tight_layout()  ## sortens the plot
