`timescale 1ns / 1ps
//==============================================================================
// Monty on the Run — Full-Length PWM Decimation Capture
//
// Drives all 3 SID voices with captured stimulus, captures PWM output
// decimated to ~44.1 kHz (24 MHz / 544 = 44,117 Hz).
//
// Stimulus file: decimal format (tick addr data per line).
// Tick values are 50 MHz-referenced; converted to wall-clock ns: tick * 20.
//==============================================================================
module monty_full_tb;

    // 24 MHz system clock
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

    wire pwm_out = uo_out[0];

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
            ui_in[7] = 1'b1;   // WE rising edge
            @(posedge clk);
            ui_in[7] = 1'b0;   // deassert WE
            @(posedge clk);
        end
    endtask

    //==========================================================================
    // Map flat SID address (0x00–0x18) → voice_sel + reg_addr
    //
    // Register remap (SID ↔ this design per-voice layout):
    //   SID reg 4 (waveform/gate) → internal reg 6
    //   SID reg 5 (attack/decay)  → internal reg 4
    //   SID reg 6 (sustain/rel)   → internal reg 5
    //   Regs 0-3 (freq, pw) are identical.
    //
    // Global registers (0x15-0x18) are written to voice 3, regs 0-3.
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
            end else if (sid_addr <= 24) begin
                // Global registers: FC_LO(21)→v3r0, FC_HI(22)→v3r1,
                //                   RES_FILT(23)→v3r2, MODE_VOL(24)→v3r3
                voice = 2'd3;
                voice_offset = sid_addr - 21;
            end else begin
                skip = 1;
                voice_offset = 0;
            end

            // Remap per-voice registers 4/5/6
            if (voice != 2'd3) begin
                case (voice_offset)
                    4: reg_addr = 3'd6;  // SID ctrl/waveform → reg 6
                    5: reg_addr = 3'd4;  // SID attack/decay  → reg 4
                    6: reg_addr = 3'd5;  // SID sustain/rel   → reg 5
                    default: reg_addr = voice_offset[2:0];
                endcase
            end else begin
                reg_addr = voice_offset[2:0];  // global regs: direct mapping
            end

            if (!skip)
                sid_write(voice, reg_addr, data[7:0]);
        end
    endtask

    //==========================================================================
    // PWM decimation capture (~44.1 kHz)
    //   Count high cycles over 544-clock windows.
    //   Output value = count of clocks where PWM was high (0–544).
    //   Scaled to 0–255 range in post-processing.
    //==========================================================================
    localparam DECIM = 544;
    integer wav_fd;
    integer sample_count;
    integer decim_cnt;
    integer pwm_high_cnt;

    initial begin
        decim_cnt     = 0;
        pwm_high_cnt  = 0;
        sample_count  = 0;
        wav_fd = $fopen("tests/monty_full_pwm.raw", "w");
        if (wav_fd == 0) begin
            $display("ERROR: Cannot open output file");
            $finish;
        end

        @(posedge rst_n);  // wait for reset release

        forever begin
            @(posedge clk);
            if (pwm_out) pwm_high_cnt = pwm_high_cnt + 1;
            decim_cnt = decim_cnt + 1;
            if (decim_cnt >= DECIM) begin
                $fwrite(wav_fd, "%d\n", pwm_high_cnt);
                sample_count = sample_count + 1;
                decim_cnt = 0;
                pwm_high_cnt = 0;
            end
        end
    end

    //==========================================================================
    // Main stimulus driver
    //==========================================================================
    integer stim_fd;
    real    tick_r;
    integer addr_i, data_i;
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

        // Open stimulus (decimal: tick addr data)
        stim_fd = $fopen("tests/monty_full_stim.txt", "r");
        if (stim_fd == 0) begin
            $display("ERROR: Cannot open stimulus file tests/monty_full_stim.txt");
            $finish;
        end

        $display("Starting Monty on the Run full simulation (PWM capture)...");

        while (!$feof(stim_fd)) begin
            scan_result = $fscanf(stim_fd, "%f %d %d\n", tick_r, addr_i, data_i);
            if (scan_result == 3) begin
                // Convert 50 MHz ticks to nanoseconds: tick * 20ns
                // Use real to avoid 32-bit integer overflow (ticks exceed 2^31)
                target_ns = tick_r * 20.0;

                // Wait until simulation time reaches target
                while ($time < target_ns)
                    @(posedge clk);

                sid_write_sid(addr_i, data_i);
                event_count = event_count + 1;

                if (event_count % 5000 == 0)
                    $display("  T=%0t ns (%0d s): %0d events",
                             $time, $time / 1_000_000_000, event_count);
            end
        end

        $fclose(stim_fd);
        $display("Stimulus complete: %0d events at T=%0t ns", event_count, $time);

        // Run 1s tail for audio decay
        $display("Running 1s tail...");
        #1_000_000_000;

        $fclose(wav_fd);
        $display("Captured %0d samples (~%.1f seconds at 44.1 kHz)",
                 sample_count, sample_count / 44117.0);
        $finish;
    end

endmodule
