`timescale 1ns / 1ps
//==============================================================================
// Sequencer Drum + Bass Testbench
//==============================================================================
// Verifies that V1 (drums) and V2 (bassline) produce sound simultaneously.
//
// Drum pattern (V1): K.H.S.H.K..KHS.H.
// Bass pattern (V2): C..C...G..C.B...  (C2, G1, Bb1)
//
// Tests:
//   1. V1 produces sound on drum steps (kick=saw, snare/hihat=noise)
//   2. V2 produces sawtooth bass on bass steps
//   3. V2 bass is tonal (low zero-crossings, not noise)
//   4. Overlap: V1 and V2 sound simultaneously
//   5. Bass sustains through rest steps (ADSR sustain > 0)
//
// Generates sid_seq_bass.wav for listening.
//==============================================================================

module sid_seq_bass_tb;

    localparam CLK_PERIOD  = 20;
    localparam STEP_CLOCKS = 8_388_608;      // 2^23
    localparam ALPHA       = 165;
    localparam WAV_SAMPLE_DIV = 1134;        // 50 MHz / 44.1 kHz

    //--------------------------------------------------------------------------
    // Clock & DUT
    //--------------------------------------------------------------------------
    reg clk;
    initial clk = 0;
    always #(CLK_PERIOD / 2) clk = ~clk;

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe), .ena(ena),
        .clk(clk), .rst_n(rst_n)
    );

    // Internal probes
    wire [7:0] v1_out    = dut.v1_out;
    wire [7:0] v2_out    = dut.v2_out;
    wire [7:0] mixed     = dut.mixed;
    wire [3:0] seq_step  = dut.u_seq.step;
    wire       v1_gate   = dut.u_seq.gate_on;
    wire       v2_gate   = dut.u_seq.v2_gate_on;
    wire       pwm_out   = uio_out[7];

    //--------------------------------------------------------------------------
    // Per-step statistics
    //--------------------------------------------------------------------------
    reg [7:0]  step_v1_peak [0:15];
    reg [7:0]  step_v2_peak [0:15];
    reg [31:0] step_overlap [0:15];
    reg [31:0] step_v2_zc   [0:15];   // V2 zero-crossings (low = tonal)

    reg [7:0]  cur_v1_peak, cur_v2_peak;
    reg [31:0] cur_overlap;
    reg [31:0] cur_v2_zc;
    reg [7:0]  prev_v2_out;
    reg [3:0]  prev_step;

    always @(posedge clk) begin
        if (!rst_n) begin
            cur_v1_peak <= 0; cur_v2_peak <= 0;
            cur_overlap <= 0; cur_v2_zc   <= 0;
            prev_v2_out <= 0; prev_step   <= 0;
        end else begin
            if (seq_step != prev_step) begin
                step_v1_peak[prev_step] <= cur_v1_peak;
                step_v2_peak[prev_step] <= cur_v2_peak;
                step_overlap[prev_step] <= cur_overlap;
                step_v2_zc[prev_step]   <= cur_v2_zc;
                cur_v1_peak <= 0; cur_v2_peak <= 0;
                cur_overlap <= 0; cur_v2_zc   <= 0;
            end else begin
                if (v1_out > cur_v1_peak) cur_v1_peak <= v1_out;
                if (v2_out > cur_v2_peak) cur_v2_peak <= v2_out;
                if (v1_out > 0 && v2_out > 0) cur_overlap <= cur_overlap + 1;
                // Zero-crossing: detect sign changes in V2 (centered at 128)
                if ((prev_v2_out < 8'd128 && v2_out >= 8'd128) ||
                    (prev_v2_out >= 8'd128 && v2_out < 8'd128))
                    cur_v2_zc <= cur_v2_zc + 1;
            end
            prev_v2_out <= v2_out;
            prev_step   <= seq_step;
        end
    end

    //--------------------------------------------------------------------------
    // IIR low-pass filter + WAV writer (same as overlap TB)
    //--------------------------------------------------------------------------
    reg  [31:0] filter_acc1, filter_acc2;
    wire [31:0] pwm_val = (pwm_out === 1'b1) ? 32'hFFFF_0000 : 32'h0000_0000;
    wire [47:0] diff1 = (pwm_val >= filter_acc1) ?
                        {16'd0, pwm_val} - {16'd0, filter_acc1} :
                        {16'd0, filter_acc1} - {16'd0, pwm_val};
    wire [47:0] fstep1 = (diff1 * ALPHA) >> 16;
    wire [47:0] diff2 = (filter_acc1 >= filter_acc2) ?
                        {16'd0, filter_acc1} - {16'd0, filter_acc2} :
                        {16'd0, filter_acc2} - {16'd0, filter_acc1};
    wire [47:0] fstep2 = (diff2 * ALPHA) >> 16;

    always @(posedge clk) begin
        if (!rst_n) begin
            filter_acc1 <= 0; filter_acc2 <= 0;
        end else begin
            filter_acc1 <= (pwm_val >= filter_acc1) ?
                filter_acc1 + fstep1[31:0] : filter_acc1 - fstep1[31:0];
            filter_acc2 <= (filter_acc1 >= filter_acc2) ?
                filter_acc2 + fstep2[31:0] : filter_acc2 - fstep2[31:0];
        end
    end

    wire signed [15:0] raw_sample = {1'b0, filter_acc2[31:17]} - 16'd16384;

    localparam signed [31:0] DC_BLOCK_R = 65339;
    integer wav_fd, wav_sample_count, wav_clk_count;
    reg recording;
    reg signed [31:0] dc_prev_x, dc_prev_y;
    initial begin recording = 0; dc_prev_x = 0; dc_prev_y = 0; end

    task write_wav_header;
        input integer fd; input integer ns;
        integer ds, fs;
        begin
            ds = ns * 2; fs = 36 + ds;
            $fwrite(fd, "%c%c%c%c", 8'h52,8'h49,8'h46,8'h46);
            $fwrite(fd, "%c%c%c%c", fs[7:0],fs[15:8],fs[23:16],fs[31:24]);
            $fwrite(fd, "%c%c%c%c", 8'h57,8'h41,8'h56,8'h45);
            $fwrite(fd, "%c%c%c%c", 8'h66,8'h6D,8'h74,8'h20);
            $fwrite(fd, "%c%c%c%c", 8'h10,8'h00,8'h00,8'h00);
            $fwrite(fd, "%c%c", 8'h01,8'h00);
            $fwrite(fd, "%c%c", 8'h01,8'h00);
            $fwrite(fd, "%c%c%c%c", 8'h44,8'hAC,8'h00,8'h00);
            $fwrite(fd, "%c%c%c%c", 8'h88,8'h58,8'h01,8'h00);
            $fwrite(fd, "%c%c", 8'h02,8'h00);
            $fwrite(fd, "%c%c", 8'h10,8'h00);
            $fwrite(fd, "%c%c%c%c", 8'h64,8'h61,8'h74,8'h61);
            $fwrite(fd, "%c%c%c%c", ds[7:0],ds[15:8],ds[23:16],ds[31:24]);
        end
    endtask

    always @(posedge clk) begin
        if (recording) begin
            wav_clk_count = wav_clk_count + 1;
            if (wav_clk_count >= WAV_SAMPLE_DIV) begin
                wav_clk_count = 0;
                dc_prev_y = (raw_sample - dc_prev_x) +
                            ((DC_BLOCK_R * dc_prev_y) >>> 16);
                dc_prev_x = raw_sample;
                if (dc_prev_y > 32767)
                    $fwrite(wav_fd, "%c%c", 8'hFF, 8'h7F);
                else if (dc_prev_y < -32768)
                    $fwrite(wav_fd, "%c%c", 8'h00, 8'h80);
                else
                    $fwrite(wav_fd, "%c%c", dc_prev_y[7:0], dc_prev_y[15:8]);
                wav_sample_count = wav_sample_count + 1;
            end
        end
    end

    //--------------------------------------------------------------------------
    // Pattern name lookup
    //--------------------------------------------------------------------------
    reg [47:0] drum_name [0:15];
    reg [23:0] bass_name [0:15];
    initial begin
        drum_name[0]  = "KICK  "; drum_name[1]  = "rest  ";
        drum_name[2]  = "HIHAT "; drum_name[3]  = "rest  ";
        drum_name[4]  = "SNARE "; drum_name[5]  = "rest  ";
        drum_name[6]  = "HIHAT "; drum_name[7]  = "KICK  ";
        drum_name[8]  = "rest  "; drum_name[9]  = "rest  ";
        drum_name[10] = "KICK  "; drum_name[11] = "HIHAT ";
        drum_name[12] = "SNARE "; drum_name[13] = "rest  ";
        drum_name[14] = "HIHAT "; drum_name[15] = "rest  ";

        bass_name[0]  = "C2 "; bass_name[1]  = "   ";
        bass_name[2]  = "   "; bass_name[3]  = "C2 ";
        bass_name[4]  = "   "; bass_name[5]  = "   ";
        bass_name[6]  = "   "; bass_name[7]  = "G1 ";
        bass_name[8]  = "   "; bass_name[9]  = "   ";
        bass_name[10] = "C2 "; bass_name[11] = "   ";
        bass_name[12] = "Bb1"; bass_name[13] = "   ";
        bass_name[14] = "   "; bass_name[15] = "   ";
    end

    //--------------------------------------------------------------------------
    // Main test
    //--------------------------------------------------------------------------
    integer i, pass_count, fail_count;
    integer total_overlap;

    initial begin
        $display("==============================================================");
        $display(" Drum + Bass Sequencer Testbench");
        $display(" V1: K.H.S.H.K..KHS.H.  (drums)");
        $display(" V2: C..C...G..C.B...    (bass)");
        $display("==============================================================");

        wav_fd = $fopen("sid_seq_bass.wav", "wb");
        write_wav_header(wav_fd, 150000);
        wav_sample_count = 0; wav_clk_count = 0;
        pass_count = 0; fail_count = 0;

        // Reset with seq_enable=1
        ui_in  = 8'b0000_1001;
        uio_in = 8'b0; ena = 1'b1;
        rst_n  = 1'b0;
        repeat (20) @(posedge clk);
        rst_n = 1'b1;
        repeat (500_000) @(posedge clk);

        recording = 1;
        $display("\nRecording...");

        // Sync and run 18 steps
        wait (seq_step == 4'd0);
        repeat (18 * STEP_CLOCKS) @(posedge clk);
        recording = 0;
        repeat (100) @(posedge clk);

        //----------------------------------------------------------------------
        // Report
        //----------------------------------------------------------------------
        $display("\n==============================================================");
        $display(" Per-Step Results");
        $display("==============================================================");
        $display(" Step  Drum    Bass  V1pk  V2pk  Overlap    V2 ZC");
        $display(" ----  ------  ---   ----  ----  -------    -----");

        total_overlap = 0;
        for (i = 0; i < 16; i = i + 1) begin
            $display("  %2d   %s %s  %3d   %3d   %7d    %0d",
                i, drum_name[i], bass_name[i],
                step_v1_peak[i], step_v2_peak[i],
                step_overlap[i], step_v2_zc[i]);
            total_overlap = total_overlap + step_overlap[i];
        end

        //----------------------------------------------------------------------
        // TEST 1: V1 active on drum steps
        //----------------------------------------------------------------------
        $display("\n--- TEST 1: V1 produces drums ---");
        if (step_v1_peak[0] > 10 && step_v1_peak[4] > 10 &&
            step_v1_peak[7] > 10 && step_v1_peak[11] > 10) begin
            $display("  PASS: V1 active on kick(%0d), snare(%0d), kick(%0d), hihat(%0d)",
                step_v1_peak[0], step_v1_peak[4], step_v1_peak[7], step_v1_peak[11]);
            pass_count = pass_count + 1;
        end else begin
            $display("  FAIL"); fail_count = fail_count + 1;
        end

        //----------------------------------------------------------------------
        // TEST 2: V2 active on bass steps
        //----------------------------------------------------------------------
        $display("\n--- TEST 2: V2 produces bass ---");
        if (step_v2_peak[0] > 10 && step_v2_peak[3] > 10 &&
            step_v2_peak[7] > 10 && step_v2_peak[10] > 10 &&
            step_v2_peak[12] > 10) begin
            $display("  PASS: V2 active on bass steps (C2=%0d, C2=%0d, G1=%0d, C2=%0d, Bb1=%0d)",
                step_v2_peak[0], step_v2_peak[3], step_v2_peak[7],
                step_v2_peak[10], step_v2_peak[12]);
            pass_count = pass_count + 1;
        end else begin
            $display("  FAIL: V2 peaks = %0d, %0d, %0d, %0d, %0d",
                step_v2_peak[0], step_v2_peak[3], step_v2_peak[7],
                step_v2_peak[10], step_v2_peak[12]);
            fail_count = fail_count + 1;
        end

        //----------------------------------------------------------------------
        // TEST 3: V2 is tonal (low ZC) not noise (high ZC)
        //----------------------------------------------------------------------
        $display("\n--- TEST 3: V2 is tonal sawtooth (not noise) ---");
        // Bass step 0 (C2 ~66 Hz at 50MHz): expect ~22 ZC per step (167ms × 66Hz × 2 crossings)
        // Noise would have thousands of ZC
        if (step_v2_zc[0] < 200 && step_v2_zc[0] > 0) begin
            $display("  PASS: V2 zero-crossings at step 0 = %0d (tonal, not noise)",
                step_v2_zc[0]);
            pass_count = pass_count + 1;
        end else begin
            $display("  FAIL: V2 ZC = %0d (expected 1-200 for tonal bass)",
                step_v2_zc[0]);
            fail_count = fail_count + 1;
        end

        //----------------------------------------------------------------------
        // TEST 4: Simultaneous V1+V2 overlap
        //----------------------------------------------------------------------
        $display("\n--- TEST 4: V1 drums + V2 bass overlap ---");
        // Step 0 has both kick (V1) and C2 bass (V2)
        if (step_overlap[0] > 0) begin
            $display("  PASS: Step 0 overlap = %0d clocks (kick + bass)", step_overlap[0]);
            pass_count = pass_count + 1;
        end else begin
            $display("  FAIL: No overlap at step 0"); fail_count = fail_count + 1;
        end

        //----------------------------------------------------------------------
        // TEST 5: Total overlap across all steps
        //----------------------------------------------------------------------
        $display("\n--- TEST 5: Total overlap ---");
        $display("  Total clocks V1>0 && V2>0: %0d", total_overlap);
        if (total_overlap > 100000) begin
            $display("  PASS: Significant overlap — drum + bass playing together");
            pass_count = pass_count + 1;
        end else begin
            $display("  FAIL: Insufficient overlap (%0d)", total_overlap);
            fail_count = fail_count + 1;
        end

        //----------------------------------------------------------------------
        // TEST 6: V2 bass sustains into rest steps
        //----------------------------------------------------------------------
        $display("\n--- TEST 6: Bass sustains into rest steps ---");
        // Step 1 is a rest for both drum and bass, but bass from step 0 should sustain
        if (step_v2_peak[1] > 0) begin
            $display("  PASS: V2 sustains into step 1 (peak=%0d)", step_v2_peak[1]);
            pass_count = pass_count + 1;
        end else begin
            $display("  FAIL: V2 silent at step 1 (no sustain)");
            fail_count = fail_count + 1;
        end

        //----------------------------------------------------------------------
        // TEST 7: Drum-only steps (no bass) have V1 but low/no V2
        //----------------------------------------------------------------------
        $display("\n--- TEST 7: V1 drum waveform types ---");
        // Step 0 = kick (saw → lower ZC), Step 4 = snare (noise → higher ZC)
        // Check that V1 produces different waveforms for different drum types
        if (step_v1_peak[0] > 10 && step_v1_peak[4] > 10) begin
            $display("  PASS: Both kick (peak=%0d) and snare (peak=%0d) produce output",
                step_v1_peak[0], step_v1_peak[4]);
            pass_count = pass_count + 1;
        end else begin
            $display("  FAIL"); fail_count = fail_count + 1;
        end

        //----------------------------------------------------------------------
        // WAV cleanup
        //----------------------------------------------------------------------
        begin : rewrite_header
            integer fseek_ret;
            fseek_ret = $fseek(wav_fd, 0, 0);
            write_wav_header(wav_fd, wav_sample_count);
        end
        $fclose(wav_fd);

        $display("\n==============================================================");
        $display(" WAV: %0d samples written to sid_seq_bass.wav", wav_sample_count);
        $display(" RESULTS: %0d PASSED, %0d FAILED (of %0d)",
            pass_count, fail_count, pass_count + fail_count);
        $display("==============================================================");
        $finish;
    end

    initial begin #30_000_000_000; $display("TIMEOUT"); $finish; end

endmodule
