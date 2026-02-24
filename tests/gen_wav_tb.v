`timescale 1ns / 1ps
//==============================================================================
// WAV Generator Testbench (12 MHz)
// Captures mix_out and filtered_out samples at ~44.1 kHz decimation.
//
// 9 waveform captures: saw/tri/pulse x 220/440/880 Hz
// 3 filter captures at 440 Hz sawtooth: LP, HP, BP
//==============================================================================
module gen_wav_tb;

    reg clk;
    initial clk = 0;
    always #42 clk = ~clk;  // ~12 MHz (83.33 ns period)

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    // Internal signal taps
    wire [7:0] mix_out      = dut.mix_out;
    wire [7:0] filtered_out = dut.filtered_out;

    // Decimation: 12 MHz / 272 = ~44,117 Hz sample rate
    localparam DECIM = 272;
    localparam NUM_SAMPLES = 5000;
    localparam ATTACK_WAIT = 200_000;  // ~16.7ms for ADSR attack ramp

    // Register addresses
    localparam [2:0] REG_FREQ_LO  = 3'd0,
                     REG_FREQ_HI  = 3'd1,
                     REG_PW_LO    = 3'd2,
                     REG_PW_HI    = 3'd3,
                     REG_ATK      = 3'd4,
                     REG_SUS      = 3'd5,
                     REG_WAV      = 3'd6;

    // Filter register addresses (voice_sel = 3)
    localparam [2:0] REG_FC_LO    = 3'd0,
                     REG_FC_HI    = 3'd1,
                     REG_RES_FILT = 3'd2,
                     REG_MODE_VOL = 3'd3;
    localparam [1:0] VOICE_FILT   = 2'd3;

    //==========================================================================
    // Register write task
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
    // Reset all voices and filter
    //==========================================================================
    task do_reset;
        begin
            rst_n = 0;
            ui_in = 0;
            uio_in = 0;
            repeat (50) @(posedge clk);
            rst_n = 1;
            repeat (20) @(posedge clk);
        end
    endtask

    //==========================================================================
    // Setup voice 0 with given frequency and waveform, capture mix_out
    //==========================================================================
    task capture_waveform;
        input [7:0] freq_lo;
        input [7:0] freq_hi_val;
        input [7:0] waveform_reg;
        input [255:0] filename;
        integer fd, i, j;
        begin
            do_reset;

            // Configure voice 0
            sid_write(REG_FREQ_LO, freq_lo, 2'd0);
            sid_write(REG_FREQ_HI, freq_hi_val, 2'd0);
            sid_write(REG_PW_LO, 8'h00, 2'd0);
            sid_write(REG_PW_HI, 8'h08, 2'd0);  // pw=0x800 (50% duty)
            sid_write(REG_ATK, 8'h00, 2'd0);     // instant attack/decay
            sid_write(REG_SUS, 8'h0F, 2'd0);     // max sustain, instant release

            // Filter bypass: vol=15, no filter routing
            sid_write(REG_FC_LO, 8'h00, VOICE_FILT);
            sid_write(REG_FC_HI, 8'h00, VOICE_FILT);
            sid_write(REG_RES_FILT, 8'h00, VOICE_FILT);
            sid_write(REG_MODE_VOL, 8'h1F, VOICE_FILT);  // LP, vol=15, no routing

            // Gate on
            sid_write(REG_WAV, waveform_reg, 2'd0);

            // Wait for attack
            repeat (ATTACK_WAIT) @(posedge clk);

            // Capture samples
            fd = $fopen(filename, "w");
            for (i = 0; i < NUM_SAMPLES; i = i + 1) begin
                $fdisplay(fd, "%d", mix_out);
                for (j = 0; j < DECIM; j = j + 1)
                    @(posedge clk);
            end
            $fclose(fd);
        end
    endtask

    //==========================================================================
    // Setup voice 0 sawtooth at 440 Hz, apply filter, capture filtered_out
    //==========================================================================
    task capture_filter;
        input [7:0] mode_vol_val;
        input [255:0] filename;
        integer fd, i, j;
        begin
            do_reset;

            // Voice 0: 440 Hz sawtooth
            sid_write(REG_FREQ_LO, 8'h24, 2'd0);  // freq_reg=36 -> ~440 Hz
            sid_write(REG_FREQ_HI, 8'h00, 2'd0);
            sid_write(REG_ATK, 8'h00, 2'd0);
            sid_write(REG_SUS, 8'h0F, 2'd0);
            sid_write(REG_WAV, 8'h21, 2'd0);       // sawtooth + gate

            // Filter setup
            sid_write(REG_FC_LO, 8'h00, VOICE_FILT);
            sid_write(REG_FC_HI, 8'h20, VOICE_FILT);      // fc_hi=0x20
            sid_write(REG_RES_FILT, 8'h01, VOICE_FILT);    // res=0, filt_en=V0
            sid_write(REG_MODE_VOL, mode_vol_val, VOICE_FILT);

            // Wait for attack
            repeat (ATTACK_WAIT) @(posedge clk);

            // Capture filtered output
            fd = $fopen(filename, "w");
            for (i = 0; i < NUM_SAMPLES; i = i + 1) begin
                $fdisplay(fd, "%d", filtered_out);
                for (j = 0; j < DECIM; j = j + 1)
                    @(posedge clk);
            end
            $fclose(fd);
        end
    endtask

    //==========================================================================
    // Main test sequence
    //==========================================================================
    initial begin
        ena = 1;
        rst_n = 0;
        ui_in = 0;
        uio_in = 0;

        // --- 9 waveform captures: saw/tri/pulse x 220/440/880 Hz ---
        // Frequency register values: 220 Hz -> 18, 440 Hz -> 36, 880 Hz -> 72

        // Sawtooth
        $display("Generating: saw_220.raw");
        capture_waveform(8'h12, 8'h00, 8'h21, "tests/saw_220.raw");
        $display("Generating: saw_440.raw");
        capture_waveform(8'h24, 8'h00, 8'h21, "tests/saw_440.raw");
        $display("Generating: saw_880.raw");
        capture_waveform(8'h48, 8'h00, 8'h21, "tests/saw_880.raw");

        // Triangle
        $display("Generating: tri_220.raw");
        capture_waveform(8'h12, 8'h00, 8'h11, "tests/tri_220.raw");
        $display("Generating: tri_440.raw");
        capture_waveform(8'h24, 8'h00, 8'h11, "tests/tri_440.raw");
        $display("Generating: tri_880.raw");
        capture_waveform(8'h48, 8'h00, 8'h11, "tests/tri_880.raw");

        // Pulse (50% duty)
        $display("Generating: pulse_220.raw");
        capture_waveform(8'h12, 8'h00, 8'h41, "tests/pulse_220.raw");
        $display("Generating: pulse_440.raw");
        capture_waveform(8'h24, 8'h00, 8'h41, "tests/pulse_440.raw");
        $display("Generating: pulse_880.raw");
        capture_waveform(8'h48, 8'h00, 8'h41, "tests/pulse_880.raw");

        // --- 3 filter captures at 440 Hz sawtooth ---
        $display("Generating: filter_lp.raw");
        capture_filter(8'h1F, "tests/filter_lp.raw");   // LP mode, vol=15
        $display("Generating: filter_hp.raw");
        capture_filter(8'h4F, "tests/filter_hp.raw");   // HP mode, vol=15
        $display("Generating: filter_bp.raw");
        capture_filter(8'h2F, "tests/filter_bp.raw");   // BP mode, vol=15

        $display("All waveform generation complete.");
        $finish;
    end

endmodule
