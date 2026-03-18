v {xschem version=3.4.6 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {PWM Comparator — CACE DC Transfer Template} 20 -200 0 0 0.3 0.3 {}
C {code_shown.sym} 20 -150 0 0 {name=MODELS only_toplevel=true
value=".lib cornerMOSlv.lib CACE\{corner\}
"}
C {code_shown.sym} 20 -80 0 0 {name=SIMULATION only_toplevel=true
value="
* DUT netlist
.include CACE\{DUT_path\}

* Parameters
.param vdd_val = CACE\{vdd\}

* Temperature
.temp CACE\{temperature\}

* Power supplies
Vdd  vdd 0 \{vdd_val\}
Vss  vss 0 0

* Input: sweep Vinp, hold Vinn at mid-rail
Vvinp vinp 0 0
Vvinn vinn 0 \{vdd_val/2\}

* Output load
Rload out 0 1meg

* DUT instantiation
Xcomp vinp vinn out vdd vss pwm_comp

* DC sweep: Vinp from 0 to VDD, 5mV steps
.control
  dc Vvinp 0 CACE\{vdd\} 0.005
  wrdata CACE\{simpath\}/CACE\{filename\}_CACE\{N\}.data v(out)
  quit
.endc

.end
"}
