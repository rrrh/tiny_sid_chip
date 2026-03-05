`timescale 1ns / 1ps
//==============================================================================
// ADSR Envelope Test — 440 Hz Triangle, Voice 0
//
// ADSR: slow attack (500ms), medium decay (240ms) to half sustain (0x8),
//       short sustain (~200ms), long release (2.4s)
//
// Captures filtered_out at ~44.1 kHz decimation → raw sample file.
//==============================================================================
module adsr_tri440_tb;

    reg clk;
    initial clk = 0;
    always #20.833 clk = ~clk;  // ~24 MHz

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    wire [7:0] audio_out = dut.filtered_out;

    // Internal register addresses (per-voice)
    localparam [2:0] REG_FREQ_LO = 3'd0,
                     REG_FREQ_HI = 3'd1,
                     REG_PW_LO   = 3'd2,
                     REG_PW_HI   = 3'd3,
                     REG_ATK     = 3'd4,  // attack/decay
                     REG_SUS     = 3'd5,  // sustain/release
                     REG_WAV     = 3'd6;  // waveform + gate

    // Filter/global registers (voice_sel = 3)
    localparam [2:0] REG_MODE_VOL = 3'd3;
    localparam [1:0] VOICE_FILT   = 2'd3;

    //==========================================================================
    // Register write: 3-clock protocol
    //==========================================================================
    task sid_write;
        input [2:0] addr;
        input [7:0] data;
        input [1:0] voice;
        begin
            ui_in  = {1'b0, 2'b00, voice, addr};
            uio_in = data;
            @(posedge clk);
            ui_in[7] = 1'b1;
            @(posedge clk);
            ui_in[7] = 1'b0;
            @(posedge clk);
        end
    endtask

    //==========================================================================
    // Sample capture (~44.1 kHz decimation: 24 MHz / 544)
    //==========================================================================
    localparam DECIM = 544;
    integer wav_fd, sample_count, decim_cnt;

    initial begin
        decim_cnt    = 0;
        sample_count = 0;
        wav_fd = $fopen("tests/adsr_tri440.raw", "w");
        if (wav_fd == 0) begin
            $display("ERROR: Cannot open output file");
            $finish;
        end

        @(posedge rst_n);

        forever begin
            @(posedge clk);
            decim_cnt = decim_cnt + 1;
            if (decim_cnt >= DECIM) begin
                $fwrite(wav_fd, "%d\n", audio_out);
                sample_count = sample_count + 1;
                decim_cnt = 0;
            end
        end
    end

    //==========================================================================
    // Main test sequence
    //==========================================================================
    initial begin
        ena    = 1;
        rst_n  = 0;
        ui_in  = 0;
        uio_in = 0;

        // Reset
        repeat (100) @(posedge clk);
        rst_n = 1;
        repeat (50) @(posedge clk);

        $display("=== ADSR Envelope Test: 440 Hz Triangle ===");

        // Volume = 15, no filter
        sid_write(REG_MODE_VOL, 8'h0F, VOICE_FILT);

        // Voice 0: 440 Hz frequency (0x1CD6)
        sid_write(REG_FREQ_LO, 8'hD6, 2'd0);
        sid_write(REG_FREQ_HI, 8'h1C, 2'd0);

        // Pulse width (not used for triangle, but set anyway)
        sid_write(REG_PW_LO, 8'h00, 2'd0);
        sid_write(REG_PW_HI, 8'h08, 2'd0);

        // ADSR: attack=0xA (500ms), decay=0x7 (240ms)
        sid_write(REG_ATK, 8'hA7, 2'd0);

        // Sustain=0x8 (half), release=0xB (2.4s)
        sid_write(REG_SUS, 8'h8B, 2'd0);

        // Gate ON — triangle waveform (bit 4) + gate (bit 0)
        sid_write(REG_WAV, 8'h11, 2'd0);
        $display("  Gate ON at T=%0t ns", $time);

        // Wait for attack (500ms) + decay (240ms) + short sustain (200ms) = ~940ms
        // 940ms at 24 MHz = 22,560,000 cycles
        repeat (22_560_000) @(posedge clk);

        // Gate OFF — keep triangle selected, clear gate bit
        sid_write(REG_WAV, 8'h10, 2'd0);
        $display("  Gate OFF at T=%0t ns (entering release)", $time);

        // Wait for release (2.4s) + margin = 3s
        // 3s at 24 MHz = 72,000,000 cycles
        repeat (72_000_000) @(posedge clk);

        $fclose(wav_fd);
        $display("  Captured %0d samples (~%.1f seconds at 44.1 kHz)",
                 sample_count, sample_count / 44117.0);
        $display("=== ADSR test complete ===");
        $finish;
    end

endmodule
