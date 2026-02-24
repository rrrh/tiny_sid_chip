`timescale 1ns / 1ps
//==============================================================================
// PWM Analog Output Testbench (12 MHz)
// Captures PWM pin transitions as ngspice PWL files for analog filter sim.
//
// 9 waveform captures (uo_out[0]): saw/tri/pulse x 220/440/880 Hz
// 3 filter captures (uo_out[1]): LP/HP/BP at 440 Hz sawtooth
//
// Output: tests/{name}.pwl — piecewise-linear voltage waveform
// VDD = 3.3 V, edge time = 2 ns (matches PCB I/O bank)
//==============================================================================
module pwm_analog_tb;

    // --- Parameters ---
    localparam real VDD     = 3.3;
    localparam real EDGE_NS = 2.0;
    localparam      SIM_CYCLES = 1_500_000;  // ~125 ms at 12 MHz

    // --- Clock and DUT ---
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

    wire pwm_raw      = uo_out[0];  // unfiltered PWM (mix_out)
    wire pwm_filtered  = uo_out[1];  // digitally filtered PWM

    // Pin selector: 0 = pwm_raw (uo_out[0]), 1 = pwm_filtered (uo_out[1])
    reg  capture_sel;
    wire pwm_capture = capture_sel ? pwm_filtered : pwm_raw;

    // Register addresses (same as gen_wav_tb.v)
    localparam [2:0] REG_FREQ_LO  = 3'd0,
                     REG_FREQ_HI  = 3'd1,
                     REG_PW_LO    = 3'd2,
                     REG_PW_HI    = 3'd3,
                     REG_ATK      = 3'd4,
                     REG_SUS      = 3'd5,
                     REG_WAV      = 3'd6;

    localparam [2:0] REG_FC_LO    = 3'd0,
                     REG_FC_HI    = 3'd1,
                     REG_RES_FILT = 3'd2,
                     REG_MODE_VOL = 3'd3;
    localparam [1:0] VOICE_FILT   = 2'd3;

    localparam       ATTACK_WAIT  = 200_000;

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
    // Reset
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
    // Capture PWM transitions from pwm_capture wire to a PWL file
    //==========================================================================
    task capture_pwl;
        input [255:0] filename;
        integer fd, cyc;
        reg     prev_pwm;
        real    t_ns;
        begin
            fd = $fopen(filename, "w");
            if (fd == 0) begin
                $display("ERROR: Cannot open %0s", filename);
                $finish;
            end

            // Write initial state
            prev_pwm = pwm_capture;
            if (prev_pwm)
                $fwrite(fd, "0n %0.3f\n", VDD);
            else
                $fwrite(fd, "0n 0\n");

            // Record transitions
            for (cyc = 0; cyc < SIM_CYCLES; cyc = cyc + 1) begin
                @(posedge clk);
                if (pwm_capture !== prev_pwm) begin
                    t_ns = $realtime;
                    if (pwm_capture) begin
                        $fwrite(fd, "%0.1fn 0\n",   t_ns);
                        $fwrite(fd, "%0.1fn %0.3f\n", t_ns + EDGE_NS, VDD);
                    end else begin
                        $fwrite(fd, "%0.1fn %0.3f\n", t_ns, VDD);
                        $fwrite(fd, "%0.1fn 0\n",     t_ns + EDGE_NS);
                    end
                    prev_pwm = pwm_capture;
                end
            end

            // Final state
            t_ns = $realtime;
            if (prev_pwm)
                $fwrite(fd, "%0.1fn %0.3f\n", t_ns, VDD);
            else
                $fwrite(fd, "%0.1fn 0\n", t_ns);

            $fclose(fd);
        end
    endtask

    //==========================================================================
    // Setup voice 0, gate, wait for attack, then capture uo_out[0] as PWL
    //==========================================================================
    task capture_waveform_pwl;
        input [7:0] freq_lo;
        input [7:0] freq_hi_val;
        input [7:0] waveform_reg;
        input [255:0] filename;
        begin
            do_reset;
            capture_sel = 0;  // select uo_out[0]

            // Configure voice 0
            sid_write(REG_FREQ_LO, freq_lo, 2'd0);
            sid_write(REG_FREQ_HI, freq_hi_val, 2'd0);
            sid_write(REG_PW_LO, 8'h00, 2'd0);
            sid_write(REG_PW_HI, 8'h08, 2'd0);  // pw=0x800 (50% duty)
            sid_write(REG_ATK, 8'h00, 2'd0);     // instant attack/decay
            sid_write(REG_SUS, 8'h0F, 2'd0);     // max sustain

            // Filter bypass: vol=15
            sid_write(REG_FC_LO, 8'h00, VOICE_FILT);
            sid_write(REG_FC_HI, 8'h00, VOICE_FILT);
            sid_write(REG_RES_FILT, 8'h00, VOICE_FILT);
            sid_write(REG_MODE_VOL, 8'h1F, VOICE_FILT);

            // Gate on
            sid_write(REG_WAV, waveform_reg, 2'd0);

            // Wait for attack ramp
            repeat (ATTACK_WAIT) @(posedge clk);

            // Capture PWM transitions
            capture_pwl(filename);
        end
    endtask

    //==========================================================================
    // Setup voice 0 saw 440 Hz + filter, capture uo_out[1] as PWL
    //==========================================================================
    task capture_filter_pwl;
        input [7:0] mode_vol_val;
        input [255:0] filename;
        begin
            do_reset;
            capture_sel = 1;  // select uo_out[1]

            // Voice 0: 440 Hz sawtooth
            sid_write(REG_FREQ_LO, 8'h24, 2'd0);
            sid_write(REG_FREQ_HI, 8'h00, 2'd0);
            sid_write(REG_ATK, 8'h00, 2'd0);
            sid_write(REG_SUS, 8'h0F, 2'd0);
            sid_write(REG_WAV, 8'h21, 2'd0);  // sawtooth + gate

            // Filter setup
            sid_write(REG_FC_LO, 8'h00, VOICE_FILT);
            sid_write(REG_FC_HI, 8'h20, VOICE_FILT);
            sid_write(REG_RES_FILT, 8'h01, VOICE_FILT);  // res=0, filt_en=V0
            sid_write(REG_MODE_VOL, mode_vol_val, VOICE_FILT);

            // Wait for attack ramp
            repeat (ATTACK_WAIT) @(posedge clk);

            // Capture PWM transitions
            capture_pwl(filename);
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
        capture_sel = 0;

        // --- 9 waveform captures: saw/tri/pulse x 220/440/880 Hz ---
        $display("Generating: saw_220.pwl");
        capture_waveform_pwl(8'h12, 8'h00, 8'h21, "tests/saw_220.pwl");
        $display("Generating: saw_440.pwl");
        capture_waveform_pwl(8'h24, 8'h00, 8'h21, "tests/saw_440.pwl");
        $display("Generating: saw_880.pwl");
        capture_waveform_pwl(8'h48, 8'h00, 8'h21, "tests/saw_880.pwl");

        $display("Generating: tri_220.pwl");
        capture_waveform_pwl(8'h12, 8'h00, 8'h11, "tests/tri_220.pwl");
        $display("Generating: tri_440.pwl");
        capture_waveform_pwl(8'h24, 8'h00, 8'h11, "tests/tri_440.pwl");
        $display("Generating: tri_880.pwl");
        capture_waveform_pwl(8'h48, 8'h00, 8'h11, "tests/tri_880.pwl");

        $display("Generating: pulse_220.pwl");
        capture_waveform_pwl(8'h12, 8'h00, 8'h41, "tests/pulse_220.pwl");
        $display("Generating: pulse_440.pwl");
        capture_waveform_pwl(8'h24, 8'h00, 8'h41, "tests/pulse_440.pwl");
        $display("Generating: pulse_880.pwl");
        capture_waveform_pwl(8'h48, 8'h00, 8'h41, "tests/pulse_880.pwl");

        // --- 3 filter captures at 440 Hz sawtooth ---
        $display("Generating: filter_lp.pwl");
        capture_filter_pwl(8'h1F, "tests/filter_lp.pwl");
        $display("Generating: filter_hp.pwl");
        capture_filter_pwl(8'h4F, "tests/filter_hp.pwl");
        $display("Generating: filter_bp.pwl");
        capture_filter_pwl(8'h2F, "tests/filter_bp.pwl");

        $display("All PWL generation complete.");
        $finish;
    end

endmodule
