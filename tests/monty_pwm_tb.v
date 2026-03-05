`timescale 1ns / 1ps
//==============================================================================
// Monty on the Run — PWM Output Capture
//
// Drives SID with Hubbard's Monty on the Run stimulus (filter bypass),
// captures uo_out[0] PWM transitions as a PWL waveform file for analog filter
// simulation via sim_analog.py or ngspice pwm_filter.spice.
//
// Combines monty_bypass_tb.v stimulus driver + pwm_analog_tb.v edge capture.
//==============================================================================
module monty_pwm_tb;

    // --- Parameters ---
    localparam real VDD     = 3.3;
    localparam real EDGE_NS = 2.0;

    // --- 24 MHz system clock ---
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

    wire pwm_out = uo_out[0];  // unfiltered PWM output

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
    // Map flat SID address (0x00-0x18) -> voice_sel + reg_addr
    //
    // Register remap (SID <-> internal per-voice layout differs):
    //   SID reg 4 (waveform/gate $D404) -> internal reg 6
    //   SID reg 5 (attack/decay  $D405) -> internal reg 4
    //   SID reg 6 (sustain/rel   $D406) -> internal reg 5
    //   Regs 0-3 (freq, pw) are identical.
    //
    // Filter registers (0x15-0x18) are SKIPPED for bypass mode.
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
                4: reg_addr = 3'd6;  // SID ctrl/waveform -> internal reg 6
                5: reg_addr = 3'd4;  // SID attack/decay  -> internal reg 4
                6: reg_addr = 3'd5;  // SID sustain/rel   -> internal reg 5
                default: reg_addr = voice_offset[2:0];
            endcase

            if (!skip)
                sid_write(voice, reg_addr, data[7:0]);
        end
    endtask

    //==========================================================================
    // PWL edge-capture process
    // Monitors pwm_out (uo_out[0]) and writes each transition to PWL file.
    //==========================================================================
    integer pwl_fd;
    integer edge_count;
    reg     prev_pwm;
    real    t_ns;
    reg     capture_active;

    initial begin
        capture_active = 0;
        edge_count = 0;

        // Wait until capture is activated by main stimulus block
        wait (capture_active);

        pwl_fd = $fopen("tests/monty_pwm.pwl", "w");
        if (pwl_fd == 0) begin
            $display("ERROR: Cannot open PWL output file");
            $finish;
        end

        // Write initial state
        prev_pwm = pwm_out;
        t_ns = $realtime;
        if (prev_pwm)
            $fwrite(pwl_fd, "%0.1fn %0.3f\n", t_ns, VDD);
        else
            $fwrite(pwl_fd, "%0.1fn 0\n", t_ns);

        // Record transitions until simulation ends
        forever begin
            @(posedge clk);
            if (pwm_out !== prev_pwm) begin
                t_ns = $realtime;
                if (pwm_out) begin
                    $fwrite(pwl_fd, "%0.1fn 0\n",     t_ns);
                    $fwrite(pwl_fd, "%0.1fn %0.3f\n", t_ns + EDGE_NS, VDD);
                end else begin
                    $fwrite(pwl_fd, "%0.1fn %0.3f\n", t_ns, VDD);
                    $fwrite(pwl_fd, "%0.1fn 0\n",     t_ns + EDGE_NS);
                end
                prev_pwm = pwm_out;
                edge_count = edge_count + 1;

                if (edge_count % 1_000_000 == 0)
                    $display("  PWL: %0d M edges captured at T=%0t ns",
                             edge_count / 1_000_000, $time);
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

        // Activate PWL capture
        capture_active = 1;

        // Open preprocessed stimulus (decimal: tick addr data)
        stim_fd = $fopen("tests/monty_stim_dec.txt", "r");
        if (stim_fd == 0) begin
            $display("ERROR: Cannot open stimulus file tests/monty_stim_dec.txt");
            $finish;
        end

        $display("Starting Monty on the Run PWM capture simulation...");

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
                    $display("  T=%0t ns: %0d/%0d events",
                             $time, event_count, 8550);
            end
        end

        $fclose(stim_fd);
        $display("Stimulus complete: %0d events at T=%0t ns", event_count, $time);

        // Run 0.5 more seconds for audio tail
        $display("Running 0.5s tail...");
        #500_000_000;

        // Write final PWL state and close
        t_ns = $realtime;
        if (prev_pwm)
            $fwrite(pwl_fd, "%0.1fn %0.3f\n", t_ns, VDD);
        else
            $fwrite(pwl_fd, "%0.1fn 0\n", t_ns);
        $fclose(pwl_fd);

        $display("PWL capture complete: %0d edges written to tests/monty_pwm.pwl",
                 edge_count);
        $finish;
    end

endmodule
