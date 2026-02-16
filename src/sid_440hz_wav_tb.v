`timescale 1ns / 1ps
//==============================================================================
// SID 440 Hz WAV Testbench
//==============================================================================
// Drives sid_top with a 440 Hz sawtooth waveform, feeds through pwm_audio,
// applies a digital low-pass filter, and writes a 16-bit mono PCM WAV file.
// This exercises the full SID voice chain including the ADSR envelope and
// sequential multiplier.
//==============================================================================

module sid_440hz_wav_tb;

    //--------------------------------------------------------------------------
    // Parameters
    //--------------------------------------------------------------------------
    localparam CLK_PERIOD     = 20;          // 50 MHz → 20 ns
    localparam SETTLE_CLOCKS  = 5_000_000;   // 100 ms filter settling
    localparam RECORD_CLOCKS  = 25_000_000;  // 0.5 s recording
    localparam WAV_SAMPLE_DIV = 1134;        // 50 MHz / 44.1 kHz ≈ 1134
    localparam NUM_WAV_SAMPLES = 22050;      // 0.5 s at 44.1 kHz
    localparam ALPHA          = 165;         // IIR filter alpha (~20 kHz cutoff)

    // SID frequency register for 440 Hz at 50 MHz:
    // The 24-bit accumulator increments by {8'b0, frequency} each clock.
    // freq_reg = round(440 * 2^24 / 50e6) = 148 → produces 441.1 Hz
    // (Note: sid_top_tb values like FREQ_C4=4291 are calibrated for the
    // original SID's ~1 MHz clock, not 50 MHz.)
    localparam FREQ_A4 = 16'd148;

    // Waveform bits
    localparam GATE  = 8'h01;
    localparam SAW   = 8'h20;
    localparam PULSE = 8'h40;

    //--------------------------------------------------------------------------
    // Clock
    //--------------------------------------------------------------------------
    reg clk;
    initial clk = 0;
    always #(CLK_PERIOD / 2) clk = ~clk;

    //--------------------------------------------------------------------------
    // DUT: sid_top → pwm_audio
    //--------------------------------------------------------------------------
    reg         rst;
    reg  [15:0] frequency;
    reg  [7:0]  duration;
    reg  [7:0]  attack;
    reg  [7:0]  sustain;
    reg  [7:0]  waveform;
    wire [7:0]  audio_out;
    wire        pwm_out;

    sid_top u_sid (
        .clk       (clk),
        .rst       (rst),
        .frequency (frequency),
        .duration  (duration),
        .attack    (attack),
        .sustain   (sustain),
        .waveform  (waveform),
        .audio_out (audio_out)
    );

    pwm_audio u_pwm (
        .clk    (clk),
        .rst_n  (~rst),
        .sample (audio_out),
        .pwm    (pwm_out)
    );

    //--------------------------------------------------------------------------
    // Digital R/C low-pass filter (two cascaded 1st-order IIR stages)
    //--------------------------------------------------------------------------
    reg [31:0] filter_acc1;
    reg [31:0] filter_acc2;
    wire [31:0] pwm_val = (pwm_out === 1'b1) ? 32'hFFFF_0000 : 32'h0000_0000;

    wire [47:0] diff1 = (pwm_val >= filter_acc1) ?
                        {16'd0, pwm_val} - {16'd0, filter_acc1} :
                        {16'd0, filter_acc1} - {16'd0, pwm_val};
    wire [47:0] step1 = (diff1 * ALPHA) >> 16;

    wire [47:0] diff2 = (filter_acc1 >= filter_acc2) ?
                        {16'd0, filter_acc1} - {16'd0, filter_acc2} :
                        {16'd0, filter_acc2} - {16'd0, filter_acc1};
    wire [47:0] step2 = (diff2 * ALPHA) >> 16;

    always @(posedge clk) begin
        if (rst) begin
            filter_acc1 <= 0;
            filter_acc2 <= 0;
        end else begin
            if (pwm_val >= filter_acc1)
                filter_acc1 <= filter_acc1 + step1[31:0];
            else
                filter_acc1 <= filter_acc1 - step1[31:0];
            if (filter_acc1 >= filter_acc2)
                filter_acc2 <= filter_acc2 + step2[31:0];
            else
                filter_acc2 <= filter_acc2 - step2[31:0];
        end
    end

    wire signed [15:0] filtered_sample;
    assign filtered_sample = filter_acc2[31:16] - 16'd32768;

    //--------------------------------------------------------------------------
    // WAV file writer
    //--------------------------------------------------------------------------
    integer wav_fd;
    integer wav_sample_count;
    integer wav_clk_count;
    integer total_clocks;

    task write_wav_header;
        input integer fd;
        input integer num_samples;
        integer data_size;
        integer file_size;
        begin
            data_size = num_samples * 2;
            file_size = 36 + data_size;
            $fwrite(fd, "%c%c%c%c", 8'h52, 8'h49, 8'h46, 8'h46);
            $fwrite(fd, "%c%c%c%c",
                file_size[7:0], file_size[15:8],
                file_size[23:16], file_size[31:24]);
            $fwrite(fd, "%c%c%c%c", 8'h57, 8'h41, 8'h56, 8'h45);
            $fwrite(fd, "%c%c%c%c", 8'h66, 8'h6D, 8'h74, 8'h20);
            $fwrite(fd, "%c%c%c%c", 8'h10, 8'h00, 8'h00, 8'h00);
            $fwrite(fd, "%c%c", 8'h01, 8'h00);
            $fwrite(fd, "%c%c", 8'h01, 8'h00);
            $fwrite(fd, "%c%c%c%c", 8'h44, 8'hAC, 8'h00, 8'h00);
            $fwrite(fd, "%c%c%c%c", 8'h88, 8'h58, 8'h01, 8'h00);
            $fwrite(fd, "%c%c", 8'h02, 8'h00);
            $fwrite(fd, "%c%c", 8'h10, 8'h00);
            $fwrite(fd, "%c%c%c%c", 8'h64, 8'h61, 8'h74, 8'h61);
            $fwrite(fd, "%c%c%c%c",
                data_size[7:0], data_size[15:8],
                data_size[23:16], data_size[31:24]);
        end
    endtask

    task write_sample;
        input integer fd;
        input signed [15:0] sample_val;
        begin
            $fwrite(fd, "%c%c", sample_val[7:0], sample_val[15:8]);
        end
    endtask

    //--------------------------------------------------------------------------
    // Main simulation
    //--------------------------------------------------------------------------
    initial begin
        $display("SID 440 Hz WAV Testbench — Sawtooth through full voice chain");

        wav_fd = $fopen("sid_440hz.wav", "wb");
        if (wav_fd == 0) begin
            $display("ERROR: Cannot open sid_440hz.wav for writing");
            $finish;
        end
        write_wav_header(wav_fd, NUM_WAV_SAMPLES);

        // Reset
        rst = 1;
        frequency = 0; duration = 0; attack = 0; sustain = 0; waveform = 0;
        wav_sample_count = 0;
        wav_clk_count = 0;
        total_clocks = 0;
        repeat (10) @(posedge clk);
        rst = 0;

        // Configure SID: 440 Hz pulse, instant attack, max sustain
        frequency = FREQ_A4;
        duration  = 8'h80;       // ~50% duty cycle
        attack    = 8'h00;       // attack=0 (instant), decay=0
        sustain   = 8'h0F;       // sustain=max, release=0
        waveform  = PULSE | GATE;

        // Let ADSR ramp up and filter settle
        $display("Settling for %0d clocks...", SETTLE_CLOCKS);
        repeat (SETTLE_CLOCKS) @(posedge clk);
        total_clocks = SETTLE_CLOCKS;
        $display("Recording...");

        // Record
        while (total_clocks < SETTLE_CLOCKS + RECORD_CLOCKS &&
               wav_sample_count < NUM_WAV_SAMPLES) begin
            @(posedge clk);
            total_clocks = total_clocks + 1;
            wav_clk_count = wav_clk_count + 1;

            if (wav_clk_count >= WAV_SAMPLE_DIV) begin
                wav_clk_count = 0;
                write_sample(wav_fd, filtered_sample);
                wav_sample_count = wav_sample_count + 1;

                if (wav_sample_count % 5000 == 0)
                    $display("  Written %0d / %0d WAV samples...",
                             wav_sample_count, NUM_WAV_SAMPLES);
            end
        end

        // Rewrite header with actual count
        begin : rewrite_header
            integer fseek_ret;
            fseek_ret = $fseek(wav_fd, 0, 0);
            write_wav_header(wav_fd, wav_sample_count);
        end

        $fclose(wav_fd);
        $display("Done! Wrote %0d samples to sid_440hz.wav", wav_sample_count);
        $finish;
    end

endmodule
