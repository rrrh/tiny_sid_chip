`timescale 1ns / 1ps
//==============================================================================
// SID Top Level Testbench — Single Voice
//==============================================================================

module sid_top_tb;

    reg clk;
    reg rst;

    initial clk = 0;
    always #10 clk = ~clk;  // 50 MHz

    reg [15:0] frequency;
    reg [15:0] duration;
    reg [7:0]  attack;
    reg [7:0]  sustain;
    reg [7:0]  waveform;

    wire [7:0] audio_out;

    sid_top dut (
        .clk       (clk),
        .rst       (rst),
        .frequency (frequency),
        .duration  (duration),
        .attack    (attack),
        .sustain   (sustain),
        .waveform  (waveform),
        .audio_out (audio_out)
    );

    initial begin
        $dumpfile("sid_top_tb.vcd");
        $dumpvars(0, sid_top_tb);
    end

    // Waveform bit constants
    localparam GATE     = 8'h01;
    localparam RINGMOD  = 8'h04;
    localparam TRI      = 8'h10;
    localparam SAW      = 8'h20;
    localparam PULSE    = 8'h40;
    localparam NOISE    = 8'h80;

    localparam FREQ_C4  = 16'd4291;
    localparam FREQ_E4  = 16'd5404;
    localparam FREQ_C5  = 16'd8583;

    initial begin
        frequency = 0; duration = 0; attack = 0; sustain = 0; waveform = 0;
        rst = 1;
        repeat (10) @(posedge clk);
        rst = 0;
        repeat (5) @(posedge clk);

        //--------------------------------------------------------------
        // Test 1: Sawtooth C4
        //--------------------------------------------------------------
        $display("[%0t] Test 1: Sawtooth C4", $time);
        frequency = FREQ_C4; duration = 16'h0800;
        attack = 8'h00; sustain = 8'h0F;
        waveform = SAW | GATE;

        repeat (5000) @(posedge clk);
        if (audio_out == 0)
            $display("[%0t] FAIL: output is zero", $time);
        else
            $display("[%0t] OK: output = %0d", $time, audio_out);

        waveform = SAW;
        repeat (5000) @(posedge clk);

        //--------------------------------------------------------------
        // Test 2: Pulse wave E4
        //--------------------------------------------------------------
        $display("[%0t] Test 2: Pulse E4", $time);
        frequency = FREQ_E4; duration = 16'h0400;
        attack = 8'h20; sustain = 8'h4A;
        waveform = PULSE | GATE;

        repeat (8000) @(posedge clk);
        if (audio_out == 0)
            $display("[%0t] FAIL: output is zero", $time);
        else
            $display("[%0t] OK: output = %0d", $time, audio_out);

        waveform = PULSE;
        repeat (5000) @(posedge clk);

        //--------------------------------------------------------------
        // Test 3: Triangle C4
        //--------------------------------------------------------------
        $display("[%0t] Test 3: Triangle C4", $time);
        frequency = FREQ_C4; duration = 16'h0000;
        attack = 8'h00; sustain = 8'h0F;
        waveform = TRI | GATE;

        repeat (5000) @(posedge clk);
        if (audio_out == 0)
            $display("[%0t] FAIL: output is zero", $time);
        else
            $display("[%0t] OK: output = %0d", $time, audio_out);

        waveform = TRI;
        repeat (5000) @(posedge clk);

        //--------------------------------------------------------------
        // Test 4: Noise
        //--------------------------------------------------------------
        $display("[%0t] Test 4: Noise C5", $time);
        frequency = FREQ_C5; duration = 16'h0000;
        attack = 8'h00; sustain = 8'h0F;
        waveform = NOISE | GATE;

        repeat (8000) @(posedge clk);
        if (audio_out == 0)
            $display("[%0t] FAIL: output is zero", $time);
        else
            $display("[%0t] OK: output = %0d", $time, audio_out);

        waveform = NOISE;
        repeat (3000) @(posedge clk);

        //--------------------------------------------------------------
        // Done
        //--------------------------------------------------------------
        $display("[%0t] All tests complete.", $time);
        $finish;
    end

endmodule
