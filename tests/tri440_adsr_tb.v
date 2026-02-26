`timescale 1ns / 1ps
//==============================================================================
// Triangle 440 Hz + ADSR Envelope Testbench (24 MHz)
// Captures PWM pin transitions as PWL file for analog filter simulation.
//
// Voice 0: triangle waveform at 440 Hz
// ADSR: attack=9, decay=9, sustain=10, release=9 (slow for visible envelope)
// Gate ON ~1.5 s, then gate OFF ~0.5 s (shows full ADSR envelope)
//
// Output: tests/tri440_adsr.pwl
//==============================================================================
module tri440_adsr_tb;

    // --- Parameters ---
    localparam real VDD     = 3.3;
    localparam real EDGE_NS = 2.0;

`ifdef GL_TEST
    // GL mode: shorter for speed (~1.5 s total)
    localparam GATE_ON_CYCLES  = 24_000_000;  // 1.0 s
    localparam GATE_OFF_CYCLES = 12_000_000;  // 0.5 s
`else
    // RTL mode: full 2 s
    localparam GATE_ON_CYCLES  = 36_000_000;  // 1.5 s
    localparam GATE_OFF_CYCLES = 12_000_000;  // 0.5 s
`endif
    localparam SIM_CYCLES      = GATE_ON_CYCLES + GATE_OFF_CYCLES;

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
        real    t_ns;
        begin
            fd = $fopen(filename, "w");
            if (fd == 0) begin
                $display("ERROR: Cannot open %0s", filename);
                $finish;
            end

            prev_pwm = pwm_raw;
            if (prev_pwm)
                $fwrite(fd, "0n %0.3f\n", VDD);
            else
                $fwrite(fd, "0n 0\n");

            for (cyc = 0; cyc < num_cycles; cyc = cyc + 1) begin
                @(posedge clk);
                if (pwm_raw !== prev_pwm) begin
                    t_ns = $realtime;
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

            t_ns = $realtime;
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

        // Configure voice 0: triangle 440 Hz
        sid_write(REG_FREQ_LO, 8'h24, 2'd0);   // freq_lo for 440 Hz
        sid_write(REG_FREQ_HI, 8'h00, 2'd0);   // freq_hi
        sid_write(REG_PW_LO, 8'h00, 2'd0);
        sid_write(REG_PW_HI, 8'h08, 2'd0);     // pw=0x800

        // ADSR: attack=9, decay=9, sustain=10, release=9 (slow — visible envelope)
        sid_write(REG_ATK, 8'h99, 2'd0);        // {attack[3:0], decay[3:0]}
        sid_write(REG_SUS, 8'hA9, 2'd0);        // {sustain[3:0], release[3:0]}

        // Filter bypass: vol=15, no filter mode bits
        sid_write(REG_FC_LO, 8'h00, VOICE_FILT);
        sid_write(REG_FC_HI, 8'h00, VOICE_FILT);
        sid_write(REG_RES_FILT, 8'h00, VOICE_FILT);
        sid_write(REG_MODE_VOL, 8'h0F, VOICE_FILT);

        // Gate ON — triangle waveform (0x10) + gate (0x01) = 0x11
        $display("Gate ON — triangle 440 Hz with ADSR (A=9 D=9 S=10 R=9)");
        sid_write(REG_WAV, 8'h11, 2'd0);

        // Begin capture immediately (captures attack/decay/sustain phases)
        fork
            capture_pwl("tests/tri440_adsr.pwl", SIM_CYCLES);
            begin
                // After ~80 ms, gate OFF to trigger release phase
                repeat (GATE_ON_CYCLES) @(posedge clk);
                $display("Gate OFF — release phase");
                sid_write(REG_WAV, 8'h10, 2'd0);  // triangle waveform, gate=0
            end
        join

        $display("tri440_adsr PWL generation complete.");
        $finish;
    end

endmodule
