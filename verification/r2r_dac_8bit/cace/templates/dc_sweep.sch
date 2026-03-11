v {xschem version=3.4.6 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {R-2R DAC 8-bit — CACE DC Sweep Template} 20 -200 0 0 0.3 0.3 {}
C {code_shown.sym} 20 -150 0 0 {name=MODELS only_toplevel=true
value=".lib cornerMOSlv.lib CACE\{corner\}
.lib cornerRES.lib res_typ
.lib cornerCAP.lib cap_typ
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
Vsub sub! 0 0

* Digital code input (swept 0-255 as a voltage)
Vcode code 0 0

* Bit extraction from code voltage
* Each bit = vdd_val * ( floor(code/2^n) mod 2 )
Bb7 d7 0 V = \{vdd_val\} * (floor(v(code)/128) - 2*floor(v(code)/256))
Bb6 d6 0 V = \{vdd_val\} * (floor(v(code)/64)  - 2*floor(v(code)/128))
Bb5 d5 0 V = \{vdd_val\} * (floor(v(code)/32)  - 2*floor(v(code)/64))
Bb4 d4 0 V = \{vdd_val\} * (floor(v(code)/16)  - 2*floor(v(code)/32))
Bb3 d3 0 V = \{vdd_val\} * (floor(v(code)/8)   - 2*floor(v(code)/16))
Bb2 d2 0 V = \{vdd_val\} * (floor(v(code)/4)   - 2*floor(v(code)/8))
Bb1 d1 0 V = \{vdd_val\} * (floor(v(code)/2)   - 2*floor(v(code)/4))
Bb0 d0 0 V = \{vdd_val\} * (floor(v(code)/1)   - 2*floor(v(code)/2))

* Output load
Rload vout 0 1meg

* DUT instantiation
Xdac d0 d1 d2 d3 d4 d5 d6 d7 vdd vout vss r2r_dac_8bit

* DC sweep: code 0 -> 255
.control
  dc Vcode 0 255 1
  wrdata CACE\{simpath\}/CACE\{filename\}_CACE\{N\}.data v(vout)
  quit
.endc

.end
"}
