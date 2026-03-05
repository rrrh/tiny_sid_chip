// Verilator C++ testbench for Monty on the Run full-length simulation
// Replaces monty_full_tb.v — typically 10-50x faster than Icarus Verilog.
//
// Drives SID register writes from stimulus file, captures PWM-decimated
// output at ~44.1 kHz (24 MHz / 544).

#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include "Vtt_um_sid.h"
#include "verilated.h"

// 24 MHz clock → 41.667 ns period (we count in half-periods for toggle)
static const int DECIM = 544;

// ── SID address remapping ────────────────────────────────────────────────
// Map flat SID address (0x00–0x18) → {voice_sel[1:0], reg_addr[2:0]}
// Remap per-voice: SID reg 4→6, 5→4, 6→5 (waveform/ADSR nibble swap)
// Global regs 21-24 → voice 3, regs 0-3
static bool sid_remap(int sid_addr, int &voice, int &reg_addr) {
    int voice_offset;
    if (sid_addr < 7) {
        voice = 0; voice_offset = sid_addr;
    } else if (sid_addr < 14) {
        voice = 1; voice_offset = sid_addr - 7;
    } else if (sid_addr < 21) {
        voice = 2; voice_offset = sid_addr - 14;
    } else if (sid_addr <= 24) {
        voice = 3; voice_offset = sid_addr - 21;
        reg_addr = voice_offset;
        return true;
    } else {
        return false;  // skip
    }

    // Per-voice register remap
    switch (voice_offset) {
        case 4: reg_addr = 6; break;  // SID ctrl/waveform → reg 6
        case 5: reg_addr = 4; break;  // SID attack/decay  → reg 4
        case 6: reg_addr = 5; break;  // SID sustain/rel   → reg 5
        default: reg_addr = voice_offset; break;
    }
    return true;
}

// ── Clock tick helper ────────────────────────────────────────────────────
static uint64_t sim_time = 0;

static void tick(Vtt_um_sid *dut) {
    dut->clk = 0;
    dut->eval();
    sim_time++;
    dut->clk = 1;
    dut->eval();
    sim_time++;
}

// ── 3-clock SID register write protocol ──────────────────────────────────
// Clock 1: set addr+data, Clock 2: WE=1, Clock 3: WE=0
static void sid_write(Vtt_um_sid *dut, int voice, int reg_addr, int data) {
    // ui_in = {WE, 2'b00, voice[1:0], reg_addr[2:0]}
    dut->ui_in  = (0 << 7) | (voice << 3) | reg_addr;
    dut->uio_in = data & 0xFF;
    tick(dut);

    dut->ui_in = (1 << 7) | (voice << 3) | reg_addr;  // WE rising
    tick(dut);

    dut->ui_in = (0 << 7) | (voice << 3) | reg_addr;  // WE falling
    tick(dut);
}

// ── Main ─────────────────────────────────────────────────────────────────
int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);

    const char *stim_path = "tests/monty_full_stim.txt";
    const char *raw_path  = "tests/monty_full_pwm_vl.raw";
    if (argc > 1) stim_path = argv[1];
    if (argc > 2) raw_path  = argv[2];

    Vtt_um_sid *dut = new Vtt_um_sid;

    // Open output file
    FILE *fout = fopen(raw_path, "w");
    if (!fout) { fprintf(stderr, "Cannot open %s\n", raw_path); return 1; }

    // Reset sequence: 100 clocks with rst_n=0
    dut->ena   = 1;
    dut->rst_n = 0;
    dut->ui_in = 0;
    dut->uio_in = 0;
    for (int i = 0; i < 100; i++) tick(dut);

    dut->rst_n = 1;
    for (int i = 0; i < 50; i++) tick(dut);

    // Open stimulus file
    FILE *fstim = fopen(stim_path, "r");
    if (!fstim) { fprintf(stderr, "Cannot open %s\n", stim_path); return 1; }

    printf("Starting Monty on the Run full simulation (Verilator)...\n");

    // PWM decimation state
    int decim_cnt    = 0;
    int pwm_high_cnt = 0;
    long sample_count = 0;

    // Read all stimulus events into memory for fast access
    struct StimEvent { uint64_t tick; int addr; int data; };
    int stim_cap = 100000;
    int stim_count = 0;
    StimEvent *events = (StimEvent *)malloc(stim_cap * sizeof(StimEvent));

    {
        double tick_r;
        int addr_i, data_i;
        while (fscanf(fstim, "%lf %d %d", &tick_r, &addr_i, &data_i) == 3) {
            if (stim_count >= stim_cap) {
                stim_cap *= 2;
                events = (StimEvent *)realloc(events, stim_cap * sizeof(StimEvent));
            }
            events[stim_count].tick = (uint64_t)(tick_r * 20.0);  // convert to ns
            events[stim_count].addr = addr_i;
            events[stim_count].data = data_i;
            stim_count++;
        }
    }
    fclose(fstim);
    printf("  Loaded %d stimulus events\n", stim_count);

    // Each tick() call = 1 clock cycle, sim_time increments by 2 per tick.
    // We track wall-clock in units of clock cycles (sim_time/2).
    // Stimulus ticks are in ns; 1 clock = 41.667 ns (24 MHz).
    // Convert ns target to clock-cycle count: ns / 41.667 ≈ ns * 24 / 1000
    // More precisely: clk_cycle = ns * 24e6 / 1e9 = ns * 0.024

    int event_idx = 0;
    long clk_count = 150;  // already did 100 + 50 clocks

    // Compute last event time + 1 second tail in clock cycles
    uint64_t last_event_ns = (stim_count > 0) ? events[stim_count - 1].tick : 0;
    uint64_t tail_ns = 1000000000ULL;  // 1 second
    uint64_t end_ns = last_event_ns + tail_ns;
    long end_clk = (long)((double)end_ns * 0.024);

    printf("  Last event at %.3f s, running until %.3f s (%ld clocks)\n",
           last_event_ns / 1e9, end_ns / 1e9, end_clk);

    while (clk_count < end_clk) {
        // Check if next stimulus event should fire
        if (event_idx < stim_count) {
            long event_clk = (long)((double)events[event_idx].tick * 0.024);
            if (clk_count >= event_clk) {
                int voice, reg_addr;
                if (sid_remap(events[event_idx].addr, voice, reg_addr)) {
                    sid_write(dut, voice, reg_addr, events[event_idx].data);
                    clk_count += 3;  // sid_write uses 3 ticks
                }
                event_idx++;

                // Progress report every 5000 events
                if (event_idx % 5000 == 0) {
                    double secs = (double)clk_count / 24e6;
                    printf("  T=%.3f s: %d/%d events, %ld samples\n",
                           secs, event_idx, stim_count, sample_count);
                }
                continue;  // re-check for back-to-back events at same time
            }
        }

        // Normal clock tick
        tick(dut);
        clk_count++;

        // PWM decimation
        if (dut->uo_out & 1) pwm_high_cnt++;
        decim_cnt++;
        if (decim_cnt >= DECIM) {
            fprintf(fout, "%d\n", pwm_high_cnt);
            sample_count++;
            decim_cnt = 0;
            pwm_high_cnt = 0;
        }
    }

    fclose(fout);
    free(events);

    printf("Simulation complete: %d events, %ld samples (%.2f s at 44117 Hz)\n",
           stim_count, sample_count, (double)sample_count / 44117.0);
    printf("Output: %s\n", raw_path);

    delete dut;
    return 0;
}
