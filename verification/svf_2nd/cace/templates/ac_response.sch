v {xschem version=3.4.6 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {SVF 2nd-Order \u2014 CACE AC Response Template} 20 -200 0 0 0.3 0.3 {}
C {code_shown.sym} 20 -150 0 0 {name=SIMULATION only_toplevel=true
value="
* DUT (behavioral CT equivalent)
.include CACE\{DUT_path\}

* SC design parameters
.param vdd_val = CACE\{vdd\}
.param f_clk = CACE\{f_clk\}
.param q_code = CACE\{q_code\}
.param c_sw = 73.5e-15
.param c_q_unit = 73.5e-15
.param r_eff = \{1/(f_clk*c_sw)\}
.param c_q = \{q_code*c_q_unit\}
.param r_q = \{1/(f_clk*c_q)\}

* Power supplies
Vdd  vdd 0 \{vdd_val\}
Vss  vss 0 0

* Input: DC bias + 1V AC stimulus
Vin  vin 0 dc 0.6 ac 1

* Mux control
Vsel0 sel0 0 CACE\{sel0\}
Vsel1 sel1 0 CACE\{sel1\}

* Output load
Rload vout 0 1meg

* DUT instantiation
Xsvf vin vout sel1 sel0 vdd vss svf_2nd r_eff_val=\{r_eff\} r_q_val=\{r_q\}

* AC analysis: 1 Hz to 1 MHz, 50 pts/decade
.control
  ac dec 50 1 1e6
  wrdata CACE\{simpath\}/CACE\{filename\}_CACE\{N\}.data v(vout)
  quit
.endc

.end
"}
