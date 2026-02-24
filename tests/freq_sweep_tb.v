`timescale 1ns / 1ps
//==============================================================================
// Frequency Sweep Testbench — Gate-Level Compatible
// Sweeps sawtooth through multiple frequencies, captures PWM as PWL file
// for analog filter simulation.
//
// Usage (RTL):
//   iverilog -o tests/freq_sweep -g2005-sv src/tt_um_sid.v src/filter.v \
//     src/SVF_8bit.v src/pwm_audio.v tests/freq_sweep_tb.v
//   vvp tests/freq_sweep
//
// Usage (GL):
//   iverilog -o tests/freq_sweep_gl -g2012 -DGL_TEST -DFUNCTIONAL \
//     -I src patched_stdcell.v gate_level_netlist.v tests/freq_sweep_tb.v
//   vvp tests/freq_sweep_gl
//==============================================================================
module freq_sweep_tb;

    // --- Parameters ---
    localparam real VDD     = 3.3;
    localparam real EDGE_NS = 2.0;

`ifdef GL_TEST
    // GL: lighter sweep (~120ms sim time, ~25 min wall clock)
    localparam STEP_CYCLES  = 120_000;  // ~10 ms per step
    localparam ATTACK_WAIT  = 120_000;  // ~10 ms
`else
    // RTL: full sweep (~3.1s sim time)
    localparam STEP_CYCLES  = 3_000_000;  // ~250 ms per step
    localparam ATTACK_WAIT  = 200_000;    // ~17 ms
`endif
    localparam NUM_STEPS    = 12;

    // --- Clock and DUT ---
    reg clk;
    initial clk = 0;
    always #42 clk = ~clk;  // ~12 MHz (83.33 ns period)

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    wire pwm_out = uo_out[0];

    // Register addresses
    localparam [2:0] REG_FREQ_LO  = 3'd0,
                     REG_FREQ_HI  = 3'd1,
                     REG_PW_LO    = 3'd2,
                     REG_PW_HI    = 3'd3,
                     REG_ATK      = 3'd4,
                     REG_SUS      = 3'd5,
                     REG_WAV      = 3'd6;
    localparam [2:0] REG_FC_LO    = 3'd0,
                     REG_FC_HI    = 3'd1,
                     REG_RES_FILT = 3'd2,
                     REG_MODE_VOL = 3'd3;
    localparam [1:0] VOICE_FILT   = 2'd3;

    // Frequency table: 12 steps from ~110 Hz (A2) to ~2093 Hz (C7)
    // freq_reg = f_hz * 65536 / 800000
    reg [7:0] freq_table [0:11];
    initial begin
        freq_table[ 0] = 8'd9;    // ~110 Hz (A2)
        freq_table[ 1] = 8'd11;   // ~131 Hz (C3)
        freq_table[ 2] = 8'd14;   // ~165 Hz (E3)
        freq_table[ 3] = 8'd18;   // ~220 Hz (A3)
        freq_table[ 4] = 8'd27;   // ~330 Hz (E4)
        freq_table[ 5] = 8'd36;   // ~440 Hz (A4)
        freq_table[ 6] = 8'd54;   // ~659 Hz (E5)
        freq_table[ 7] = 8'd72;   // ~880 Hz (A5)
        freq_table[ 8] = 8'd86;   // ~1047 Hz (C6)
        freq_table[ 9] = 8'd108;  // ~1319 Hz (E6)
        freq_table[10] = 8'd144;  // ~1760 Hz (A6)
        freq_table[11] = 8'd172;  // ~2093 Hz (C7)
    end

    //==========================================================================
    // Register write task
    //==========================================================================
    task sid_write;
        input [2:0] addr;
        input [7:0] data;
        input [1:0] voice;
        begin
            @(negedge clk);
            ui_in  = {1'b0, 2'b00, voice, addr};
            uio_in = data;
            @(negedge clk);
            ui_in[7] = 1'b1;
            @(negedge clk);
            @(negedge clk);
            ui_in[7] = 1'b0;
            @(negedge clk);
        end
    endtask

    //==========================================================================
    // PWL capture
    //==========================================================================
    integer pwl_fd;
    reg     prev_pwm;

    task pwl_open;
        input [255:0] filename;
        begin
            pwl_fd = $fopen(filename, "w");
            if (pwl_fd == 0) begin
                $display("ERROR: Cannot open %0s", filename);
                $finish;
            end
            prev_pwm = pwm_out;
            if (prev_pwm)
                $fwrite(pwl_fd, "0n %0.3f\n", VDD);
            else
                $fwrite(pwl_fd, "0n 0\n");
        end
    endtask

    task pwl_sample;
        begin
            if (pwm_out !== prev_pwm) begin
                if (pwm_out) begin
                    $fwrite(pwl_fd, "%0.1fn 0\n",   $realtime);
                    $fwrite(pwl_fd, "%0.1fn %0.3f\n", $realtime + EDGE_NS, VDD);
                end else begin
                    $fwrite(pwl_fd, "%0.1fn %0.3f\n", $realtime, VDD);
                    $fwrite(pwl_fd, "%0.1fn 0\n",     $realtime + EDGE_NS);
                end
                prev_pwm = pwm_out;
            end
        end
    endtask

    task pwl_close;
        begin
            if (prev_pwm)
                $fwrite(pwl_fd, "%0.1fn %0.3f\n", $realtime, VDD);
            else
                $fwrite(pwl_fd, "%0.1fn 0\n", $realtime);
            $fclose(pwl_fd);
        end
    endtask

    //==========================================================================
    // Main
    //==========================================================================
    integer step;

    initial begin
        ena = 1;
        rst_n = 0;
        ui_in = 0;
        uio_in = 0;

        // Reset
        repeat (50) @(posedge clk);
        rst_n = 1;
        repeat (20) @(posedge clk);

        // Configure voice 0: sawtooth, instant attack, max sustain
        sid_write(REG_FREQ_LO, freq_table[0], 2'd0);
        sid_write(REG_FREQ_HI, 8'h00, 2'd0);
        sid_write(REG_PW_LO, 8'h00, 2'd0);
        sid_write(REG_PW_HI, 8'h08, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);

        // Filter: bypass (passthrough), vol=15
        sid_write(REG_FC_LO, 8'h00, VOICE_FILT);
        sid_write(REG_FC_HI, 8'h00, VOICE_FILT);
        sid_write(REG_RES_FILT, 8'h00, VOICE_FILT);
        sid_write(REG_MODE_VOL, 8'h1F, VOICE_FILT);

        // Gate on — sawtooth
        sid_write(REG_WAV, 8'h21, 2'd0);

        // Wait for attack
        repeat (ATTACK_WAIT) @(posedge clk);

        // Open PWL file
        pwl_open("tests/freq_sweep.pwl");

        for (step = 0; step < NUM_STEPS; step = step + 1) begin
            $display("Step %0d/%0d: freq_reg=%0d (t=%0.1f ms)",
                     step+1, NUM_STEPS, freq_table[step], $realtime/1e6);

            // Update frequency
            sid_write(REG_FREQ_LO, freq_table[step], 2'd0);

            // Run for STEP_CYCLES
            repeat (STEP_CYCLES) begin
                @(posedge clk);
                pwl_sample;
            end
        end

        pwl_close;
        $display("Frequency sweep complete: tests/freq_sweep.pwl");
        $display("Total sim time: %0.1f ms", $realtime/1e6);
        $finish;
    end

endmodule
