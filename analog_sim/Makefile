NGSPICE = /home/shue/.local/bin/ngspice -b
SIMS = r2r_dac bias_dac svf sar_adc full_chain

.PHONY: all $(SIMS) clean

all: $(SIMS)

r2r_dac:
	cd r2r_dac && $(NGSPICE) r2r_dac_tb.spice -o r2r_dac.log

bias_dac:
	cd bias_dac && $(NGSPICE) bias_dac_tb.spice -o bias_dac.log

svf:
	cd svf && $(NGSPICE) svf_tb.spice -o svf.log

sar_adc:
	cd sar_adc && $(NGSPICE) sar_adc_tb.spice -o sar_adc.log

full_chain:
	cd full_chain && $(NGSPICE) full_chain_tb.spice -o full_chain.log

clean:
	rm -f */*.log */*.raw */*.dat
