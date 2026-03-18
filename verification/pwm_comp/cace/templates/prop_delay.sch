v {xschem version=3.4.6 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {PWM Comparator — CACE Propagation Delay Template} 20 -200 0 0 0.3 0.3 {}
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

* Input: Vinn at mid-rail
Vvinn vinn 0 \{vdd_val/2\}

* Vinp: two fast step transitions to measure tPLH and tPHL
* Start low (0.2V), step up to 1.0V at 50ns (rising crossing),
* step back down at 200ns (falling crossing). 1ns transitions.
Vvinp vinp 0 PWL(0 0.2 49n 0.2 50n 1.0 199n 1.0 200n 0.2 400n 0.2)

* Output load
Cload out 0 10f
Rload out 0 1meg

* DUT instantiation
Xcomp vinp vinn out vdd vss pwm_comp

* Transient: 400ns
.control
  tran 0.05n 400n
  wrdata CACE\{simpath\}/CACE\{filename\}_CACE\{N\}.data v(vinp) v(out)
  quit
.endc

.end
"}
