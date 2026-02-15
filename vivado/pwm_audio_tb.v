`timescale 1ns / 1ps
//==============================================================================
// PWM Audio Testbench
//==============================================================================
// Generates a 440 Hz sine wave, feeds it into pwm_audio, simulates R/C
// low-pass filter recovery, and saves the result as a 16-bit mono PCM WAV file.
//==============================================================================

module pwm_audio_tb;

    //--------------------------------------------------------------------------
    // Parameters
    //--------------------------------------------------------------------------
    localparam CLK_PERIOD    = 20;        // 50 MHz clock → 20 ns period
    localparam PWM_PERIOD    = 255;       // PWM cycle length in clocks (8-bit)
    localparam SETTLE_CLOCKS = 5_000_000;  // 100 ms filter settling time
    localparam SIM_CLOCKS    = 30_000_000; // settle + 0.5 s recording
    localparam WAV_SAMPLE_DIV = 1134;     // 50 MHz / 44.1 kHz ≈ 1134
    localparam NUM_WAV_SAMPLES = 22050;   // ~0.5 s at 44.1 kHz
    // Phase accumulator: 24-bit (8.16 fixed point)
    // fs_pwm = 50e6 / 255 ≈ 196078 Hz
    // Increment per PWM sample = 256 * 440 / 196078 ≈ 0.575
    // In 16-bit fractional: 0.575 * 65536 = 37683
    localparam PHASE_INC     = 37683;
    // IIR filter alpha: ~20 kHz cutoff at 50 MHz → 2*pi*20000/50e6 ≈ 0.00251
    // In 16-bit fixed point: 0.00251 * 65536 ≈ 165
    // Two cascaded stages give -40 dB/decade rolloff above 20 kHz
    localparam ALPHA         = 165;

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
    // Sine lookup table (256 entries, 8-bit unsigned, centered at 128)
    //--------------------------------------------------------------------------
    reg [7:0] sine_lut [0:255];
    integer i;

    initial begin
        for (i = 0; i < 256; i = i + 1) begin
            sine_lut[i] = 128 + $rtoi(127.0 * $sin(2.0 * 3.14159265358979 * i / 256.0));
        end
    end

    //--------------------------------------------------------------------------
    // Phase accumulator and sample generation
    //--------------------------------------------------------------------------
    reg [23:0] phase_acc;  // 8.16 fixed point
    reg [7:0]  pwm_count;
    reg [7:0]  audio_sample;
    wire        pwm_out;

    always @(posedge clk) begin
        if (!rst_n) begin
            phase_acc <= 0;
            pwm_count <= 0;
            audio_sample <= 128;
        end else begin
            pwm_count <= pwm_count + 1;
            if (pwm_count == PWM_PERIOD - 1) begin
                pwm_count <= 0;
                phase_acc <= phase_acc + PHASE_INC;
                audio_sample <= sine_lut[phase_acc[23:16]];
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
    // y[n] = y[n-1] + alpha * (x[n] - y[n-1])
    // 16.16 fixed-point accumulators to avoid precision dead zones
    // Uses === to guard against X on pwm_out before first clock after reset
    //--------------------------------------------------------------------------
    reg [31:0] filter_acc1;  // 16.16 fixed point
    reg [31:0] filter_acc2;  // 16.16 fixed point
    // PWM input: 65535 in 16.16 = 0xFFFF0000
    wire [31:0] pwm_val = (pwm_out === 1'b1) ? 32'hFFFF_0000 : 32'h0000_0000;

    // Use 48-bit intermediates to avoid overflow in diff * ALPHA
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
            // Stage 1: filter PWM input
            if (pwm_val >= filter_acc1)
                filter_acc1 <= filter_acc1 + step1[31:0];
            else
                filter_acc1 <= filter_acc1 - step1[31:0];
            // Stage 2: filter stage 1 output
            if (filter_acc1 >= filter_acc2)
                filter_acc2 <= filter_acc2 + step2[31:0];
            else
                filter_acc2 <= filter_acc2 - step2[31:0];
        end
    end

    // Extract integer part (upper 16 bits) and convert to signed
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
            data_size = num_samples * 2;  // 16-bit mono = 2 bytes/sample
            file_size = 36 + data_size;
            // "RIFF"
            $fwrite(fd, "%c%c%c%c", 8'h52, 8'h49, 8'h46, 8'h46);
            // File size - 8 (little-endian 32-bit)
            $fwrite(fd, "%c%c%c%c",
                file_size[7:0], file_size[15:8],
                file_size[23:16], file_size[31:24]);
            // "WAVE"
            $fwrite(fd, "%c%c%c%c", 8'h57, 8'h41, 8'h56, 8'h45);
            // "fmt "
            $fwrite(fd, "%c%c%c%c", 8'h66, 8'h6D, 8'h74, 8'h20);
            // Subchunk1 size = 16 (PCM)
            $fwrite(fd, "%c%c%c%c", 8'h10, 8'h00, 8'h00, 8'h00);
            // Audio format = 1 (PCM)
            $fwrite(fd, "%c%c", 8'h01, 8'h00);
            // Num channels = 1
            $fwrite(fd, "%c%c", 8'h01, 8'h00);
            // Sample rate = 44100 (0x0000AC44)
            $fwrite(fd, "%c%c%c%c", 8'h44, 8'hAC, 8'h00, 8'h00);
            // Byte rate = 44100 * 1 * 2 = 88200 (0x00015888)
            $fwrite(fd, "%c%c%c%c", 8'h88, 8'h58, 8'h01, 8'h00);
            // Block align = 2
            $fwrite(fd, "%c%c", 8'h02, 8'h00);
            // Bits per sample = 16
            $fwrite(fd, "%c%c", 8'h10, 8'h00);
            // "data"
            $fwrite(fd, "%c%c%c%c", 8'h64, 8'h61, 8'h74, 8'h61);
            // Data size (little-endian 32-bit)
            $fwrite(fd, "%c%c%c%c",
                data_size[7:0], data_size[15:8],
                data_size[23:16], data_size[31:24]);
        end
    endtask

    task write_sample;
        input integer fd;
        input signed [15:0] sample_val;
        begin
            // 16-bit signed little-endian
            $fwrite(fd, "%c%c", sample_val[7:0], sample_val[15:8]);
        end
    endtask

    //--------------------------------------------------------------------------
    // Main simulation
    //--------------------------------------------------------------------------
    initial begin
        $display("PWM Audio Testbench - 440 Hz sine wave");
        $display("Simulation: %0d clock cycles (%.3f seconds)",
                 SIM_CLOCKS, SIM_CLOCKS * 20.0e-9);

        // Open WAV file and write header
        wav_fd = $fopen("pwm_440hz.wav", "wb");
        if (wav_fd == 0) begin
            $display("ERROR: Cannot open pwm_440hz.wav for writing");
            $finish;
        end
        write_wav_header(wav_fd, NUM_WAV_SAMPLES);

        // Reset
        rst_n = 0;
        wav_sample_count = 0;
        wav_clk_count = 0;
        total_clocks = 0;
        #(CLK_PERIOD * 10);
        rst_n = 1;

        // Let filter settle before recording
        $display("Settling filter for %0d clocks...", SETTLE_CLOCKS);
        repeat (SETTLE_CLOCKS) @(posedge clk);
        total_clocks = SETTLE_CLOCKS;
        $display("Recording...");

        // Run simulation
        while (total_clocks < SIM_CLOCKS && wav_sample_count < NUM_WAV_SAMPLES) begin
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

        // Rewrite header with actual sample count
        begin : rewrite_header
            integer fseek_ret;
            fseek_ret = $fseek(wav_fd, 0, 0);
            write_wav_header(wav_fd, wav_sample_count);
        end

        $fclose(wav_fd);
        $display("Done! Wrote %0d samples to pwm_440hz.wav", wav_sample_count);
        $finish;
    end

endmodule
