`timescale 1ns / 1ps
//==============================================================================
// Frequency Sweep Testbench (24 MHz)
// Sweeps Voice 0 sawtooth through 16 frequency points (matching SVF fc codes).
// Bypass mode — no filter routing, captures raw digital→PWM output.
//
// Voice 0: sawtooth waveform, instant attack (A=0), max sustain (S=15), gate ON
// Filter: bypass (mode_vol=0x0F, res_filt=0x00)
//
// Outputs: tests/sweep_0250hz.pwl through tests/sweep_16000hz.pwl
//==============================================================================
module freq_sweep_tb;

    localparam real VDD     = 3.3;
    localparam real EDGE_NS = 2.0;

    // Settle time per frequency point (20 osc cycles at slowest = ~80ms at 250Hz,
    // but we use a fixed count for digital settling)
    localparam SETTLE_CYCLES = 480_000;   // 20 ms at 24 MHz
    // Capture duration per frequency point
    localparam CAPTURE_CYCLES = 480_000;  // 20 ms at 24 MHz

    // --- Clock and DUT ---
    reg clk;
    initial clk = 0;
    always #21 clk = ~clk;  // ~24 MHz

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    wire pwm_raw = uo_out[0];

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
    // Register write task (negedge-aligned for GL compatibility)
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
        input integer num_cycles;
        integer fd, cyc;
        reg     prev_pwm;
        real    t_ns, t0;
        begin
            fd = $fopen(filename, "w");
            if (fd == 0) begin
                $display("ERROR: Cannot open %0s", filename);
                $finish;
            end

            t0 = $realtime;  // capture start time — all timestamps relative to this

            prev_pwm = pwm_raw;
            if (prev_pwm)
                $fwrite(fd, "0n %0.3f\n", VDD);
            else
                $fwrite(fd, "0n 0\n");

            for (cyc = 0; cyc < num_cycles; cyc = cyc + 1) begin
                @(posedge clk);
                if (pwm_raw !== prev_pwm) begin
                    t_ns = $realtime - t0;
                    if (pwm_raw) begin
                        $fwrite(fd, "%0.1fn 0\n",   t_ns);
                        $fwrite(fd, "%0.1fn %0.3f\n", t_ns + EDGE_NS, VDD);
                    end else begin
                        $fwrite(fd, "%0.1fn %0.3f\n", t_ns, VDD);
                        $fwrite(fd, "%0.1fn 0\n",     t_ns + EDGE_NS);
                    end
                    prev_pwm = pwm_raw;
                end
            end

            t_ns = $realtime - t0;
            if (prev_pwm)
                $fwrite(fd, "%0.1fn %0.3f\n", t_ns, VDD);
            else
                $fwrite(fd, "%0.1fn 0\n", t_ns);

            $fclose(fd);
        end
    endtask

    //==========================================================================
    // Frequency point capture task
    //==========================================================================
    task sweep_point;
        input [7:0] freq_lo;
        input [7:0] freq_hi;
        input [255:0] filename;
        input integer freq_hz;
        begin
            $display("  Freq %0d Hz: reg=0x%02x%02x -> %0s",
                     freq_hz, freq_hi, freq_lo, filename);
            sid_write(REG_FREQ_LO, freq_lo, 2'd0);
            sid_write(REG_FREQ_HI, freq_hi, 2'd0);
            repeat (SETTLE_CYCLES) @(posedge clk);
            capture_pwl(filename, CAPTURE_CYCLES);
        end
    endtask

    //==========================================================================
    // Main test sequence
    //==========================================================================
    initial begin
        ena = 1;
        rst_n = 0;
        ui_in = 0;
        uio_in = 0;

        do_reset;

        // --- Configure voice 0: sawtooth, instant ADSR ---
        sid_write(REG_FREQ_LO, 8'h42, 2'd0);   // initial freq (1 kHz)
        sid_write(REG_FREQ_HI, 8'h00, 2'd0);
        sid_write(REG_PW_LO,   8'h00, 2'd0);
        sid_write(REG_PW_HI,   8'h08, 2'd0);   // pw=0x800 (not used for saw)

        // ADSR: attack=0 (instant), decay=0, sustain=15, release=0
        // REG_ATK = {decay[7:4], attack[3:0]}, REG_SUS = {release[7:4], sustain[3:0]}
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);

        // --- Filter: bypass mode ---
        sid_write(REG_FC_LO, 8'h00, VOICE_FILT);
        sid_write(REG_FC_HI, 8'h00, VOICE_FILT);
        sid_write(REG_RES_FILT, 8'h00, VOICE_FILT);  // no routing
        sid_write(REG_MODE_VOL, 8'h0F, VOICE_FILT);   // bypass, vol=15

        // --- Gate ON: sawtooth + gate ---
        // Sawtooth = bit 5, gate = bit 0
        sid_write(REG_WAV, 8'h21, 2'd0);
        $display("Gate ON — sawtooth waveform, bypass mode, vol=15");

        // Let ADSR reach sustain (instant attack, but need a few cycles)
        repeat (24_000) @(posedge clk);  // 1 ms

        // ===== 16-point frequency sweep =====
        $display("Starting 16-point frequency sweep...");

        // Code 0: 250 Hz — freq_reg = 16
        sweep_point(8'h10, 8'h00, "tests/sweep_0250hz.pwl", 250);

        // Code 1: 330 Hz — freq_reg = 22
        sweep_point(8'h16, 8'h00, "tests/sweep_0330hz.pwl", 330);

        // Code 2: 400 Hz — freq_reg = 26
        sweep_point(8'h1A, 8'h00, "tests/sweep_0400hz.pwl", 400);

        // Code 3: 500 Hz — freq_reg = 33
        sweep_point(8'h21, 8'h00, "tests/sweep_0500hz.pwl", 500);

        // Code 4: 660 Hz — freq_reg = 43
        sweep_point(8'h2B, 8'h00, "tests/sweep_0660hz.pwl", 660);

        // Code 5: 800 Hz — freq_reg = 52
        sweep_point(8'h34, 8'h00, "tests/sweep_0800hz.pwl", 800);

        // Code 6: 1000 Hz — freq_reg = 66
        sweep_point(8'h42, 8'h00, "tests/sweep_1000hz.pwl", 1000);

        // Code 7: 1300 Hz — freq_reg = 85
        sweep_point(8'h55, 8'h00, "tests/sweep_1300hz.pwl", 1300);

        // Code 8: 2000 Hz — freq_reg = 131
        sweep_point(8'h83, 8'h00, "tests/sweep_2000hz.pwl", 2000);

        // Code 9: 2700 Hz — freq_reg = 177
        sweep_point(8'hB1, 8'h00, "tests/sweep_2700hz.pwl", 2700);

        // Code 10: 4000 Hz — freq_reg = 262
        sweep_point(8'h06, 8'h01, "tests/sweep_4000hz.pwl", 4000);

        // Code 11: 5300 Hz — freq_reg = 347
        sweep_point(8'h5B, 8'h01, "tests/sweep_5300hz.pwl", 5300);

        // Code 12: 8000 Hz — freq_reg = 524
        sweep_point(8'h0C, 8'h02, "tests/sweep_8000hz.pwl", 8000);

        // Code 13: 10600 Hz — freq_reg = 695
        sweep_point(8'hB7, 8'h02, "tests/sweep_10600hz.pwl", 10600);

        // Code 14: 12700 Hz — freq_reg = 832
        sweep_point(8'h40, 8'h03, "tests/sweep_12700hz.pwl", 12700);

        // Code 15: 16000 Hz — freq_reg = 1049
        sweep_point(8'h19, 8'h04, "tests/sweep_16000hz.pwl", 16000);

        // Gate OFF
        sid_write(REG_WAV, 8'h20, 2'd0);

        $display("Frequency sweep PWL generation complete (16 files).");
        $finish;
    end

endmodule
