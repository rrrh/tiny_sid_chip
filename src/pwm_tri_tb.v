`timescale 1ns / 1ps
//==============================================================================
// Testbench: Dump PWM output for single triangle voice to PWL file
//==============================================================================
// Runs voice 0 as triangle C4 (262 Hz) and writes PWM transitions
// to pwm_tri_output.pwl in ngspice Piece-Wise Linear format.
//
// VDDIO = 3.3 V (sg13g2 I/O bank)
//==============================================================================

module pwm_tri_tb;

    // --- Parameters ---
    localparam real VDD     = 3.3;     // I/O bank voltage (sg13g2 VDDIO)
    localparam real EDGE_NS = 2.0;     // Rise/fall time in ns
    localparam      SIM_CYCLES = 10_000_000; // 2 s at 5 MHz

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
    localparam [7:0] GATE = 8'h01, TRI = 8'h10;
    localparam [7:0] FREQ_C4 = 8'd17;
    localparam [2:0] REG_FREQ = 3'd0,
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
        pwl_file = $fopen("pwm_tri_output.pwl", "w");
        if (pwl_file == 0) begin
            $display("ERROR: Cannot open pwm_tri_output.pwl");
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

        // --- Configure voice 0: triangle C4 ---
        sid_write(REG_FREQ, FREQ_C4, 2'd0);
        sid_write(REG_ATK,  8'h00,   2'd0);  // instant attack
        sid_write(REG_SUS,  8'h0F,   2'd0);  // max sustain
        sid_write(REG_WAV,  TRI | GATE, 2'd0);

        // --- Record PWM transitions ---
        prev_pwm = pwm_out;
        repeat (SIM_CYCLES) begin
            @(posedge clk);
            if (pwm_out !== prev_pwm) begin
                t_ns = $realtime;
                if (pwm_out) begin
                    $fwrite(pwl_file, "%0.1fn 0\n",   t_ns);
                    $fwrite(pwl_file, "%0.1fn %0.3f\n", t_ns + EDGE_NS, VDD);
                end else begin
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
        $display("PWL file written: pwm_tri_output.pwl (%0d cycles)", SIM_CYCLES);
        $finish;
    end

    // Safety timeout
    initial begin #3_000_000_000; $display("ERROR: Timeout"); $finish; end

endmodule
