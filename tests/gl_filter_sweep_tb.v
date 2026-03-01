`timescale 1ns / 1ps
//==============================================================================
// Gate-Level Testbench: 440 Hz Sawtooth Through LP/HP/BP at Two Cutoffs
//
// 6 captures × 0.25s each:
//   LP @ low fc, LP @ high fc,
//   HP @ low fc, HP @ high fc,
//   BP @ low fc, BP @ high fc
//
// fc mapping (3-bit alpha1 = fc[10:8]):
//   Low cutoff:  fc_hi = 0x20 → alpha1 = 1 (relative ~220 Hz)
//   High cutoff: fc_hi = 0x60 → alpha1 = 3 (relative ~660 Hz)
//
// Usage (GL):
//   iverilog -o tests/filter_sweep_gl -g2012 -DGL_TEST -DFUNCTIONAL -DSIM \
//     -I src patched_stdcell.v gate_level_netlist.v tests/gl_filter_sweep_tb.v
//   vvp tests/filter_sweep_gl
//==============================================================================
module gl_filter_sweep_tb;

    localparam real VDD     = 3.3;
    localparam real EDGE_NS = 2.0;
    localparam CAPTURE_CYCLES = 3_000_000;  // 0.25s at 12 MHz
    localparam ATTACK_WAIT    = 200_000;    // ~17 ms

    // --- Clock and DUT ---
    reg clk;
    initial clk = 0;
    always #42 clk = ~clk;  // ~12 MHz

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    wire pwm_out = uo_out[0];

    // Register addresses
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

    // Filter mode_vol values: mode[6:4] | vol[3:0]
    //   LP = mode bit 0 → mode_vol = 8'h1F
    //   BP = mode bit 1 → mode_vol = 8'h2F
    //   HP = mode bit 2 → mode_vol = 8'h4F
    localparam [7:0] MODE_LP = 8'h1F,
                     MODE_BP = 8'h2F,
                     MODE_HP = 8'h4F;

    // Cutoff register values (fc_hi sets alpha1 = fc[10:8])
    localparam [7:0] FC_LO_CUT = 8'h20,  // alpha1 = 1 (low cutoff, ~220 Hz relative)
                     FC_HI_CUT = 8'h60;  // alpha1 = 3 (high cutoff, ~660 Hz relative)

    //==========================================================================
    // Register write (negedge-aligned for GL compatibility)
    //==========================================================================
    task sid_write;
        input [2:0] addr;
        input [7:0] data;
        input [1:0] voice;
        begin
            @(negedge clk);
            ui_in  = {1'b0, 2'b00, voice, addr};
            uio_in = data;
            @(negedge clk);
            ui_in[7] = 1'b1;
            @(negedge clk);
            @(negedge clk);
            ui_in[7] = 1'b0;
            @(negedge clk);
        end
    endtask

    //==========================================================================
    // PWL capture
    //==========================================================================
    integer pwl_fd;
    reg     prev_pwm;

    task pwl_open;
        input [255:0] filename;
        begin
            pwl_fd = $fopen(filename, "w");
            if (pwl_fd == 0) begin
                $display("ERROR: Cannot open %0s", filename);
                $finish;
            end
            prev_pwm = pwm_out;
            if (prev_pwm)
                $fwrite(pwl_fd, "0n %0.3f\n", VDD);
            else
                $fwrite(pwl_fd, "0n 0\n");
        end
    endtask

    task pwl_sample;
        begin
            if (pwm_out !== prev_pwm) begin
                if (pwm_out) begin
                    $fwrite(pwl_fd, "%0.1fn 0\n",   $realtime);
                    $fwrite(pwl_fd, "%0.1fn %0.3f\n", $realtime + EDGE_NS, VDD);
                end else begin
                    $fwrite(pwl_fd, "%0.1fn %0.3f\n", $realtime, VDD);
                    $fwrite(pwl_fd, "%0.1fn 0\n",     $realtime + EDGE_NS);
                end
                prev_pwm = pwm_out;
            end
        end
    endtask

    task pwl_close;
        begin
            if (prev_pwm)
                $fwrite(pwl_fd, "%0.1fn %0.3f\n", $realtime, VDD);
            else
                $fwrite(pwl_fd, "%0.1fn 0\n", $realtime);
            $fclose(pwl_fd);
        end
    endtask

    //==========================================================================
    // Capture one filter configuration
    //==========================================================================
    task capture_filter;
        input [7:0]   fc_hi_val;
        input [7:0]   mode_vol_val;
        input [255:0] filename;
        integer i;
        begin
            // Reset
            rst_n = 0; ui_in = 0; uio_in = 0;
            repeat (50) @(posedge clk);
            rst_n = 1;
            repeat (20) @(posedge clk);

            // Voice 0: 440 Hz sawtooth, instant attack, max sustain
            sid_write(REG_FREQ_LO, 8'h1D, 2'd0);
            sid_write(REG_FREQ_HI, 8'h00, 2'd0);
            sid_write(REG_PW_LO,   8'h00, 2'd0);
            sid_write(REG_PW_HI,   8'h08, 2'd0);
            sid_write(REG_ATK,     8'h00, 2'd0);
            sid_write(REG_SUS,     8'h0F, 2'd0);

            // Filter: route voice 0, set cutoff and mode
            sid_write(REG_FC_LO,    8'h00,        VOICE_FILT);
            sid_write(REG_FC_HI,    fc_hi_val,    VOICE_FILT);
            sid_write(REG_RES_FILT, 8'h01,        VOICE_FILT);  // res=0, filt_en=voice0
            sid_write(REG_MODE_VOL, mode_vol_val,  VOICE_FILT);

            // Gate on — sawtooth
            sid_write(REG_WAV, 8'h21, 2'd0);

            // Wait for attack
            repeat (ATTACK_WAIT) @(posedge clk);

            // Capture
            pwl_open(filename);
            repeat (CAPTURE_CYCLES) begin
                @(posedge clk);
                pwl_sample;
            end
            pwl_close;
        end
    endtask

    //==========================================================================
    // Main
    //==========================================================================
    initial begin
        ena = 1;
        rst_n = 0;
        ui_in = 0;
        uio_in = 0;

        // LP @ low cutoff
        $display("1/6: LP @ low fc (alpha1=1)");
        capture_filter(FC_LO_CUT, MODE_LP, "tests/filt_lp_lo.pwl");
        $display("     done (t=%0.1f ms)", $realtime/1e6);

        // LP @ high cutoff
        $display("2/6: LP @ high fc (alpha1=3)");
        capture_filter(FC_HI_CUT, MODE_LP, "tests/filt_lp_hi.pwl");
        $display("     done (t=%0.1f ms)", $realtime/1e6);

        // HP @ low cutoff
        $display("3/6: HP @ low fc (alpha1=1)");
        capture_filter(FC_LO_CUT, MODE_HP, "tests/filt_hp_lo.pwl");
        $display("     done (t=%0.1f ms)", $realtime/1e6);

        // HP @ high cutoff
        $display("4/6: HP @ high fc (alpha1=3)");
        capture_filter(FC_HI_CUT, MODE_HP, "tests/filt_hp_hi.pwl");
        $display("     done (t=%0.1f ms)", $realtime/1e6);

        // BP @ low cutoff
        $display("5/6: BP @ low fc (alpha1=1)");
        capture_filter(FC_LO_CUT, MODE_BP, "tests/filt_bp_lo.pwl");
        $display("     done (t=%0.1f ms)", $realtime/1e6);

        // BP @ high cutoff
        $display("6/6: BP @ high fc (alpha1=3)");
        capture_filter(FC_HI_CUT, MODE_BP, "tests/filt_bp_hi.pwl");
        $display("     done (t=%0.1f ms)", $realtime/1e6);

        $display("All filter captures complete.");
        $finish;
    end

endmodule
