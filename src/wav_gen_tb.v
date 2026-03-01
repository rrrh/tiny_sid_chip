`timescale 1ns / 1ps
//==============================================================================
// WAV generation testbench — 3-voice SID (saw + pulse + tri)
// Captures mix_out at 1 MHz (slot 4) and writes hex samples to file.
//==============================================================================

module wav_gen_tb;

    reg clk;
    initial clk = 0;
    always #100 clk = ~clk;  // 5 MHz

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    localparam [2:0] REG_FREQ = 3'd0, REG_PW = 3'd2,
                     REG_ATK  = 3'd4, REG_SUS = 3'd5, REG_WAV = 3'd6;

    localparam [7:0] GATE = 8'h01, TRI = 8'h10, SAW = 8'h20, PULSE = 8'h40;

    task sid_write;
        input [2:0] addr; input [7:0] data; input [1:0] voice;
        begin
            ui_in[2:0] <= addr; ui_in[4:3] <= voice; uio_in <= data;
            @(posedge clk);
            ui_in[7] <= 1'b1; @(posedge clk);
            ui_in[7] <= 1'b0; @(posedge clk);
        end
    endtask

    // Capture mix_out during slot 4 (after slot 3 latch)
    integer sample_file;
    integer sample_count;
    localparam integer TOTAL_SAMPLES = 2_000_000;  // 2 seconds at 1 MHz

    initial begin
        sample_file = $fopen("sid_samples.hex", "w");
        if (sample_file == 0) begin
            $display("ERROR: Cannot open output file");
            $finish;
        end

        ui_in = 0; uio_in = 0; ena = 1; rst_n = 1;
        repeat (10) @(posedge clk);

        // Reset
        rst_n = 0; repeat (50) @(posedge clk);
        rst_n = 1; repeat (50) @(posedge clk);

        // V0: Sawtooth C4 (~262 Hz) — freq_reg = 262 * 65536 / 1e6 ≈ 17
        sid_write(REG_FREQ, 8'd17, 2'd0);
        sid_write(REG_ATK, 8'h00, 2'd0);
        sid_write(REG_SUS, 8'h0F, 2'd0);
        sid_write(REG_WAV, SAW | GATE, 2'd0);

        // V1: Pulse E4 (~330 Hz) — freq_reg ≈ 22, PW=128 (50% duty)
        sid_write(REG_FREQ, 8'd22, 2'd1);
        sid_write(REG_PW, 8'h80, 2'd1);
        sid_write(REG_ATK, 8'h00, 2'd1);
        sid_write(REG_SUS, 8'h0F, 2'd1);
        sid_write(REG_WAV, PULSE | GATE, 2'd1);

        // V2: Triangle G4 (~392 Hz) — freq_reg ≈ 26
        sid_write(REG_FREQ, 8'd26, 2'd2);
        sid_write(REG_ATK, 8'h00, 2'd2);
        sid_write(REG_SUS, 8'h0F, 2'd2);
        sid_write(REG_WAV, TRI | GATE, 2'd2);

        $display("Recording %0d samples (2 seconds at 1 MHz)...", TOTAL_SAMPLES);

        // Wait for ADSR attack to ramp up
        repeat (25_000) @(posedge clk);

        // Capture samples: one per mod-6 frame, on slot 4 (after mix latch)
        sample_count = 0;
        while (sample_count < TOTAL_SAMPLES) begin
            @(posedge clk);
            if (dut.slot == 3'd4) begin
                $fwrite(sample_file, "%02x\n", dut.mix_out);
                sample_count = sample_count + 1;
            end
        end

        $fclose(sample_file);
        $display("Done. Wrote %0d samples to sid_samples.hex", sample_count);
        $finish;
    end

    initial begin #60_000_000_000; $display("ERROR: Timeout!"); $finish; end

endmodule
