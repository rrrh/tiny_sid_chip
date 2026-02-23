`timescale 1ns / 1ps
//==============================================================================
// Testbench: Dump PWM output as ngspice PWL file
//==============================================================================
// Runs 3-voice SID (saw C4 + pulse E4 + tri G4) and writes PWM transitions
// to pwm_output.pwl in ngspice Piece-Wise Linear format.
//
// Usage in ngspice:
//   Vpwm pwm_in gnd PWL file="pwm_output.pwl"
//
// The output swings between 0 V and VDDIO (3.3 V for sg13g2 I/O bank).
// Rise/fall time is 2 ns (adjustable via EDGE_NS parameter).
//==============================================================================

module pwm_ngspice_tb;

    // --- Parameters ---
    localparam real VDD     = 3.3;     // I/O bank voltage (sg13g2 VDDIO)
    localparam real EDGE_NS = 2.0;     // Rise/fall time in ns
    localparam      SIM_CYCLES = 2_000_000;  // ~400 us at 5 MHz

    // --- Clock and DUT ---
    reg clk;
    initial clk = 0;
    always #100 clk = ~clk;  // 5 MHz (200 ns period)

    reg        rst_n, ena;
    reg  [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    wire pwm_out = uo_out[0];

    // --- Register constants ---
    localparam [7:0] GATE = 8'h01, SAW = 8'h20, PULSE = 8'h40, TRI = 8'h10;
    localparam [7:0] FREQ_C4 = 8'd17, FREQ_E4 = 8'd22, FREQ_G4 = 8'd26;
    localparam [2:0] REG_FREQ = 3'd0, REG_PW = 3'd2,
                     REG_ATK  = 3'd4, REG_SUS = 3'd5, REG_WAV = 3'd6;

    task sid_write;
        input [2:0] addr; input [7:0] data; input [1:0] voice;
        begin
            ui_in[2:0] <= addr; ui_in[4:3] <= voice; uio_in <= data;
            @(posedge clk);
            ui_in[7] <= 1'b1; @(posedge clk);
            ui_in[7] <= 1'b0; @(posedge clk);
        end
    endtask

    // --- PWL file writer ---
    integer pwl_file;
    reg     prev_pwm;
    real    t_ns;

    initial begin
        pwl_file = $fopen("pwm_output.pwl", "w");
        if (pwl_file == 0) begin
            $display("ERROR: Cannot open pwm_output.pwl");
            $finish;
        end

        // --- Reset ---
        ui_in = 0; uio_in = 0; ena = 1; rst_n = 0;
        prev_pwm = 0;
        repeat (100) @(posedge clk);
        rst_n = 1;
        repeat (50) @(posedge clk);

        // Write initial state
        $fwrite(pwl_file, "0n 0\n");

        // --- Configure 3 voices ---
        // V0: sawtooth C4
        sid_write(REG_FREQ, FREQ_C4, 2'd0);
        sid_write(REG_ATK,  8'h00,   2'd0);
        sid_write(REG_SUS,  8'h0F,   2'd0);
        sid_write(REG_WAV,  SAW | GATE, 2'd0);

        // V1: pulse E4
        sid_write(REG_FREQ, FREQ_E4, 2'd1);
        sid_write(REG_PW,   8'h80,   2'd1);
        sid_write(REG_ATK,  8'h00,   2'd1);
        sid_write(REG_SUS,  8'h0F,   2'd1);
        sid_write(REG_WAV,  PULSE | GATE, 2'd1);

        // V2: triangle G4
        sid_write(REG_FREQ, FREQ_G4, 2'd2);
        sid_write(REG_ATK,  8'h00,   2'd2);
        sid_write(REG_SUS,  8'h0F,   2'd2);
        sid_write(REG_WAV,  TRI | GATE, 2'd2);

        // --- Record PWM transitions ---
        prev_pwm = pwm_out;
        repeat (SIM_CYCLES) begin
            @(posedge clk);
            if (pwm_out !== prev_pwm) begin
                t_ns = $realtime;
                // Write transition with finite edge time
                if (pwm_out) begin
                    // Rising edge: low at t, high at t+edge
                    $fwrite(pwl_file, "%0.1fn 0\n",   t_ns);
                    $fwrite(pwl_file, "%0.1fn %0.3f\n", t_ns + EDGE_NS, VDD);
                end else begin
                    // Falling edge: high at t, low at t+edge
                    $fwrite(pwl_file, "%0.1fn %0.3f\n", t_ns, VDD);
                    $fwrite(pwl_file, "%0.1fn 0\n",     t_ns + EDGE_NS);
                end
                prev_pwm = pwm_out;
            end
        end

        // Final state
        t_ns = $realtime;
        if (prev_pwm)
            $fwrite(pwl_file, "%0.1fn %0.3f\n", t_ns, VDD);
        else
            $fwrite(pwl_file, "%0.1fn 0\n", t_ns);

        $fclose(pwl_file);
        $display("PWL file written: pwm_output.pwl (%0d cycles)", SIM_CYCLES);
        $finish;
    end

    // Safety timeout
    initial begin #600_000_000; $display("ERROR: Timeout"); $finish; end

endmodule
