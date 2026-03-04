`timescale 1ns / 1ps
//==============================================================================
// Monty on the Run — Filter Bypass Capture
//
// Drives TT6581 with Hubbard's Monty on the Run SID stimulus, filter bypassed
// (no voices routed to filter), and captures filtered_out (= mix_out) at
// ~44.1 kHz for WAV conversion.
//
// Stimulus file: preprocessed decimal format (tick addr data per line).
// Tick values are 50 MHz-referenced; converted to wall-clock ns for scheduling.
//==============================================================================
module monty_bypass_tb;

    // 24 MHz system clock (correct SID pitch: 24/24 = 1 MHz per voice)
    reg clk;
    initial clk = 0;
    always #20.833 clk = ~clk;  // ~24 MHz (41.667 ns period)

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    // Tap bypass output (= mix_out when no voices routed to filter)
    wire [7:0] bypass_out = dut.filtered_out;
    wire [7:0] dbg_mix    = dut.mix_out;

    //==========================================================================
    // Register write: 3-clock protocol (addr+data, WE rise, WE fall)
    //==========================================================================
    task sid_write;
        input [1:0] voice;
        input [2:0] addr;
        input [7:0] data;
        begin
            ui_in  = {1'b0, 2'b00, voice, addr};
            uio_in = data;
            @(posedge clk);
            ui_in[7] = 1'b1;   // WE rising edge triggers write
            @(posedge clk);
            ui_in[7] = 1'b0;   // deassert WE
            @(posedge clk);
        end
    endtask

    //==========================================================================
    // Map flat SID address (0x00–0x18) → voice_sel + reg_addr
    //
    // Register remap (SID ↔ TT6581 per-voice layout differs):
    //   SID reg 4 (waveform/gate $D404) → TT6581 reg 6
    //   SID reg 5 (attack/decay  $D405) → TT6581 reg 4
    //   SID reg 6 (sustain/rel   $D406) → TT6581 reg 5
    //   Regs 0-3 (freq, pw) are identical.
    //
    // Filter registers (0x15–0x18) are SKIPPED for bypass mode.
    //==========================================================================
    task sid_write_sid;
        input integer sid_addr;
        input integer data;
        reg [1:0] voice;
        reg [2:0] reg_addr;
        reg        skip;
        integer    voice_offset;
        begin
            skip = 0;
            if (sid_addr < 7) begin
                voice = 2'd0;
                voice_offset = sid_addr;
            end else if (sid_addr < 14) begin
                voice = 2'd1;
                voice_offset = sid_addr - 7;
            end else if (sid_addr < 21) begin
                voice = 2'd2;
                voice_offset = sid_addr - 14;
            end else begin
                skip = 1;  // filter regs or read-only: skip for bypass
                voice_offset = 0;
            end

            // Remap per-voice registers 4/5/6
            case (voice_offset)
                4: reg_addr = 3'd6;  // SID ctrl/waveform → TT6581 reg 6
                5: reg_addr = 3'd4;  // SID attack/decay  → TT6581 reg 4
                6: reg_addr = 3'd5;  // SID sustain/rel   → TT6581 reg 5
                default: reg_addr = voice_offset[2:0];
            endcase

            if (!skip)
                sid_write(voice, reg_addr, data[7:0]);
        end
    endtask

    //==========================================================================
    // Sample capture process (~44.1 kHz decimation)
    //   24 MHz / 544 = 44,117.6 Hz
    //==========================================================================
    localparam DECIM = 544;
    integer wav_fd;
    integer sample_count;
    integer decim_cnt;

    initial begin
        decim_cnt    = 0;
        sample_count = 0;
        wav_fd = $fopen("tests/monty_bypass.raw", "w");
        if (wav_fd == 0) begin
            $display("ERROR: Cannot open output file");
            $finish;
        end

        @(posedge rst_n);  // wait for reset release

        forever begin
            @(posedge clk);
            decim_cnt = decim_cnt + 1;
            if (decim_cnt >= DECIM) begin
                $fwrite(wav_fd, "%d\n", bypass_out);
                sample_count = sample_count + 1;
                decim_cnt = 0;
            end
        end
    end

    //==========================================================================
    // Main stimulus driver
    //==========================================================================
    integer stim_fd;
    integer tick_i, addr_i, data_i;
    integer scan_result;
    integer event_count;
    time    target_ns;

    initial begin
        ena    = 1;
        rst_n  = 0;
        ui_in  = 0;
        uio_in = 0;
        event_count = 0;

        // Reset sequence
        repeat (100) @(posedge clk);
        rst_n = 1;
        repeat (50) @(posedge clk);

        // Set mode_vol = 0x0F: mode=0 (no filter), vol=15
        sid_write(2'd3, 3'd3, 8'h0F);

        // Open preprocessed stimulus (decimal: tick addr data)
        stim_fd = $fopen("tests/monty_stim_dec.txt", "r");
        if (stim_fd == 0) begin
            $display("ERROR: Cannot open stimulus file tests/monty_stim_dec.txt");
            $finish;
        end

        $display("Starting Monty on the Run bypass simulation...");

        while (!$feof(stim_fd)) begin
            scan_result = $fscanf(stim_fd, "%d %d %d\n", tick_i, addr_i, data_i);
            if (scan_result == 3) begin
                // Convert 50 MHz ticks to nanoseconds: tick * 20ns
                target_ns = tick_i;
                target_ns = target_ns * 20;

                // Wait until simulation time reaches target
                while ($time < target_ns)
                    @(posedge clk);

                sid_write_sid(addr_i, data_i);
                event_count = event_count + 1;

                if (event_count % 1000 == 0)
                    $display("  T=%0t ns: %0d/%0d events, mix=%0d",
                             $time, event_count, 8550, dbg_mix);
            end
        end

        $fclose(stim_fd);
        $display("Stimulus complete: %0d events at T=%0t ns", event_count, $time);

        $display("  Filter: bypass=%0d mix_out=%0d filtered_out=%0d",
                 dut.bypass, dut.mix_out, bypass_out);

        // Run 0.5 more seconds for audio tail
        $display("Running 0.5s tail...");
        #500_000_000;

        $fclose(wav_fd);
        $display("Captured %0d samples (~%.1f seconds at 44.1 kHz)",
                 sample_count, sample_count / 44117.0);
        $finish;
    end

endmodule
