`timescale 1ns / 1ps
module gl_quick2_tb;
    reg clk;
    initial clk = 0;
    always #21 clk = ~clk;  // ~24 MHz

    reg rst_n, ena;
    reg [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;

    tt_um_sid dut (
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    task sid_write;
        input [2:0] addr; input [7:0] data; input [1:0] voice;
        begin
            @(negedge clk);
            ui_in  = {1'b0, 2'b00, voice, addr};
            uio_in = data;
            @(negedge clk); ui_in[7] = 1'b1;
            @(negedge clk); @(negedge clk);
            ui_in[7] = 1'b0;
            @(negedge clk);
        end
    endtask

    integer i, toggle_count;
    reg prev;

    initial begin
        ena = 1; rst_n = 0; ui_in = 0; uio_in = 0;
        repeat (50) @(posedge clk);
        rst_n = 1;
        repeat (20) @(posedge clk);

        // Triangle 440 Hz, instant ADSR, bypass filter vol=15
        sid_write(3'd0, 8'h1D, 2'd0);
        sid_write(3'd1, 8'h00, 2'd0);
        sid_write(3'd2, 8'h00, 2'd0);
        sid_write(3'd3, 8'h08, 2'd0);  // pw
        sid_write(3'd4, 8'h00, 2'd0);  // atk=0, dec=0
        sid_write(3'd5, 8'hF0, 2'd0);  // sus=15, rel=0
        sid_write(3'd0, 8'h00, 2'd3);
        sid_write(3'd1, 8'h00, 2'd3);
        sid_write(3'd2, 8'h00, 2'd3);
        sid_write(3'd3, 8'h0F, 2'd3);  // mode_vol bypass
        sid_write(3'd6, 8'h11, 2'd0);  // triangle + gate

        prev = uo_out[0];
        toggle_count = 0;
        $display("t=0: uo_out=%b", uo_out);

        for (i = 0; i < 100000; i = i + 1) begin
            @(posedge clk);
            if (uo_out[0] !== prev) begin
                toggle_count = toggle_count + 1;
                if (toggle_count <= 5)
                    $display("t=%0t: uo[0] -> %b (cycle %0d)", $time, uo_out[0], i);
                prev = uo_out[0];
            end
        end

        $display("Total toggles in 100k cycles: %0d", toggle_count);
        $finish;
    end
endmodule
