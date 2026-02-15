`timescale 1ns / 1ps
//==============================================================================
// PWM Audio Sweep Testbench
//==============================================================================
// Generates a sine wave sweeping from 0 to 15 kHz, feeds it into pwm_audio,
// simulates R/C low-pass filter recovery, and saves the result as a WAV file.
//==============================================================================

module pwm_audio_sweep_tb;

    //--------------------------------------------------------------------------
    // Parameters
    //--------------------------------------------------------------------------
    localparam CLK_PERIOD    = 20;         // 50 MHz clock → 20 ns period
    localparam PWM_PERIOD    = 4095;       // PWM cycle length in clocks
    localparam SETTLE_CLOCKS = 5_000_000;  // 100 ms filter settling time
    localparam WAV_SAMPLE_DIV = 1134;      // 50 MHz / 44.1 kHz ≈ 1134
    // 3 seconds of audio at 44.1 kHz
    localparam NUM_WAV_SAMPLES = 132300;
    // settle + 3 s recording
    localparam SIM_CLOCKS    = 155_000_000;
    // Sample rate of PWM updates
    // fs_pwm = 50e6 / 4095 ≈ 12207 Hz
    //
    // Phase increment per PWM sample for frequency f:
    //   inc = 4096 * f / fs_pwm * 4096 (in 12.12 fixed point)
    //   inc = 4096 * 4096 * f / 12207 = 1374.4 * f
    // At 15 kHz: inc = 1374.4 * 15000 = 20,616,380
    // We ramp from 0 to this value over the recording duration.
    //
    // Total PWM samples in 3 s: 3 * 12207 ≈ 36621
    // Increment step per PWM sample: 20616380 / 36621 ≈ 563

    // IIR filter alpha: ~4 kHz cutoff at 50 MHz
    // alpha = 2*pi*4000/50e6 ≈ 0.000503
    // In 16-bit fixed point: 0.000503 * 65536 ≈ 33
    // Two cascaded stages give -40 dB/decade rolloff
    localparam ALPHA         = 33;

    //--------------------------------------------------------------------------
    // Clock and reset
    //--------------------------------------------------------------------------
    reg clk;
    reg rst_n;

    initial begin
        clk = 0;
        forever #(CLK_PERIOD / 2) clk = ~clk;
    end

    //--------------------------------------------------------------------------
    // Sine lookup table (4096 entries, 12-bit unsigned, centered at 2048)
    //--------------------------------------------------------------------------
    reg [11:0] sine_lut [0:4095];
    integer i;

    initial begin
        for (i = 0; i < 4096; i = i + 1) begin
            sine_lut[i] = 2048 + $rtoi(2047.0 * $sin(2.0 * 3.14159265358979 * i / 4096.0));
        end
    end

    //--------------------------------------------------------------------------
    // Phase accumulator with swept frequency
    //--------------------------------------------------------------------------
    reg [23:0] phase_acc;      // 12.12 fixed point
    reg [31:0] phase_inc;      // current phase increment (ramps up)
    reg [11:0] pwm_count;
    reg [11:0] audio_sample;
    wire        pwm_out;

    // Frequency sweep: ramp phase_inc from 0 to 20616380 over recording
    // Increment phase_inc by 563 each PWM sample
    localparam PHASE_INC_MAX  = 20_616_380;
    localparam PHASE_INC_STEP = 563;

    always @(posedge clk) begin
        if (!rst_n) begin
            phase_acc <= 0;
            phase_inc <= 0;
            pwm_count <= 0;
            audio_sample <= 2048;
        end else begin
            pwm_count <= pwm_count + 1;
            if (pwm_count == PWM_PERIOD - 1) begin
                pwm_count <= 0;
                phase_acc <= phase_acc + phase_inc[23:0];
                audio_sample <= sine_lut[phase_acc[23:12]];
                // Ramp frequency
                if (phase_inc < PHASE_INC_MAX)
                    phase_inc <= phase_inc + PHASE_INC_STEP;
            end
        end
    end

    //--------------------------------------------------------------------------
    // DUT: pwm_audio
    //--------------------------------------------------------------------------
    pwm_audio dut (
        .clk    (clk),
        .rst_n  (rst_n),
        .sample (audio_sample),
        .pwm    (pwm_out)
    );

    //--------------------------------------------------------------------------
    // Digital R/C low-pass filter (two cascaded 1st-order IIR stages)
    // 16.16 fixed-point accumulators, ~4 kHz cutoff, -40 dB/decade rolloff
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
        if (!rst_n) begin
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
        $display("PWM Audio Sweep Testbench - 0 to 15 kHz");
        $display("Simulation: %0d clock cycles (%.3f seconds)",
                 SIM_CLOCKS, SIM_CLOCKS * 20.0e-9);

        wav_fd = $fopen("pwm_sweep.wav", "wb");
        if (wav_fd == 0) begin
            $display("ERROR: Cannot open pwm_sweep.wav for writing");
            $finish;
        end
        write_wav_header(wav_fd, NUM_WAV_SAMPLES);

        rst_n = 0;
        wav_sample_count = 0;
        wav_clk_count = 0;
        total_clocks = 0;
        #(CLK_PERIOD * 10);
        rst_n = 1;

        $display("Settling filter for %0d clocks...", SETTLE_CLOCKS);
        repeat (SETTLE_CLOCKS) @(posedge clk);
        total_clocks = SETTLE_CLOCKS;
        $display("Recording sweep...");

        while (total_clocks < SIM_CLOCKS && wav_sample_count < NUM_WAV_SAMPLES) begin
            @(posedge clk);
            total_clocks = total_clocks + 1;
            wav_clk_count = wav_clk_count + 1;

            if (wav_clk_count >= WAV_SAMPLE_DIV) begin
                wav_clk_count = 0;
                write_sample(wav_fd, filtered_sample);
                wav_sample_count = wav_sample_count + 1;

                if (wav_sample_count % 22050 == 0)
                    $display("  Written %0d / %0d WAV samples (%.1f s)...",
                             wav_sample_count, NUM_WAV_SAMPLES,
                             wav_sample_count / 44100.0);
            end
        end

        begin : rewrite_header
            integer fseek_ret;
            fseek_ret = $fseek(wav_fd, 0, 0);
            write_wav_header(wav_fd, wav_sample_count);
        end

        $fclose(wav_fd);
        $display("Done! Wrote %0d samples to pwm_sweep.wav", wav_sample_count);
        $finish;
    end

endmodule
