`timescale 1ns / 1ps
//==============================================================================
// SID Drum Loop Testbench — Hip-Hop Boom-Bap Beat via SPI
//==============================================================================
// Drives tt_um_sid through the SPI interface with a kick/snare/hi-hat pattern
// at 90 BPM. Kick uses triangle (~80 Hz), snare uses noise, hi-hat uses
// high-freq noise with very fast decay. PWM output is filtered through a
// 2-stage IIR low-pass and written to a 16-bit WAV.
//
// Pattern (1-bar loop, 16th-note grid):
//   Step: 1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16
//   Kick: X  .  .  .  .  .  .  X  .  .  X  .  .  .  .  .
//   Snr:  .  .  .  .  X  .  .  .  .  .  .  .  X  .  .  .
//   HiH:  .  .  X  .  .  .  X  .  .  .  .  X  .  .  X  .
//==============================================================================

module sid_drum_loop_tb;

    //--------------------------------------------------------------------------
    // Timing parameters
    //--------------------------------------------------------------------------
    localparam CLK_PERIOD        = 20;           // 50 MHz
    localparam STEP_CLOCKS       = 8_333_333;    // 16th note at 90 BPM (~167 ms)
    localparam KICK_GATE_CLOCKS  = 2_500_000;    // 50 ms gate-on for kick
    localparam SNARE_GATE_CLOCKS = 1_500_000;    // 30 ms gate-on for snare
    localparam HIHAT_GATE_CLOCKS = 750_000;      // 15 ms gate-on for hi-hat

    localparam NUM_STEPS         = 16;           // 1 bar × 16 steps
    localparam SETTLE_CLOCKS     = 1_000_000;    // 20 ms filter settling

    //--------------------------------------------------------------------------
    // WAV parameters
    //--------------------------------------------------------------------------
    localparam WAV_SAMPLE_DIV    = 1134;         // 50 MHz / 44.1 kHz
    localparam NUM_WAV_SAMPLES   = 120000;       // ~2.72 s at 44.1 kHz
    localparam ALPHA             = 165;          // IIR filter coefficient

    //--------------------------------------------------------------------------
    // Drum sound parameters
    //--------------------------------------------------------------------------
    // Kick: ~80 Hz triangle, fast attack, medium decay, no sustain
    //   freq = round(80 * 2^24 / 50e6) = 27
    localparam [15:0] KICK_FREQ  = 16'd27;
    localparam [7:0]  KICK_ATK   = 8'h40;       // attack=0 (instant), decay=4 (~42 ms)
    localparam [7:0]  KICK_SUS   = 8'h00;       // sustain=0, release=0 (fast)
    localparam [7:0]  KICK_PW    = 8'h80;
    localparam [7:0]  KICK_WAV   = 8'h21;       // sawtooth + gate

    // Snare: noise, fast attack, short decay, slight sustain for body
    //   freq = round(5000 * 2^24 / 50e6) = 1678 (fast LFSR clocking)
    localparam [15:0] SNARE_FREQ = 16'd1678;
    localparam [7:0]  SNARE_ATK  = 8'h30;       // attack=0, decay=3 (~21 ms)
    localparam [7:0]  SNARE_SUS  = 8'h10;       // sustain=0, release=1 (~5 ms)
    localparam [7:0]  SNARE_WAV  = 8'h81;       // noise + gate

    // Hi-hat: high-freq noise, very fast attack & decay, no sustain
    //   freq = round(12000 * 2^24 / 50e6) = 4027 (very fast LFSR clocking)
    localparam [15:0] HIHAT_FREQ = 16'd4027;
    localparam [7:0]  HIHAT_ATK  = 8'h10;       // attack=0 (instant), decay=1 (~5 ms)
    localparam [7:0]  HIHAT_SUS  = 8'h00;       // sustain=0, release=0 (fast)
    localparam [7:0]  HIHAT_WAV  = 8'h81;       // noise + gate

    // Gate-off: write waveform register without gate bit
    localparam [7:0]  GATE_OFF   = 8'h00;

    //--------------------------------------------------------------------------
    // SPI constants
    //--------------------------------------------------------------------------
    localparam [2:0] REG_FREQ_LO = 3'd0,
                     REG_FREQ_HI = 3'd1,
                     REG_PW_LO   = 3'd2,
                     REG_ATK     = 3'd4,
                     REG_SUS     = 3'd5,
                     REG_WAV     = 3'd6;
    localparam SPI_HP = 100;  // 5 MHz SPI clock (100 ns half-period)

    //--------------------------------------------------------------------------
    // Pattern: 0 = rest, 1 = kick, 2 = snare, 3 = hi-hat
    // Boom-bap: K.H.S.H.K.KHS.H.
    //--------------------------------------------------------------------------
    reg [1:0] pattern [0:15];
    initial begin
        pattern[0]  = 2'd1;  // Kick
        pattern[1]  = 2'd0;
        pattern[2]  = 2'd3;  // Hi-hat
        pattern[3]  = 2'd0;
        pattern[4]  = 2'd2;  // Snare
        pattern[5]  = 2'd0;
        pattern[6]  = 2'd3;  // Hi-hat
        pattern[7]  = 2'd1;  // Kick
        pattern[8]  = 2'd0;
        pattern[9]  = 2'd0;
        pattern[10] = 2'd1;  // Kick
        pattern[11] = 2'd3;  // Hi-hat
        pattern[12] = 2'd2;  // Snare
        pattern[13] = 2'd0;
        pattern[14] = 2'd3;  // Hi-hat
        pattern[15] = 2'd0;
    end

    //--------------------------------------------------------------------------
    // Clock
    //--------------------------------------------------------------------------
    reg clk;
    initial clk = 0;
    always #(CLK_PERIOD / 2) clk = ~clk;

    //--------------------------------------------------------------------------
    // DUT: tt_um_sid
    //--------------------------------------------------------------------------
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

    wire pwm_out = uio_out[7];

    //--------------------------------------------------------------------------
    // 2-stage IIR low-pass filter on PWM output
    //--------------------------------------------------------------------------
    reg  [31:0] filter_acc1;
    reg  [31:0] filter_acc2;
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

    // Unsigned filter → signed, halved for DC-blocker headroom
    // filter_acc2[31:17] is 15-bit unsigned (0..32767)
    // Subtract midpoint: -16384..+16383, fits in signed 16-bit
    wire signed [15:0] raw_sample;
    assign raw_sample = {1'b0, filter_acc2[31:17]} - 16'd16384;

    //--------------------------------------------------------------------------
    // SPI bit-bang write (CPOL=0, CPHA=0, MSB first)
    //--------------------------------------------------------------------------
    task spi_write;
        input [2:0] addr;
        input [7:0] data;
        reg   [15:0] word;
        integer i;
        begin
            word = {addr, 5'b00000, data};
            ui_in[0] <= 1'b0;  // CS_n low
            #(SPI_HP);
            for (i = 15; i >= 0; i = i - 1) begin
                ui_in[2] <= word[i];
                #(SPI_HP);
                ui_in[1] <= 1'b1;  // rising edge — slave samples
                #(SPI_HP);
                ui_in[1] <= 1'b0;
            end
            #(SPI_HP);
            ui_in[0] <= 1'b1;  // CS_n high
            #(SPI_HP);
        end
    endtask

    task sid_write;
        input [2:0] idx;
        input [7:0] val;
        begin
            spi_write(idx, val);
            repeat (10) @(posedge clk);
        end
    endtask

    task sid_write_freq;
        input [15:0] freq;
        begin
            sid_write(REG_FREQ_LO, freq[7:0]);
            sid_write(REG_FREQ_HI, freq[15:8]);
        end
    endtask

    //--------------------------------------------------------------------------
    // Drum trigger tasks
    //--------------------------------------------------------------------------
    task trigger_kick;
        begin
            sid_write_freq(KICK_FREQ);
            sid_write(REG_PW_LO, KICK_PW);
            sid_write(REG_ATK, KICK_ATK);
            sid_write(REG_SUS, KICK_SUS);
            sid_write(REG_WAV, KICK_WAV);
        end
    endtask

    task trigger_snare;
        begin
            sid_write_freq(SNARE_FREQ);
            sid_write(REG_ATK, SNARE_ATK);
            sid_write(REG_SUS, SNARE_SUS);
            sid_write(REG_WAV, SNARE_WAV);
        end
    endtask

    task trigger_hihat;
        begin
            sid_write_freq(HIHAT_FREQ);
            sid_write(REG_ATK, HIHAT_ATK);
            sid_write(REG_SUS, HIHAT_SUS);
            sid_write(REG_WAV, HIHAT_WAV);
        end
    endtask

    task gate_off;
        begin
            sid_write(REG_WAV, GATE_OFF);
        end
    endtask

    //--------------------------------------------------------------------------
    // WAV file writer
    //--------------------------------------------------------------------------
    integer wav_fd;
    integer wav_sample_count;
    integer wav_clk_count;

    task write_wav_header;
        input integer fd;
        input integer num_samples;
        integer data_size;
        integer file_size;
        begin
            data_size = num_samples * 2;
            file_size = 36 + data_size;
            $fwrite(fd, "%c%c%c%c", 8'h52, 8'h49, 8'h46, 8'h46);  // "RIFF"
            $fwrite(fd, "%c%c%c%c",
                file_size[7:0], file_size[15:8],
                file_size[23:16], file_size[31:24]);
            $fwrite(fd, "%c%c%c%c", 8'h57, 8'h41, 8'h56, 8'h45);  // "WAVE"
            $fwrite(fd, "%c%c%c%c", 8'h66, 8'h6D, 8'h74, 8'h20);  // "fmt "
            $fwrite(fd, "%c%c%c%c", 8'h10, 8'h00, 8'h00, 8'h00);  // chunk size 16
            $fwrite(fd, "%c%c", 8'h01, 8'h00);                      // PCM
            $fwrite(fd, "%c%c", 8'h01, 8'h00);                      // mono
            $fwrite(fd, "%c%c%c%c", 8'h44, 8'hAC, 8'h00, 8'h00);  // 44100 Hz
            $fwrite(fd, "%c%c%c%c", 8'h88, 8'h58, 8'h01, 8'h00);  // byte rate
            $fwrite(fd, "%c%c", 8'h02, 8'h00);                      // block align
            $fwrite(fd, "%c%c", 8'h10, 8'h00);                      // 16 bit
            $fwrite(fd, "%c%c%c%c", 8'h64, 8'h61, 8'h74, 8'h61);  // "data"
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
    // WAV recording process — runs concurrently with pattern sequencer
    //--------------------------------------------------------------------------
    // DC-blocking high-pass filter at WAV sample rate (44.1 kHz).
    // y[n] = x[n] - x[n-1] + R * y[n-1],  R = 0.997 (~20 Hz cutoff)
    // Fixed-point: R = 65339 / 65536  (16 fractional bits)
    //--------------------------------------------------------------------------
    localparam signed [31:0] DC_BLOCK_R = 65339;

    reg recording;
    initial recording = 0;

    reg signed [31:0] dc_prev_x;
    reg signed [31:0] dc_prev_y;

    initial begin
        dc_prev_x = 0;
        dc_prev_y = 0;
    end

    always @(posedge clk) begin
        if (recording && wav_sample_count < NUM_WAV_SAMPLES) begin
            wav_clk_count = wav_clk_count + 1;
            if (wav_clk_count >= WAV_SAMPLE_DIV) begin
                wav_clk_count = 0;

                // DC-blocking HPF: y = (x - prev_x) + R * prev_y
                dc_prev_y = (raw_sample - dc_prev_x) +
                            ((DC_BLOCK_R * dc_prev_y) >>> 16);
                dc_prev_x = raw_sample;

                // Clamp to signed 16-bit
                if (dc_prev_y > 32767)
                    write_sample(wav_fd, 16'sd32767);
                else if (dc_prev_y < -32768)
                    write_sample(wav_fd, -16'sd32768);
                else
                    write_sample(wav_fd, dc_prev_y[15:0]);

                wav_sample_count = wav_sample_count + 1;
            end
        end
    end

    //--------------------------------------------------------------------------
    // Main simulation — pattern sequencer
    //--------------------------------------------------------------------------
    integer step;
    integer bar;
    integer step_idx;
    integer gate_clocks;
    integer remaining;

    initial begin
        $display("SID Drum Loop — Hip-Hop Boom-Bap at 90 BPM");
        $display("Pattern: K.H.S.H.K..KHS.H.");

        // Open WAV
        wav_fd = $fopen("sid_drum_loop.wav", "wb");
        if (wav_fd == 0) begin
            $display("ERROR: Cannot open sid_drum_loop.wav");
            $finish;
        end
        write_wav_header(wav_fd, NUM_WAV_SAMPLES);
        wav_sample_count = 0;
        wav_clk_count    = 0;

        // Reset
        ui_in  = 8'b0000_0001;  // CS_n=1
        uio_in = 8'b0;
        ena    = 1'b1;
        rst_n  = 1'b0;
        repeat (20) @(posedge clk);
        rst_n  = 1'b1;
        repeat (10) @(posedge clk);

        // Short settle
        $display("Settling...");
        repeat (SETTLE_CLOCKS) @(posedge clk);

        // Start recording
        recording = 1;
        $display("Recording 1 bar...");

        for (bar = 0; bar < 1; bar = bar + 1) begin
            $display("  Bar %0d", bar + 1);
            for (step = 0; step < NUM_STEPS; step = step + 1) begin
                step_idx = bar * 16 + step;

                case (pattern[step])
                    2'd1: begin
                        // Kick
                        $display("    [step %0d] KICK", step_idx + 1);
                        trigger_kick;
                        repeat (KICK_GATE_CLOCKS) @(posedge clk);
                        gate_off;
                        remaining = STEP_CLOCKS - KICK_GATE_CLOCKS;
                        repeat (remaining) @(posedge clk);
                    end
                    2'd2: begin
                        // Snare
                        $display("    [step %0d] SNARE", step_idx + 1);
                        trigger_snare;
                        repeat (SNARE_GATE_CLOCKS) @(posedge clk);
                        gate_off;
                        remaining = STEP_CLOCKS - SNARE_GATE_CLOCKS;
                        repeat (remaining) @(posedge clk);
                    end
                    2'd3: begin
                        // Hi-hat
                        $display("    [step %0d] HIHAT", step_idx + 1);
                        trigger_hihat;
                        repeat (HIHAT_GATE_CLOCKS) @(posedge clk);
                        gate_off;
                        remaining = STEP_CLOCKS - HIHAT_GATE_CLOCKS;
                        repeat (remaining) @(posedge clk);
                    end
                    default: begin
                        // Rest
                        repeat (STEP_CLOCKS) @(posedge clk);
                    end
                endcase

                if (wav_sample_count % 20000 == 0 && wav_sample_count > 0)
                    $display("    WAV: %0d / %0d samples", wav_sample_count, NUM_WAV_SAMPLES);
            end
        end

        // Let tail ring out
        $display("Recording tail...");
        repeat (5_000_000) @(posedge clk);

        // Stop recording, rewrite header with actual count
        recording = 0;
        begin : rewrite_header
            integer fseek_ret;
            fseek_ret = $fseek(wav_fd, 0, 0);
            write_wav_header(wav_fd, wav_sample_count);
        end

        $fclose(wav_fd);
        $display("Done! Wrote %0d samples to sid_drum_loop.wav", wav_sample_count);
        $finish;
    end

    //--------------------------------------------------------------------------
    // Timeout watchdog — 15 seconds sim time
    //--------------------------------------------------------------------------
    initial begin
        #15_000_000_000;
        $display("ERROR: Simulation timeout!");
        $finish;
    end

endmodule
