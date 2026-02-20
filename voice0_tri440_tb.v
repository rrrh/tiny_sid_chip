`timescale 1ns / 1ps
//==============================================================================
// Testbench: Voice 0 triangle wave at 440 Hz
//==============================================================================
// With a 16-bit accumulator and /16 prescaler, effective voice update
// rate is 50 MHz / 3 / 16 = 1.042 MHz. Resolution is ~15.9 Hz per step:
//   freq_reg = Hz * 65536 / (50e6 / 3 / 16) ≈ Hz * 0.06291
//   440 Hz → freq_reg = 27.7 → 28 → actual 445 Hz
//
// Captures voice output (voice_out[11:4]) directly, bypassing PWM,
// at ~44.1 kHz for multiple periods, then writes to a text file.
//==============================================================================
module voice0_tri440_tb;

    reg clk;
    initial clk = 0;
    always #10 clk = ~clk; // 50 MHz

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    // Direct access to internal voice output (8-bit, after envelope + mix shift)
    wire [7:0] mix_out    = dut.mix_out;
    // Raw 12-bit voice output before mixing
    wire [11:0] voice_out = dut.voice_out;
    // Phase accumulator for voice 0
    wire [15:0] v0_acc    = dut.v_acc_0;
    // ADSR envelope for voice 0
    wire [3:0]  v0_env    = dut.v_env_0;

    // Decimation: sample every 1134 clocks ≈ 44,092 Hz
    localparam DECIM = 1134;
    // freq_reg=28, voice update every 3 clocks (50 MHz / 3)
    // One period = 2^20 / 28 ≈ 37,449 voice updates = 112,348 clocks
    // At 44092 Hz sample rate, one period ≈ 99 samples
    // Capture 10 periods for a useful WAV
    localparam SAMPLES = 1000;
    // Attack ramp wait: 500k clocks = 10ms (more than enough for rate 0)
    localparam ATTACK_WAIT = 500_000;

    //==========================================================================
    // Register write task
    //==========================================================================
    task sid_write(input [2:0] addr, input [7:0] data, input [1:0] voice);
        begin
            ui_in = {1'b0, 2'b00, voice, addr};
            uio_in = data;
            @(posedge clk);
            ui_in[7] = 1'b1;
            @(posedge clk);
            ui_in[7] = 1'b0;
            @(posedge clk);
        end
    endtask

    //==========================================================================
    // Main test
    //==========================================================================
    integer fd, i, j;

    initial begin
        $dumpfile("voice0_tri440.vcd");
        $dumpvars(0, voice0_tri440_tb);

        ena = 1; rst_n = 0; ui_in = 0; uio_in = 0;
        repeat (20) @(posedge clk);
        rst_n = 1;
        repeat (10) @(posedge clk);

        // Configure voice 0: triangle, freq_reg=28 (~445 Hz), fastest attack, full sustain
        sid_write(0, 8'h1C, 0); // freq_lo = 0x1C (28)
        sid_write(1, 8'h00, 0); // freq_hi = 0x00
        sid_write(4, 8'h00, 0); // attack=0 (fastest), decay=0
        sid_write(5, 8'h0F, 0); // sustain=F (full), release=0
        sid_write(6, 8'h11, 0); // triangle + gate

        $display("Voice 0 configured: triangle, freq_reg=28 (~445 Hz)");
        $display("Waiting for ADSR attack ramp...");

        // Wait for attack to ramp to full
        repeat (ATTACK_WAIT) @(posedge clk);

        $display("Envelope value: %0d (expect 15)", v0_env);
        $display("Capturing %0d samples at ~44.1 kHz...", SAMPLES);

        // Capture voice output samples
        fd = $fopen("voice0_tri440.raw", "w");

        for (i = 0; i < SAMPLES; i = i + 1) begin
            // Write: mix_out (8-bit), voice_out (12-bit), accumulator
            $fwrite(fd, "%d %d %d\n", mix_out, voice_out, v0_acc);
            for (j = 0; j < DECIM; j = j + 1)
                @(posedge clk);
        end

        $fclose(fd);
        $display("Wrote %0d samples to voice0_tri440.raw", SAMPLES);
        $display("Done.");
        $finish;
    end

endmodule
