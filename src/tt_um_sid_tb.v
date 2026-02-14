`timescale 1ns / 1ps
//==============================================================================
// Comprehensive Testbench for tt_um_sid
//==============================================================================
// Tests the full TT top-level including SPI register interface, all waveform
// types, ADSR envelope behavior, PDM output activity, and edge cases.
//
// SPI Protocol: 16-bit frames, {addr[2:0], 5'b0, data[7:0]}
// Registers: 0=freq_lo, 1=freq_hi, 2=pw_lo, 3=pw_hi,
//            4=attack, 5=sustain, 6=waveform
//==============================================================================

module tt_um_sid_tb;

    //==========================================================================
    // Clock generation — 50 MHz (20 ns period)
    //==========================================================================
    reg clk;
    initial clk = 0;
    always #10 clk = ~clk;

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
    wire pdm_out = uo_out[1];

    //==========================================================================
    // PDM-to-PCM decimation filter (CIC order 1, integrate-and-dump)
    // Converts the 50 MHz 1-bit PDM to ~48.8 kHz 10-bit PCM for waveform
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
    // Constants
    //==========================================================================
    localparam [7:0] GATE  = 8'h01,
                     SYNC  = 8'h02,
                     RMOD  = 8'h04,
                     TEST  = 8'h08,
                     TRI   = 8'h10,
                     SAW   = 8'h20,
                     PULSE = 8'h40,
                     NOISE = 8'h80;

    localparam [15:0] FREQ_C4 = 16'd4291,
                      FREQ_E4 = 16'd5404,
                      FREQ_G4 = 16'd6430,
                      FREQ_C5 = 16'd8583;

    // Register addresses (16-bit SPI, 8-bit data)
    localparam [2:0] REG_FREQ_LO = 3'd0,
                     REG_FREQ_HI = 3'd1,
                     REG_PW_LO   = 3'd2,
                     REG_PW_HI   = 3'd3,
                     REG_ATK     = 3'd4,
                     REG_SUS     = 3'd5,
                     REG_WAV     = 3'd6;

    // SPI half-period: 100 ns → 5 MHz SPI clock
    localparam SPI_HP = 100;

    //==========================================================================
    // VCD dump
    //==========================================================================
    initial begin
        $dumpfile("tt_um_sid_tb.vcd");
        $dumpvars(0, tt_um_sid_tb);
    end

    //==========================================================================
    // SPI Master — bit-bang 16-bit write (CPOL=0, CPHA=0, MSB first)
    //   Word: {addr[2:0], 5'b0, data[7:0]}
    //==========================================================================
    task spi_write;
        input [2:0] addr;
        input [7:0] data;
        reg   [15:0] word;
        integer i;
        begin
            word = {addr, 5'b00000, data};

            // Assert CS_n low
            ui_in[0] <= 1'b0;
            #(SPI_HP);

            for (i = 15; i >= 0; i = i - 1) begin
                // Set MOSI while clock is low
                ui_in[2] <= word[i];
                #(SPI_HP);
                // Rising edge — slave samples
                ui_in[1] <= 1'b1;
                #(SPI_HP);
                // Falling edge
                ui_in[1] <= 1'b0;
            end

            // Deassert CS_n
            #(SPI_HP);
            ui_in[0] <= 1'b1;
            #(SPI_HP);
        end
    endtask

    //==========================================================================
    // Convenience: SPI register write + synchronizer settling
    //==========================================================================
    task sid_write;
        input [2:0] idx;
        input [7:0] val;
        begin
            spi_write(idx, val);
            repeat (10) @(posedge clk);
        end
    endtask

    //==========================================================================
    // Convenience: write a 16-bit frequency as two byte registers
    //==========================================================================
    task sid_write_freq;
        input [15:0] freq;
        begin
            sid_write(REG_FREQ_LO, freq[7:0]);
            sid_write(REG_FREQ_HI, freq[15:8]);
        end
    endtask

    //==========================================================================
    // Convenience: write a 16-bit pulse width as two byte registers
    //==========================================================================
    task sid_write_pw;
        input [15:0] pw;
        begin
            sid_write(REG_PW_LO, pw[7:0]);
            sid_write(REG_PW_HI, pw[15:8]);
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
    // Measure average PCM level over N decimated samples (~48.8 kHz rate)
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
        ui_in  = 8'b0000_0001;   // CS_n=1, CLK=0, MOSI=0
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
        if (pdm_out == 1'b0) begin
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
        // 2. SPI register write — verify PDM becomes active
        // =============================================================
        $display("\n===== 2. SPI register write =====");
        sid_write_freq(FREQ_C4);
        sid_write_pw(16'h0800);
        sid_write(REG_ATK, 8'h00);   // attack=0(fast), decay=0(fast)
        sid_write(REG_SUS, 8'h0F);   // sustain=F(max), release=0(fast)
        sid_write(REG_WAV, SAW | GATE);

        // Wait for ADSR attack to complete (rate 0: ~131k clocks)
        repeat (150_000) @(posedge clk);
        count_pdm(10_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: PDM active after SPI writes (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: PDM inactive after SPI writes (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW);
        repeat (150_000) @(posedge clk);

        // =============================================================
        // 3. Sawtooth waveform
        // =============================================================
        $display("\n===== 3. Sawtooth waveform =====");
        sid_write_freq(FREQ_C4);
        sid_write_pw(16'h0800);
        sid_write(REG_ATK, 8'h00);
        sid_write(REG_SUS, 8'h0F);
        sid_write(REG_WAV, SAW | GATE);

        repeat (150_000) @(posedge clk);
        count_pdm(20_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 50) begin
            $display("[%0t] TEST %0d PASS: Sawtooth PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Sawtooth PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW);
        repeat (150_000) @(posedge clk);

        // =============================================================
        // 4. Triangle waveform
        // =============================================================
        $display("\n===== 4. Triangle waveform =====");
        sid_write_freq(FREQ_C4);
        sid_write(REG_ATK, 8'h00);
        sid_write(REG_SUS, 8'h0F);
        sid_write(REG_WAV, TRI | GATE);

        repeat (150_000) @(posedge clk);
        count_pdm(20_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 50) begin
            $display("[%0t] TEST %0d PASS: Triangle PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Triangle PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, TRI);
        repeat (150_000) @(posedge clk);

        // =============================================================
        // 5. Pulse waveform
        // =============================================================
        $display("\n===== 5. Pulse waveform =====");
        sid_write_freq(FREQ_E4);
        sid_write_pw(16'h0800);   // 50% duty
        sid_write(REG_ATK, 8'h00);
        sid_write(REG_SUS, 8'h0F);
        sid_write(REG_WAV, PULSE | GATE);

        repeat (150_000) @(posedge clk);
        count_pdm(20_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 50) begin
            $display("[%0t] TEST %0d PASS: Pulse PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Pulse PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, PULSE);
        repeat (150_000) @(posedge clk);

        // =============================================================
        // 6. Noise waveform
        // =============================================================
        $display("\n===== 6. Noise waveform =====");
        sid_write_freq(FREQ_C5);
        sid_write(REG_ATK, 8'h00);
        sid_write(REG_SUS, 8'h0F);
        sid_write(REG_WAV, NOISE | GATE);

        repeat (150_000) @(posedge clk);
        count_pdm(20_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 50) begin
            $display("[%0t] TEST %0d PASS: Noise PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Noise PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, NOISE);
        repeat (150_000) @(posedge clk);

        // =============================================================
        // 7. ADSR envelope — attack ramp (rate 4 ≈ 42 ms)
        // =============================================================
        $display("\n===== 7. ADSR attack ramp =====");
        sid_write_freq(FREQ_C4);
        sid_write_pw(16'h0800);
        sid_write(REG_ATK, 8'h04);   // attack_rate=4, decay_rate=0
        sid_write(REG_SUS, 8'h0F);   // sustain=F, release=0
        sid_write(REG_WAV, SAW | GATE);

        // Early window — envelope still low
        repeat (100_000) @(posedge clk);
        count_pdm(50_000, cnt1);
        $display("[%0t]   Early window PDM count = %0d", $time, cnt1);

        // Late window — envelope has ramped higher
        repeat (500_000) @(posedge clk);
        count_pdm(50_000, cnt2);
        $display("[%0t]   Late  window PDM count = %0d", $time, cnt2);

        test_num = test_num + 1;
        if (cnt2 > cnt1) begin
            $display("[%0t] TEST %0d PASS: ADSR attack ramp (late %0d > early %0d)", $time, test_num, cnt2, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: ADSR not ramping (late %0d <= early %0d)", $time, test_num, cnt2, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW);
        repeat (150_000) @(posedge clk);

        // =============================================================
        // 8. Gate release — PDM goes quiet
        // =============================================================
        $display("\n===== 8. Gate release =====");
        sid_write(REG_ATK, 8'h00);
        sid_write(REG_SUS, 8'h0F);
        sid_write(REG_WAV, SAW | GATE);

        repeat (150_000) @(posedge clk);
        count_pdm(10_000, cnt1);
        $display("[%0t]   Before release: PDM count = %0d", $time, cnt1);

        // Release gate
        sid_write(REG_WAV, SAW);

        // Wait for envelope release (rate 0: ~131k clocks from max)
        repeat (200_000) @(posedge clk);
        count_pdm(10_000, cnt2);
        $display("[%0t]   After  release: PDM count = %0d", $time, cnt2);

        test_num = test_num + 1;
        if (cnt2 < cnt1) begin
            $display("[%0t] TEST %0d PASS: release reduces PDM (%0d -> %0d)", $time, test_num, cnt1, cnt2);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: release did not reduce PDM (%0d -> %0d)", $time, test_num, cnt1, cnt2);
            fail_count = fail_count + 1;
        end

        // Verify fully silent
        repeat (100_000) @(posedge clk);
        count_pdm(10_000, cnt1);
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
        sid_write(REG_ATK, 8'h00);
        sid_write(REG_SUS, 8'h0F);
        sid_write(REG_WAV, SAW | GATE);
        repeat (150_000) @(posedge clk);

        count_pdm(10_000, cnt1);
        $display("[%0t]   Before test bit: PDM count = %0d", $time, cnt1);

        // Set test bit — accumulator held at 0, waveform output = 0
        sid_write(REG_WAV, SAW | GATE | TEST);
        repeat (50_000) @(posedge clk);

        count_pdm(10_000, cnt2);
        $display("[%0t]   With test bit:   PDM count = %0d", $time, cnt2);

        test_num = test_num + 1;
        if (cnt2 < cnt1) begin
            $display("[%0t] TEST %0d PASS: test bit reduces PDM (%0d -> %0d)", $time, test_num, cnt1, cnt2);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: test bit did not reduce PDM (%0d -> %0d)", $time, test_num, cnt1, cnt2);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW);
        repeat (150_000) @(posedge clk);

        // =============================================================
        // 10. Waveform combining — SAW + TRI
        // =============================================================
        $display("\n===== 10. Waveform combining (SAW+TRI) =====");
        sid_write_freq(FREQ_C4);
        sid_write(REG_ATK, 8'h00);
        sid_write(REG_SUS, 8'h0F);
        sid_write(REG_WAV, SAW | TRI | GATE);

        repeat (150_000) @(posedge clk);
        count_pdm(20_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 50) begin
            $display("[%0t] TEST %0d PASS: SAW+TRI combined PDM active (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: SAW+TRI combined PDM inactive (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW | TRI);
        repeat (150_000) @(posedge clk);

        // =============================================================
        // 11. Multiple notes — play different frequencies
        // =============================================================
        $display("\n===== 11. Multiple notes =====");
        sid_write(REG_ATK, 8'h00);
        sid_write(REG_SUS, 8'h0F);

        // C4
        sid_write_freq(FREQ_C4);
        sid_write(REG_WAV, SAW | GATE);
        repeat (150_000) @(posedge clk);
        count_pdm(10_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Note C4 (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Note C4 (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        // E4
        sid_write_freq(FREQ_E4);
        repeat (50_000) @(posedge clk);
        count_pdm(10_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Note E4 (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Note E4 (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        // G4
        sid_write_freq(FREQ_G4);
        repeat (50_000) @(posedge clk);
        count_pdm(10_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Note G4 (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Note G4 (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        // C5
        sid_write_freq(FREQ_C5);
        repeat (50_000) @(posedge clk);
        count_pdm(10_000, cnt1);
        test_num = test_num + 1;
        if (cnt1 > 10) begin
            $display("[%0t] TEST %0d PASS: Note C5 (count=%0d)", $time, test_num, cnt1);
            pass_count = pass_count + 1;
        end else begin
            $display("[%0t] TEST %0d FAIL: Note C5 (count=%0d)", $time, test_num, cnt1);
            fail_count = fail_count + 1;
        end

        sid_write(REG_WAV, SAW);
        repeat (150_000) @(posedge clk);

        // =============================================================
        // Summary
        // =============================================================
        $display("\n====================================");
        $display("  RESULTS: %0d PASSED, %0d FAILED (of %0d)", pass_count, fail_count, test_num);
        $display("====================================\n");

        $finish;
    end

    //==========================================================================
    // Timeout watchdog — 200 ms
    //==========================================================================
    initial begin
        #200_000_000;
        $display("\nERROR: Simulation timeout!");
        $finish;
    end

endmodule
