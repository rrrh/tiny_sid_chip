# Analog Simulation Overview — Gnuplot Rendering
# Generates: waveform_440.png, waveform_880.png, svf_ac_response.png, r2r_transfer.png

# ============================================================
# Plot 1: 440Hz (A4) Waveform — Filter Bypass
# ============================================================
set terminal pngcairo size 1200,500 enhanced font 'Helvetica,12'
set output 'full_chain/waveform_440.png'

set title "440 Hz (A4) — DAC Output, Filter Bypassed" font ',14'
set xlabel "Time (ms)"
set ylabel "Voltage (V)"
set grid
set key top right

set xrange [0:7]
set yrange [0:1.3]

set style line 1 lc rgb '#2166ac' lw 2
set style line 2 lc rgb '#b2182b' lw 1.5 dt 2

# wrdata format: col1=time col2=dac_v col3=time col4=adc_v col5=time col6=code
plot 'full_chain/waveform_440.dat' using ($1*1000):2 with lines ls 1 title 'DAC analog out', \
     '' using ($3*1000):4 with lines ls 2 title 'ADC reconstructed'

# ============================================================
# Plot 2: 880Hz (A5) Waveform — Filter Bypass
# ============================================================
set output 'full_chain/waveform_880.png'

set title "880 Hz (A5) — DAC Output, Filter Bypassed" font ',14'

plot 'full_chain/waveform_880.dat' using ($1*1000):2 with lines ls 1 title 'DAC analog out', \
     '' using ($3*1000):4 with lines ls 2 title 'ADC reconstructed'

# ============================================================
# Plot 3: Combined 440+880Hz on one plot
# ============================================================
set output 'full_chain/waveform_440_880.png'
set terminal pngcairo size 1200,800 enhanced font 'Helvetica,12'

set multiplot layout 2,1 title "Audio Waveforms — Filter Bypass (DAC → ADC)" font ',16'

set title "440 Hz (A4)" font ',13'
set xlabel ""
set ylabel "Voltage (V)"
set xrange [0:7]
set yrange [0:1.3]
set grid

plot 'full_chain/waveform_440.dat' using ($1*1000):2 with lines ls 1 title 'DAC out', \
     '' using ($3*1000):4 with lines ls 2 title 'ADC recon'

set title "880 Hz (A5)" font ',13'
set xlabel "Time (ms)"

plot 'full_chain/waveform_880.dat' using ($1*1000):2 with lines ls 1 title 'DAC out', \
     '' using ($3*1000):4 with lines ls 2 title 'ADC recon'

unset multiplot

# ============================================================
# Plot 4: SVF AC Frequency Response (HP / BP / LP)
# ============================================================
set terminal pngcairo size 1200,600 enhanced font 'Helvetica,12'
set output 'svf/svf_ac_response.png'

set title "SVF Frequency Response (Audio Band, gm=5µA/V, C=800pF)" font ',14'
set xlabel "Frequency (Hz)"
set ylabel "Gain (dB, re: 0.1V_{AC})"
set grid
set key top right
set logscale x
set xrange [1:100000]
set yrange [-80:0]

set style line 1 lc rgb '#d6604d' lw 2.5
set style line 2 lc rgb '#2166ac' lw 2.5
set style line 3 lc rgb '#4daf4a' lw 2.5

# Mark audio frequencies
set arrow 1 from 440,-80 to 440,-20 nohead dt 3 lc rgb '#888888'
set arrow 2 from 880,-80 to 880,-20 nohead dt 3 lc rgb '#888888'
set label 1 "440Hz" at 460,-22 font ',9' tc rgb '#888888'
set label 2 "880Hz" at 920,-22 font ',9' tc rgb '#888888'

plot 'svf/svf_hp_ac.dat' using 1:2 with lines ls 1 title 'HP', \
     'svf/svf_bp_ac.dat' using 1:2 with lines ls 2 title 'BP (peak ~1.9kHz)', \
     'svf/svf_lp_ac.dat' using 1:2 with lines ls 3 title 'LP'

unset arrow 1
unset arrow 2
unset label 1
unset label 2
unset logscale x

# ============================================================
# Plot 5: R-2R DAC Transfer Function
# ============================================================
set output 'r2r_dac/r2r_dac_transfer.png'

set title "8-bit R-2R DAC Transfer Function (CMOS Switches, IHP SG13G2)" font ',14'
set xlabel "Digital Code"
set ylabel "Output Voltage (V)"
set grid
set key top left
set xrange [0:255]
set yrange [0:1.3]

set style line 1 lc rgb '#2166ac' lw 2 pt 7 ps 0.3

plot 'r2r_dac/r2r_dac_transfer.dat' using 1:2 with linespoints ls 1 title 'V_{out}', \
     x/255.0*1.2 with lines dt 2 lc rgb '#999999' lw 1 title 'Ideal (1.2·code/255)'

# ============================================================
# Plot 6: Full Chain with SVF (1kHz through BP filter)
# ============================================================
set output 'full_chain/full_chain_filtered.png'
set terminal pngcairo size 1200,600 enhanced font 'Helvetica,12'

set title "Full Chain: 1kHz Sine — DAC → SVF (BP) → ADC" font ',14'
set xlabel "Time (ms)"
set ylabel "Voltage (V)"
set grid
set key top right
set xrange [0:5]
set yrange [0:1.5]

set style line 1 lc rgb '#2166ac' lw 1.5
set style line 2 lc rgb '#d6604d' lw 2
set style line 3 lc rgb '#4daf4a' lw 1.5 dt 2

plot 'full_chain/full_chain_out.dat' using ($1*1000):2 with lines ls 1 title 'DAC out', \
     '' using ($3*1000):4 with lines ls 2 title 'SVF out (BP)', \
     '' using ($5*1000):6 with lines ls 3 title 'ADC recon'
