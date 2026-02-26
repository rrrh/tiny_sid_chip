`timescale 1ns / 1ps
//==============================================================================
// Filter Modes Testbench (24 MHz)
// Captures PWM output for bypass / LP / BP / HP filter modes.
//
// Voice 0: triangle 440 Hz, ADSR: A=9 D=9 S=10 R=9
// Filter: fc[10:5]=1, alpha=1/512, fc ≈ 497 Hz, resonance=8
//         Voice 0 routed through filter.
//
// Outputs: tests/filter_bypass.pwl, filter_lp.pwl, filter_bp.pwl, filter_hp.pwl
//==============================================================================
module filter_modes_tb;

    localparam real VDD     = 3.3;
    localparam real EDGE_NS = 2.0;

    // Wait for ADSR attack to reach sustain (~1 s at attack=9)
    localparam ATTACK_WAIT = 24_000_000;   // 1.0 s
    // Capture duration per mode
    localparam CAPTURE_CYCLES = 6_000_000; // 0.25 s

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
    // Main test sequence
    //==========================================================================
    initial begin
        ena = 1;
        rst_n = 0;
        ui_in = 0;
        uio_in = 0;

        do_reset;

        // --- Configure voice 0: triangle 440 Hz ---
        sid_write(REG_FREQ_LO, 8'h24, 2'd0);   // freq_lo for 440 Hz
        sid_write(REG_FREQ_HI, 8'h00, 2'd0);   // freq_hi
        sid_write(REG_PW_LO,   8'h00, 2'd0);
        sid_write(REG_PW_HI,   8'h08, 2'd0);   // pw=0x800

        // ADSR: attack=9, decay=9, sustain=10, release=9
        sid_write(REG_ATK, 8'h99, 2'd0);
        sid_write(REG_SUS, 8'hA9, 2'd0);

        // --- Filter setup ---
        // fc[10:5] = 1 → alpha = 1/512, fc ≈ 497 Hz (closest to 440)
        // fc[10:0] = 1<<5 = 32 = {fc_hi=0x04, fc_lo[2:0]=0b000}
        sid_write(REG_FC_LO, 8'h00, VOICE_FILT);
        sid_write(REG_FC_HI, 8'h04, VOICE_FILT);

        // Resonance = 8, voice 0 routed to filter
        sid_write(REG_RES_FILT, 8'h81, VOICE_FILT);

        // Start bypass: vol=15, no mode bits
        sid_write(REG_MODE_VOL, 8'h0F, VOICE_FILT);

        // --- Gate ON: triangle + gate ---
        $display("Gate ON — triangle 440 Hz with ADSR (A=9 D=9 S=10 R=9)");
        sid_write(REG_WAV, 8'h11, 2'd0);

        // Wait for ADSR to reach sustain
        $display("Waiting for attack phase (%0d cycles)...", ATTACK_WAIT);
        repeat (ATTACK_WAIT) @(posedge clk);

        // ===== Bypass capture =====
        $display("Capturing bypass (no filter) ...");
        sid_write(REG_MODE_VOL, 8'h0F, VOICE_FILT);  // no mode, vol=15
        capture_pwl("tests/filter_bypass.pwl", CAPTURE_CYCLES);

        // ===== LP capture =====
        $display("Capturing LP mode ...");
        sid_write(REG_MODE_VOL, 8'h1F, VOICE_FILT);  // LP, vol=15
        capture_pwl("tests/filter_lp.pwl", CAPTURE_CYCLES);

        // ===== BP capture =====
        $display("Capturing BP mode ...");
        sid_write(REG_MODE_VOL, 8'h2F, VOICE_FILT);  // BP, vol=15
        capture_pwl("tests/filter_bp.pwl", CAPTURE_CYCLES);

        // ===== HP capture =====
        $display("Capturing HP mode ...");
        sid_write(REG_MODE_VOL, 8'h4F, VOICE_FILT);  // HP, vol=15
        capture_pwl("tests/filter_hp.pwl", CAPTURE_CYCLES);

        // Gate OFF
        sid_write(REG_WAV, 8'h10, 2'd0);

        $display("Filter modes PWL generation complete.");
        $finish;
    end

endmodule
