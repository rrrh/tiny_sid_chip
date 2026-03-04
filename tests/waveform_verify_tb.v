`timescale 1ns / 1ps
//==============================================================================
// SID Waveform Verification Testbench (24 MHz)
// Captures 12 PWL files: all 4 waveforms (tri/saw/pulse/noise) at 3
// frequencies (220/440/880 Hz).
//
// Output: tests/wv_*.pwl — piecewise-linear voltage waveforms
// VDD = 3.3 V, edge time = 2 ns (matches PCB I/O bank)
//==============================================================================
module waveform_verify_tb;

    // --- Parameters ---
    localparam real VDD     = 3.3;
    localparam real EDGE_NS = 2.0;
    localparam      SIM_CYCLES  = 1_800_000;  // 75 ms at 24 MHz
    localparam      ATTACK_WAIT =   200_000;  // ~8.3 ms settle

    // --- Clock and DUT ---
    reg clk;
    initial clk = 0;
    always #21 clk = ~clk;  // ~24 MHz (41.67 ns period)

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    wire pwm_out = uo_out[0];  // unfiltered PWM (mix_out)

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

    //==========================================================================
    // Register write task
    //==========================================================================
    task sid_write;
        input [2:0] addr;
        input [7:0] data;
        input [1:0] voice;
        begin
            ui_in  = {1'b0, 2'b00, voice, addr};
            uio_in = data;
            @(posedge clk);
            ui_in[7] = 1'b1;
            @(posedge clk);
            ui_in[7] = 1'b0;
            @(posedge clk);
        end
    endtask

    //==========================================================================
    // Reset
    //==========================================================================
    task do_reset;
        begin
            rst_n = 0;
            ui_in = 0;
            uio_in = 0;
            repeat (50) @(posedge clk);
            rst_n = 1;
            repeat (20) @(posedge clk);
        end
    endtask

    //==========================================================================
    // Capture PWM transitions to PWL file
    //==========================================================================
    task capture_pwl;
        input [255:0] filename;
        integer fd, cyc;
        reg     prev_pwm;
        real    t_ns, t_start;
        begin
            fd = $fopen(filename, "w");
            if (fd == 0) begin
                $display("ERROR: Cannot open %0s", filename);
                $finish;
            end

            // Record start time so PWL timestamps are relative to capture start
            t_start = $realtime;

            // Write initial state
            prev_pwm = pwm_out;
            if (prev_pwm)
                $fwrite(fd, "0n %0.3f\n", VDD);
            else
                $fwrite(fd, "0n 0\n");

            // Record transitions
            for (cyc = 0; cyc < SIM_CYCLES; cyc = cyc + 1) begin
                @(posedge clk);
                if (pwm_out !== prev_pwm) begin
                    t_ns = $realtime - t_start;
                    if (pwm_out) begin
                        $fwrite(fd, "%0.1fn 0\n",   t_ns);
                        $fwrite(fd, "%0.1fn %0.3f\n", t_ns + EDGE_NS, VDD);
                    end else begin
                        $fwrite(fd, "%0.1fn %0.3f\n", t_ns, VDD);
                        $fwrite(fd, "%0.1fn 0\n",     t_ns + EDGE_NS);
                    end
                    prev_pwm = pwm_out;
                end
            end

            // Final state
            t_ns = $realtime - t_start;
            if (prev_pwm)
                $fwrite(fd, "%0.1fn %0.3f\n", t_ns, VDD);
            else
                $fwrite(fd, "%0.1fn 0\n", t_ns);

            $fclose(fd);
        end
    endtask

    //==========================================================================
    // Configure voice 0, gate on, wait attack, capture PWL
    //==========================================================================
    task capture_tone;
        input [7:0] freq_lo;
        input [7:0] freq_hi_val;
        input [7:0] waveform_reg;
        input [255:0] filename;
        begin
            do_reset;

            // Configure voice 0
            sid_write(REG_FREQ_LO, freq_lo, 2'd0);
            sid_write(REG_FREQ_HI, freq_hi_val, 2'd0);
            sid_write(REG_PW_LO, 8'h00, 2'd0);
            sid_write(REG_PW_HI, 8'h08, 2'd0);  // pw=0x800 (50% duty)
            sid_write(REG_ATK, 8'h00, 2'd0);     // instant attack/decay
            sid_write(REG_SUS, 8'h0F, 2'd0);     // max sustain, instant release

            // Filter bypass: vol=15
            sid_write(REG_FC_LO, 8'h00, VOICE_FILT);
            sid_write(REG_FC_HI, 8'h00, VOICE_FILT);
            sid_write(REG_RES_FILT, 8'h00, VOICE_FILT);
            sid_write(REG_MODE_VOL, 8'h1F, VOICE_FILT);

            // Gate on (waveform_reg has gate bit set)
            sid_write(REG_WAV, waveform_reg, 2'd0);

            // Wait for attack ramp
            repeat (ATTACK_WAIT) @(posedge clk);

            // Capture PWM transitions
            capture_pwl(filename);
        end
    endtask

    //==========================================================================
    // Main test sequence — 6 captures
    //==========================================================================
    initial begin
        ena = 1;
        rst_n = 0;
        ui_in = 0;
        uio_in = 0;

        // 24-bit acc @ 1 MHz: freq_reg = hz * 2^24 / 1e6
        // 220 Hz -> 3691 (0x0E6B), 440 Hz -> 7382 (0x1CD6), 880 Hz -> 14764 (0x39AC)

        $display("=== SID Waveform Verification ===");

        // --- Triangle (0x11) ---
        $display("[1/12] Triangle 220 Hz");
        capture_tone(8'h6B, 8'h0E, 8'h11, "tests/wv_tri_220.pwl");
        $display("[2/12] Triangle 440 Hz");
        capture_tone(8'hD6, 8'h1C, 8'h11, "tests/wv_tri_440.pwl");
        $display("[3/12] Triangle 880 Hz");
        capture_tone(8'hAC, 8'h39, 8'h11, "tests/wv_tri_880.pwl");

        // --- Sawtooth (0x21) ---
        $display("[4/12] Sawtooth 220 Hz");
        capture_tone(8'h6B, 8'h0E, 8'h21, "tests/wv_saw_220.pwl");
        $display("[5/12] Sawtooth 440 Hz");
        capture_tone(8'hD6, 8'h1C, 8'h21, "tests/wv_saw_440.pwl");
        $display("[6/12] Sawtooth 880 Hz");
        capture_tone(8'hAC, 8'h39, 8'h21, "tests/wv_saw_880.pwl");

        // --- Pulse 50% duty (0x41) ---
        $display("[7/12] Pulse 220 Hz");
        capture_tone(8'h6B, 8'h0E, 8'h41, "tests/wv_pulse_220.pwl");
        $display("[8/12] Pulse 440 Hz");
        capture_tone(8'hD6, 8'h1C, 8'h41, "tests/wv_pulse_440.pwl");
        $display("[9/12] Pulse 880 Hz");
        capture_tone(8'hAC, 8'h39, 8'h41, "tests/wv_pulse_880.pwl");

        // --- Noise (0x81) ---
        $display("[10/12] Noise 220 Hz");
        capture_tone(8'h6B, 8'h0E, 8'h81, "tests/wv_noise_220.pwl");
        $display("[11/12] Noise 440 Hz");
        capture_tone(8'hD6, 8'h1C, 8'h81, "tests/wv_noise_440.pwl");
        $display("[12/12] Noise 880 Hz");
        capture_tone(8'hAC, 8'h39, 8'h81, "tests/wv_noise_880.pwl");

        $display("=== All 12 PWL captures complete ===");
        $finish;
    end

endmodule
