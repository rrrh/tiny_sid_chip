`timescale 1ns / 1ps
//==============================================================================
// WAV Generator Testbench
// Runs each voice (0-2) with each waveform (saw, tri, pulse, noise),
// captures mix_out samples at ~44.1 kHz, writes to text files.
//==============================================================================
module gen_wav_tb;

    reg clk;
    initial clk = 0;
    always #10 clk = ~clk; // 50 MHz

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    // Access internal mix_out for clean 8-bit PCM capture
    wire [7:0] mix_out = dut.mix_out;

    // Sample rate: 50 MHz / 1131 ≈ 44,208 Hz (close to 44100)
    // 1131 = 377*3; 377 mod 6 = 5, avoids LFSR aliasing
    localparam DECIM = 1131;
    localparam SAMPLES_PER_FILE = 22050; // ~0.5s per waveform
    localparam ATTACK_WAIT = 500_000;    // 10ms for ADSR attack ramp

    //==========================================================================
    // Register write task
    //==========================================================================
    task sid_write(input [2:0] addr, input [7:0] data, input [1:0] voice);
        begin
            ui_in = {1'b0, 2'b00, voice, addr};
            uio_in = data;
            @(posedge clk);
            ui_in[7] = 1'b1; // assert WE
            @(posedge clk);
            ui_in[7] = 1'b0; // deassert WE
            @(posedge clk);
        end
    endtask

    //==========================================================================
    // Configure a voice and capture audio to file
    //==========================================================================
    task capture_voice(
        input [1:0] voice,
        input [7:0] waveform_reg,
        input [255:0] filename
    );
        integer fd, i, j;
        begin
            // Reset
            rst_n = 0;
            ui_in = 0;
            uio_in = 0;
            repeat (20) @(posedge clk);
            rst_n = 1;
            repeat (10) @(posedge clk);

            // Configure voice: C4 (262 Hz), freq_reg = 262*65536/(50e6/3/16) ≈ 16
            sid_write(0, 8'h10, voice); // freq_lo = 0x10 (16 ≈ C4)
            sid_write(1, 8'h00, voice); // freq_hi = 0x00
            sid_write(2, 8'h80, voice); // pulse width = 50%
            sid_write(4, 8'h00, voice); // attack=0 (fastest), decay=0
            sid_write(5, 8'h0F, voice); // sustain=F, release=0
            sid_write(6, waveform_reg, voice); // waveform + gate

            // Wait for ADSR attack to ramp up
            repeat (ATTACK_WAIT) @(posedge clk);

            // Capture samples
            fd = $fopen(filename, "w");
            for (i = 0; i < SAMPLES_PER_FILE; i = i + 1) begin
                $fwrite(fd, "%d\n", mix_out);
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

        // Voice 0
        $display("Generating: voice0_sawtooth.raw");
        capture_voice(0, 8'h21, "voice0_sawtooth.raw");
        $display("Generating: voice0_triangle.raw");
        capture_voice(0, 8'h11, "voice0_triangle.raw");
        $display("Generating: voice0_pulse.raw");
        capture_voice(0, 8'h41, "voice0_pulse.raw");
        $display("Generating: voice0_noise.raw");
        capture_voice(0, 8'h81, "voice0_noise.raw");

        // Voice 1
        $display("Generating: voice1_sawtooth.raw");
        capture_voice(1, 8'h21, "voice1_sawtooth.raw");
        $display("Generating: voice1_triangle.raw");
        capture_voice(1, 8'h11, "voice1_triangle.raw");
        $display("Generating: voice1_pulse.raw");
        capture_voice(1, 8'h41, "voice1_pulse.raw");
        $display("Generating: voice1_noise.raw");
        capture_voice(1, 8'h81, "voice1_noise.raw");

        // Voice 2
        $display("Generating: voice2_sawtooth.raw");
        capture_voice(2, 8'h21, "voice2_sawtooth.raw");
        $display("Generating: voice2_triangle.raw");
        capture_voice(2, 8'h11, "voice2_triangle.raw");
        $display("Generating: voice2_pulse.raw");
        capture_voice(2, 8'h41, "voice2_pulse.raw");
        $display("Generating: voice2_noise.raw");
        capture_voice(2, 8'h81, "voice2_noise.raw");

        $display("All WAV generation complete.");
        $finish;
    end

endmodule
