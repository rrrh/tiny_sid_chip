`timescale 1ns / 1ps
//==============================================================================
// Comprehensive Testbench for tt_um_sid (1 MHz, 8-bit freq, 6-bit waveform)
//==============================================================================
// Memory-Mapped Interface:
//   ui_in[2:0]  = register address
//   ui_in[4:3]  = voice select (0=voice1, 1=voice2, 2=voice3)
//   ui_in[7]    = write enable (rising-edge triggered)
//   uio_in[7:0] = write data
//
// Registers: 0=freq(per-voice), 2=pw(shared), 4=attack(shared),
//            5=sustain(shared), 6=waveform(per-voice)
//
// Waveform bits: [0]gate [1]test [2]tri [3]saw [4]pulse [5]noise
//
// 16-bit accumulator, 8-bit frequency register (zero-extended):
// freq_reg = Hz * 2^16 / 1e6 ≈ Hz * 0.06554
//==============================================================================

module tt_um_sid_tb;

    //==========================================================================
    // Clock generation — 1 MHz (1000 ns period)
    //==========================================================================
    reg clk;
    initial clk = 0;
    always #500 clk = ~clk;

    //==========================================================================
    // DUT signals
    //==========================================================================
    reg        rst_n;
    reg        ena;
    reg  [7:0] ui_in;
    wire [7:0] uo_out;
    reg  [7:0] uio_in;
    wire [7:0] uio_out;
    wire [7:0] uio_oe;

    tt_um_sid dut (
        .ui_in   (ui_in),
        .uo_out  (uo_out),
        .uio_in  (uio_in),
        .uio_out (uio_out),
        .uio_oe  (uio_oe),
        .ena     (ena),
        .clk     (clk),
        .rst_n   (rst_n)
    );

    //==========================================================================
    // Convenience aliases
    //==========================================================================
    wire pdm_out = uo_out[0];

    //==========================================================================
    // PDM-to-PCM decimation filter (CIC order 1, integrate-and-dump)
    // Converts the 1 MHz 1-bit PDM to ~977 Hz 10-bit PCM for waveform
    // inspection in VCD viewers.  Output range: 0 (silence) to 1024 (full).
    //==========================================================================
    localparam DECIM_SHIFT = 10;
    localparam DECIM_N     = 1 << DECIM_SHIFT;  // 1024 samples per window

    reg [DECIM_SHIFT:0]   decim_acc;     // running sum (0..1024)
    reg [DECIM_SHIFT-1:0] decim_cnt;     // sample counter (0..1023)
    reg [DECIM_SHIFT:0]   pcm_out;       // latched PCM output
    reg                   pcm_valid;     // 1-clk strobe per output sample

    always @(posedge clk) begin
        if (!rst_n) begin
            decim_acc <= 0;
            decim_cnt <= 0;
            pcm_out   <= 0;
            pcm_valid <= 1'b0;
        end else begin
            pcm_valid <= 1'b0;
            if (&decim_cnt) begin                // decim_cnt == 1023
                pcm_out   <= decim_acc + pdm_out;
                pcm_valid <= 1'b1;
                decim_acc <= 0;
                decim_cnt <= 0;
            end else begin
                decim_acc <= decim_acc + pdm_out;
                decim_cnt <= decim_cnt + 1;
            end
        end
    end

    //==========================================================================
    // Test scoring
    //==========================================================================
    integer pass_count;
    integer fail_count;
    integer test_num;

    initial begin
        pass_count = 0;
        fail_count = 0;
        test_num   = 0;
    end

    //==========================================================================
    // Constants — 6-bit waveform encoding
    //==========================================================================
    localparam [7:0] GATE  = 8'h01,
                     TEST  = 8'h02,
                     TRI   = 8'h04,
                     SAW   = 8'h08,
                     PULSE = 8'h10,
                     NOISE = 8'h20;

    // 8-bit freq reg, 16-bit acc at 1 MHz: freq_reg = Hz * 2^16 / 1e6
    localparam [7:0] FREQ_C4 = 8'd17,    // 262 Hz → 259 Hz
                     FREQ_E4 = 8'd22,    // 330 Hz → 336 Hz
                     FREQ_G4 = 8'd26,    // 392 Hz → 397 Hz
                     FREQ_C5 = 8'd34;    // 523 Hz → 519 Hz

    // Register addresses
    localparam [2:0] REG_FREQ    = 3'd0,
                     REG_PW      = 3'd2,
                     REG_ATK     = 3'd4,
                     REG_SUS     = 3'd5,
                     REG_WAV     = 3'd6;

    //==========================================================================
    // VCD dump
    //==========================================================================
    initial begin
        $dumpfile("tt_um_sid_tb.vcd");
        $dumpvars(0, tt_um_sid_tb);
    end

    //==========================================================================
    // Memory write task — set address + data, pulse write enable
    //==========================================================================
    task sid_write;
        input [2:0] addr;
        input [7:0] data;
        input [1:0] voice;
        begin
            ui_in[2:0] <= addr;
            ui_in[4:3] <= voice;
            uio_in     <= data;
            @(posedge clk);
            ui_in[7]   <= 1'b1;   // assert WE
            @(posedge clk);
            ui_in[7]   <= 1'b0;   // deassert WE
            @(posedge clk);
        end
    endtask

    //==========================================================================
    // Convenience: write frequency (single 8-bit register)
    //==========================================================================
    task sid_write_freq;
        input [7:0] freq;
        input [1:0] voice;
        begin
            sid_write(REG_FREQ, freq, voice);
        end
    endtask

    //==========================================================================
    // Convenience: write pulse width (shared, voice ignored)
    //==========================================================================
    task sid_write_pw;
        input [7:0] pw;
        begin
            sid_write(REG_PW, pw, 2'd0);
        end
    endtask

    //==========================================================================
    // Count PDM rising edges over a window of N system clocks
    //==========================================================================
    task count_pdm;
        input  integer window;
        output integer count;
        reg last;
        integer i;
        begin
            count = 0;
            last  = pdm_out;
            for (i = 0; i < window; i = i + 1) begin
                @(posedge clk);
                if (pdm_out && !last)
                    count = count + 1;
                last = pdm_out;
            end
        end
    endtask

    //==========================================================================
    // Measure average PCM level over N decimated samples
    //==========================================================================
    task measure_pcm;
        input  integer num_samples;
        output integer avg;
        integer sum, got;
        begin
            sum = 0;
            got = 0;
            while (got < num_samples) begin
                @(posedge clk);
                if (pcm_valid) begin
                    sum = sum + pcm_out;
                    got = got + 1;
                end
            end
            avg = sum / num_samples;
        end
    endtask

    //==========================================================================
    // Main test sequence
    //==========================================================================
    integer cnt1, cnt2;

    initial begin
        // Initialise inputs
        ui_in  = 8'b0;
        uio_in = 8'b0;
        ena    = 1'b1;
        rst_n  = 1'b1;
        repeat (2) @(posedge clk);

        // =============================================================
        // 1. Reset behaviour
        // =============================================================
        $display("\n===== 1. Reset behaviour =====");
        rst_n = 1'b0;
        repeat (10) @(posedge clk);

        test_num = test_num + 1;
        if (pdm_out == 2'd0) begin
            $display("[%0t] TEST %0d PASS: PDM is 0 during reset", $time, test_num);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: PDM not 0 during reset", $time, test_num);
            fail_count = fail_count + 1;
        end

        test_num = test_num + 1;
        if (uo_out[7:2] == 6'b0) begin
            $display("[%0t] TEST %0d PASS: upper outputs 0 during reset", $time, test_num);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: upper outputs non-zero during reset", $time, test_num);
            fail_count = fail_count + 1;
        end

        rst_n = 1'b1;
        repeat (10) @(posedge clk);

        count_pdm(1000, cnt1);
        test_num = test_num + 1;
        if (cnt1 == 0) begin
            $display("[%0t] TEST %0d PASS: PDM quiet after reset (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: PDM not quiet after reset (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        // =============================================================
        // 2. Register write — verify PDM becomes active
        // =============================================================
        $display("\n===== 2. Register write =====");
        sid_write_freq(FREQ_C4, 2'd0);
        sid_write_pw(8'h80);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: PDM active after register writes (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: PDM inactive after register writes (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW, 2'd0);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 3. Sawtooth waveform
        // =============================================================
        $display("\n===== 3. Sawtooth waveform =====");
        sid_write_freq(FREQ_C4, 2'd0);
        sid_write_pw(8'h80);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Sawtooth PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Sawtooth PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW, 2'd0);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 4. Triangle waveform
        // =============================================================
        $display("\n===== 4. Triangle waveform =====");
        sid_write_freq(FREQ_C4, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, TRI | GATE, 2'd0);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Triangle PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Triangle PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, TRI, 2'd0);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 5. Pulse waveform
        // =============================================================
        $display("\n===== 5. Pulse waveform =====");
        sid_write_freq(FREQ_E4, 2'd0);
        sid_write_pw(8'h80);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, PULSE | GATE, 2'd0);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Pulse PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Pulse PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, PULSE, 2'd0);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 6. Noise waveform
        // =============================================================
        $display("\n===== 6. Noise waveform =====");
        sid_write_freq(FREQ_C5, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, NOISE | GATE, 2'd0);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Noise PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Noise PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, NOISE, 2'd0);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 7. ADSR envelope — attack ramp
        // =============================================================
        $display("\n===== 7. ADSR attack ramp =====");
        sid_write_freq(FREQ_C4, 2'd0);
        sid_write_pw(8'h80);
        sid_write(REG_ATK, 8'h60, 2'd0);  // attack=6(slowest), decay=0
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);

        // Early window: measure right after gate-on (envelope still ramping)
        measure_pcm(20, cnt1);
        $display("[%0t]   Early PCM avg = %0d", $time, cnt1);

        // Late window: after envelope has had time to ramp higher
        repeat (200_000) @(posedge clk);
        measure_pcm(20, cnt2);
        $display("[%0t]   Late  PCM avg = %0d", $time, cnt2);

        test_num = test_num + 1;
        if (cnt2 > cnt1) begin
            $display("[%0t] TEST %0d PASS: ADSR attack ramp (late %0d > early %0d)", $time, test_num, cnt2, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: ADSR not ramping (late %0d <= early %0d)", $time, test_num, cnt2, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW, 2'd0);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 8. Gate release — PDM goes quiet
        // =============================================================
        $display("\n===== 8. Gate release =====");
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        $display("[%0t]   Before release: PDM count = %0d", $time, cnt1);

        sid_write(REG_WAV, SAW, 2'd0);

        repeat (30_000) @(posedge clk);
        count_pdm(5_000, cnt2);
        $display("[%0t]   After  release: PDM count = %0d", $time, cnt2);

        test_num = test_num + 1;
        if (cnt2 < cnt1) begin
            $display("[%0t] TEST %0d PASS: release reduces PDM (%0d -> %0d)", $time, test_num, cnt1, cnt2);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: release did not reduce PDM (%0d -> %0d)", $time, test_num, cnt1, cnt2);
            fail_count = fail_count + 1;
        end

        repeat (30_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 < 5) begin
            $display("[%0t] TEST %0d PASS: fully released, PDM silent (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: not fully silent after release (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        // =============================================================
        // 9. Test bit — oscillator freezes, PDM goes quiet
        // =============================================================
        $display("\n===== 9. Test bit =====");
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);
        repeat (50_000) @(posedge clk);

        count_pdm(5_000, cnt1);
        $display("[%0t]   Before test bit: PDM count = %0d", $time, cnt1);

        sid_write(REG_WAV, SAW | GATE | TEST, 2'd0);
        repeat (10_000) @(posedge clk);

        count_pdm(5_000, cnt2);
        $display("[%0t]   With test bit:   PDM count = %0d", $time, cnt2);

        test_num = test_num + 1;
        if (cnt2 < cnt1) begin
            $display("[%0t] TEST %0d PASS: test bit reduces PDM (%0d -> %0d)", $time, test_num, cnt1, cnt2);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: test bit did not reduce PDM (%0d -> %0d)", $time, test_num, cnt1, cnt2);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW, 2'd0);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 10. Waveform combining — SAW + TRI
        // =============================================================
        $display("\n===== 10. Waveform combining (SAW+TRI) =====");
        sid_write_freq(FREQ_C4, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | TRI | GATE, 2'd0);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: SAW+TRI combined PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: SAW+TRI combined PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW | TRI, 2'd0);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 11. Multiple notes — play different frequencies
        // =============================================================
        $display("\n===== 11. Multiple notes =====");
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);

        sid_write_freq(FREQ_C4, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);
        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Note C4 (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Note C4 (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write_freq(FREQ_E4, 2'd0);
        repeat (20_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Note E4 (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Note E4 (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write_freq(FREQ_G4, 2'd0);
        repeat (20_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Note G4 (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Note G4 (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write_freq(FREQ_C5, 2'd0);
        repeat (20_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Note C5 (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Note C5 (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW, 2'd0);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 12. Voice 2 sawtooth — independent PDM output
        // =============================================================
        $display("\n===== 12. Voice 2 sawtooth =====");
        sid_write(REG_WAV, 8'h00, 2'd0);
        repeat (30_000) @(posedge clk);

        sid_write_freq(FREQ_C4, 2'd1);
        sid_write_pw(8'h80);
        sid_write(REG_ATK, 8'h00, 2'd1);
        sid_write(REG_SUS, 8'h0F, 2'd1);
        sid_write(REG_WAV, SAW | GATE, 2'd1);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Voice 2 sawtooth PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Voice 2 sawtooth PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW, 2'd1);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 13. Both voices playing simultaneously
        // =============================================================
        $display("\n===== 13. Both voices simultaneous =====");
        sid_write_freq(FREQ_C4, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);

        sid_write_freq(FREQ_E4, 2'd1);
        sid_write(REG_ATK, 8'h00, 2'd1);
        sid_write(REG_SUS, 8'h0F, 2'd1);
        sid_write(REG_WAV, TRI | GATE, 2'd1);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Both voices PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Both voices PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW, 2'd0);
        sid_write(REG_WAV, TRI, 2'd1);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 14. Voice 3 sawtooth — independent PDM output
        // =============================================================
        $display("\n===== 14. Voice 3 sawtooth =====");
        sid_write(REG_WAV, 8'h00, 2'd0);
        sid_write(REG_WAV, 8'h00, 2'd1);
        repeat (30_000) @(posedge clk);

        sid_write_freq(FREQ_G4, 2'd2);
        sid_write_pw(8'h80);
        sid_write(REG_ATK, 8'h00, 2'd2);
        sid_write(REG_SUS, 8'h0F, 2'd2);
        sid_write(REG_WAV, SAW | GATE, 2'd2);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Voice 3 sawtooth PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Voice 3 sawtooth PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW, 2'd2);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // 15. All three voices playing simultaneously
        // =============================================================
        $display("\n===== 15. All three voices simultaneous =====");
        sid_write_freq(FREQ_C4, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);

        sid_write_freq(FREQ_E4, 2'd1);
        sid_write(REG_ATK, 8'h00, 2'd1);
        sid_write(REG_SUS, 8'h0F, 2'd1);
        sid_write(REG_WAV, TRI | GATE, 2'd1);

        sid_write_freq(FREQ_G4, 2'd2);
        sid_write(REG_ATK, 8'h00, 2'd2);
        sid_write(REG_SUS, 8'h0F, 2'd2);
        sid_write(REG_WAV, PULSE | GATE, 2'd2);

        repeat (50_000) @(posedge clk);
        count_pdm(5_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: All three voices PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: All three voices PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW, 2'd0);
        sid_write(REG_WAV, TRI, 2'd1);
        sid_write(REG_WAV, PULSE, 2'd2);
        repeat (30_000) @(posedge clk);

        // =============================================================
        // Summary
        // =============================================================
        $display("\n====================================");
        $display("  RESULTS: %0d PASSED, %0d FAILED (of %0d)", pass_count, fail_count, test_num);
        $display("====================================\n");

        $finish;
    end

    //==========================================================================
    // Timeout watchdog — 10 seconds (slower clock needs longer timeout)
    //==========================================================================
    initial begin
        #10_000_000_000;
        $display("\nERROR: Simulation timeout!");
        $finish;
    end

endmodule
