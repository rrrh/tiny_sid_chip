`timescale 1ns / 1ps
//==============================================================================
// Testbench for tt_um_sid (5 MHz, 2-voice Time-Multiplexed SID)
//==============================================================================

module tt_um_sid_tb;

    reg clk;
    initial clk = 0;
    always #100 clk = ~clk;  // 5 MHz (200 ns period)

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    wire pdm_out = uo_out[0];

    // PDM-to-PCM decimation
    localparam DECIM_SHIFT = 10;
    reg [DECIM_SHIFT:0] decim_acc, pcm_out;
    reg [DECIM_SHIFT-1:0] decim_cnt;
    reg pcm_valid;

    always @(posedge clk) begin
        if (!rst_n) begin
            decim_acc <= 0; decim_cnt <= 0; pcm_out <= 0; pcm_valid <= 0;
        end else begin
            pcm_valid <= 0;
            if (&decim_cnt) begin
                pcm_out <= decim_acc + pdm_out;
                pcm_valid <= 1;
                decim_acc <= 0; decim_cnt <= 0;
            end else begin
                decim_acc <= decim_acc + pdm_out;
                decim_cnt <= decim_cnt + 1;
            end
        end
    end

    integer pass_count, fail_count, test_num;
    initial begin pass_count = 0; fail_count = 0; test_num = 0; end

    localparam [7:0] GATE  = 8'h01, SYNC  = 8'h02, RMOD  = 8'h04, TEST  = 8'h08,
                     TRI   = 8'h10, SAW   = 8'h20, PULSE = 8'h40, NOISE = 8'h80;

    localparam [7:0] FREQ_C4 = 8'd17, FREQ_E4 = 8'd22,
                     FREQ_G4 = 8'd26, FREQ_C5 = 8'd34;

    localparam [2:0] REG_FREQ = 3'd0, REG_PW = 3'd2,
                     REG_ATK  = 3'd4, REG_SUS = 3'd5, REG_WAV = 3'd6;

    initial begin
        $dumpfile("tt_um_sid_tb.vcd");
        $dumpvars(0, tt_um_sid_tb);
    end

    task sid_write;
        input [2:0] addr; input [7:0] data; input [1:0] voice;
        begin
            ui_in[2:0] <= addr; ui_in[4:3] <= voice; uio_in <= data;
            @(posedge clk);
            ui_in[7] <= 1'b1; @(posedge clk);
            ui_in[7] <= 1'b0; @(posedge clk);
        end
    endtask

    task count_pdm;
        input integer window; output integer count;
        reg last; integer i;
        begin
            count = 0; last = pdm_out;
            for (i = 0; i < window; i = i + 1) begin
                @(posedge clk);
                if (pdm_out && !last) count = count + 1;
                last = pdm_out;
            end
        end
    endtask

    integer cnt1, cnt2;

    initial begin
        ui_in = 0; uio_in = 0; ena = 1; rst_n = 1;
        repeat (10) @(posedge clk);

        // 1. Reset
        $display("\n===== 1. Reset =====");
        rst_n = 0; repeat (50) @(posedge clk);
        test_num = test_num + 1;
        if (pdm_out == 0) begin $display("TEST %0d PASS: reset", test_num); pass_count = pass_count + 1; end
        else begin $display("TEST %0d FAIL: reset", test_num); fail_count = fail_count + 1; end
        rst_n = 1; repeat (50) @(posedge clk);

        // 2. Sawtooth
        $display("\n===== 2. Sawtooth =====");
        sid_write(REG_FREQ, FREQ_C4, 2'd0);
        sid_write(REG_PW, 8'h80, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);
        repeat (250_000) @(posedge clk);
        count_pdm(25_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 5) begin $display("TEST %0d PASS: saw pdm=%0d", test_num, cnt1); pass_count = pass_count + 1; end
        else begin $display("TEST %0d FAIL: saw pdm=%0d", test_num, cnt1); fail_count = fail_count + 1; end
        sid_write(REG_WAV, 8'h00, 2'd0);
        repeat (150_000) @(posedge clk);

        // 3. Triangle
        $display("\n===== 3. Triangle =====");
        sid_write(REG_FREQ, FREQ_C4, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, TRI | GATE, 2'd0);
        repeat (250_000) @(posedge clk);
        count_pdm(25_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 5) begin $display("TEST %0d PASS: tri pdm=%0d", test_num, cnt1); pass_count = pass_count + 1; end
        else begin $display("TEST %0d FAIL: tri pdm=%0d", test_num, cnt1); fail_count = fail_count + 1; end
        sid_write(REG_WAV, 8'h00, 2'd0);
        repeat (150_000) @(posedge clk);

        // 4. Pulse
        $display("\n===== 4. Pulse =====");
        sid_write(REG_FREQ, FREQ_E4, 2'd0);
        sid_write(REG_PW, 8'h80, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, PULSE | GATE, 2'd0);
        repeat (250_000) @(posedge clk);
        count_pdm(25_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 5) begin $display("TEST %0d PASS: pulse pdm=%0d", test_num, cnt1); pass_count = pass_count + 1; end
        else begin $display("TEST %0d FAIL: pulse pdm=%0d", test_num, cnt1); fail_count = fail_count + 1; end
        sid_write(REG_WAV, 8'h00, 2'd0);
        repeat (150_000) @(posedge clk);

        // 5. Noise
        $display("\n===== 5. Noise =====");
        sid_write(REG_FREQ, FREQ_C5, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, NOISE | GATE, 2'd0);
        repeat (250_000) @(posedge clk);
        count_pdm(25_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 5) begin $display("TEST %0d PASS: noise pdm=%0d", test_num, cnt1); pass_count = pass_count + 1; end
        else begin $display("TEST %0d FAIL: noise pdm=%0d", test_num, cnt1); fail_count = fail_count + 1; end
        sid_write(REG_WAV, 8'h00, 2'd0);
        repeat (150_000) @(posedge clk);

        // 6. Gate release
        $display("\n===== 6. Gate release =====");
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);
        repeat (250_000) @(posedge clk);
        count_pdm(25_000, cnt1);
        sid_write(REG_WAV, SAW, 2'd0);
        repeat (150_000) @(posedge clk);
        count_pdm(25_000, cnt2);
        test_num = test_num + 1;
        if (cnt2 < cnt1) begin $display("TEST %0d PASS: release (%0d->%0d)", test_num, cnt1, cnt2); pass_count = pass_count + 1; end
        else begin $display("TEST %0d FAIL: release (%0d->%0d)", test_num, cnt1, cnt2); fail_count = fail_count + 1; end
        sid_write(REG_WAV, 8'h00, 2'd0);
        repeat (150_000) @(posedge clk);

        // 7. Two voices simultaneous (per-voice ADSR)
        $display("\n===== 7. Two voices =====");
        sid_write(REG_FREQ, FREQ_C4, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0); sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);
        sid_write(REG_FREQ, FREQ_E4, 2'd1);
        sid_write(REG_PW, 8'h80, 2'd1);
        sid_write(REG_ATK, 8'h00, 2'd1); sid_write(REG_SUS, 8'h0F, 2'd1);
        sid_write(REG_WAV, PULSE | GATE, 2'd1);
        repeat (250_000) @(posedge clk);
        count_pdm(25_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 5) begin $display("TEST %0d PASS: 2-voice pdm=%0d", test_num, cnt1); pass_count = pass_count + 1; end
        else begin $display("TEST %0d FAIL: 2-voice pdm=%0d", test_num, cnt1); fail_count = fail_count + 1; end

        $display("\n====================================");
        $display("  RESULTS: %0d PASSED, %0d FAILED (of %0d)", pass_count, fail_count, test_num);
        $display("====================================\n");
        $finish;
    end

    initial begin #50_000_000_000; $display("\nERROR: Timeout!"); $finish; end

endmodule
