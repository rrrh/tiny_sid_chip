`timescale 1ns / 1ps
//==============================================================================
// Gate-Level Testbench: 440 Hz Sawtooth with ADSR Envelope
//
// Slow attack, medium decay, mid-level sustain, slow release.
// Captures PWM output as PWL for analog filter simulation.
//
// ADSR settings:
//   Attack  = 11 (slow)    — ~480 ms rise to peak
//   Decay   = 7  (medium)  — ~100 ms fall to sustain
//   Sustain = 8  (mid)     — ~50% level
//   Release = 11 (slow)    — ~480 ms fade to silence
//
// Usage (RTL):
//   iverilog -o tests/gl_saw440_adsr -g2005-sv src/tt_um_sid.v src/filter.v \
//     src/SVF_8bit.v src/pwm_audio.v tests/gl_saw440_adsr_tb.v
//   vvp tests/gl_saw440_adsr
//
// Usage (GL):
//   iverilog -o tests/gl_saw440_adsr_gl -g2012 -DGL_TEST -DFUNCTIONAL -DSIM \
//     -I src patched_stdcell.v gate_level_netlist.v tests/gl_saw440_adsr_tb.v
//   vvp tests/gl_saw440_adsr_gl
//==============================================================================
module gl_saw440_adsr_tb;

    localparam real VDD     = 3.3;
    localparam real EDGE_NS = 2.0;

    // Timing (in 24 MHz clock cycles):
    //   Gate-on hold  : ~1.5 s (attack + decay + sustain hold)
    //   Gate-off tail : ~1.0 s (release fade)
    //   Total         : ~2.5 s
`ifdef GL_TEST
    localparam GATE_ON_CYCLES  = 18_000_000;  // 750 ms (shorter for GL speed)
    localparam GATE_OFF_CYCLES = 12_000_000;  // 500 ms
`else
    localparam GATE_ON_CYCLES  = 36_000_000;  // 1500 ms
    localparam GATE_OFF_CYCLES = 24_000_000;  // 1000 ms
`endif

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

    //==========================================================================
    // Register write (negedge-aligned for GL compatibility)
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
    initial begin
        ena = 1;
        rst_n = 0;
        ui_in = 0;
        uio_in = 0;

        // Reset
        repeat (50) @(posedge clk);
        rst_n = 1;
        repeat (20) @(posedge clk);

        // --- Configure voice 0 ---

        // Frequency: 440 Hz (freq_reg = 7382 = 0x1CD6)
        sid_write(REG_FREQ_LO, 8'hD6, 2'd0);
        sid_write(REG_FREQ_HI, 8'h1C, 2'd0);

        // Pulse width (unused for sawtooth, but set default)
        sid_write(REG_PW_LO, 8'h00, 2'd0);
        sid_write(REG_PW_HI, 8'h08, 2'd0);

        // ADSR: attack=11 (slow), decay=7 (medium)
        // Register 4 = {decay[3:0], attack[3:0]} = {4'd7, 4'd11} = 8'h7B
        sid_write(REG_ATK, 8'h7B, 2'd0);

        // Sustain=8 (mid-level), release=11 (slow)
        // Register 5 = {release[3:0], sustain[3:0]} = {4'd11, 4'd8} = 8'hB8
        sid_write(REG_SUS, 8'hB8, 2'd0);

        // Filter: bypass (passthrough), vol=15
        sid_write(REG_FC_LO, 8'h00, VOICE_FILT);
        sid_write(REG_FC_HI, 8'h00, VOICE_FILT);
        sid_write(REG_RES_FILT, 8'h00, VOICE_FILT);
        sid_write(REG_MODE_VOL, 8'h0F, VOICE_FILT);

        // Start PWL capture
        pwl_open("tests/saw440_adsr.pwl");

        // --- Gate ON: sawtooth + gate ---
        $display("Gate ON (sawtooth 440 Hz, ADSR: A=11 D=7 S=8 R=11)");
        sid_write(REG_WAV, 8'h21, 2'd0);  // saw + gate

        repeat (GATE_ON_CYCLES) begin
            @(posedge clk);
            pwl_sample;
        end
        $display("  Attack+Decay+Sustain phase done (t=%0.1f ms)", $realtime/1e6);

        // --- Gate OFF: release phase ---
        $display("Gate OFF (release)");
        sid_write(REG_WAV, 8'h20, 2'd0);  // saw, gate=0

        repeat (GATE_OFF_CYCLES) begin
            @(posedge clk);
            pwl_sample;
        end
        $display("  Release phase done (t=%0.1f ms)", $realtime/1e6);

        pwl_close;
        $display("Complete: tests/saw440_adsr.pwl (%0.2f s)", $realtime/1e9);
        $finish;
    end

endmodule
