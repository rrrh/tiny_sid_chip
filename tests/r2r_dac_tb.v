`timescale 1ns / 1ps
// R2R DAC 8-bit gate-level testbench
// Sweeps all 256 codes, checks:
//   1. vout follows MSB (d7) for the behavioral model
//   2. sim_data_out captures all 8 bits correctly
module r2r_dac_tb;

    reg d0, d1, d2, d3, d4, d5, d6, d7;
    wire vout;

    r2r_dac_8bit dut (
        .d0(d0), .d1(d1), .d2(d2), .d3(d3),
        .d4(d4), .d5(d5), .d6(d6), .d7(d7),
        .vout(vout)
    );

    integer code;
    integer errors;

    initial begin
        errors = 0;

        // --- Test 1: Walk each bit, verify sim_data_out ---
        $display("=== Test 1: Single-bit walk ===");
        {d7,d6,d5,d4,d3,d2,d1,d0} = 8'h00;
        #10;
        for (code = 0; code < 8; code = code + 1) begin
            {d7,d6,d5,d4,d3,d2,d1,d0} = (1 << code);
            #10;
            if (dut.sim_data_out !== (1 << code)) begin
                $display("  FAIL: bit %0d: sim_data_out=%b, expected=%b",
                         code, dut.sim_data_out, (1 << code));
                errors = errors + 1;
            end
        end
        $display("  Bit-walk: %0d errors", errors);

        // --- Test 2: Full 256-code sweep, check monotonicity of MSB ---
        $display("=== Test 2: 256-code sweep ===");
        for (code = 0; code < 256; code = code + 1) begin
            {d7,d6,d5,d4,d3,d2,d1,d0} = code[7:0];
            #10;

            // Behavioral model: vout = d7
            if (vout !== d7) begin
                $display("  FAIL: code=%0d vout=%b expected=%b", code, vout, d7);
                errors = errors + 1;
            end

            // sim_data_out must match input code
            if (dut.sim_data_out !== code[7:0]) begin
                $display("  FAIL: code=%0d sim_data_out=%0d expected=%0d",
                         code, dut.sim_data_out, code);
                errors = errors + 1;
            end
        end

        // --- Test 3: Check key codes ---
        $display("=== Test 3: Key codes ===");

        // All zeros
        {d7,d6,d5,d4,d3,d2,d1,d0} = 8'h00;
        #10;
        if (vout !== 1'b0 || dut.sim_data_out !== 8'h00) begin
            $display("  FAIL: code=0x00 vout=%b data=%0d", vout, dut.sim_data_out);
            errors = errors + 1;
        end else
            $display("  PASS: 0x00 → vout=0, data=0");

        // All ones
        {d7,d6,d5,d4,d3,d2,d1,d0} = 8'hFF;
        #10;
        if (vout !== 1'b1 || dut.sim_data_out !== 8'hFF) begin
            $display("  FAIL: code=0xFF vout=%b data=%0d", vout, dut.sim_data_out);
            errors = errors + 1;
        end else
            $display("  PASS: 0xFF → vout=1, data=255");

        // Mid-scale
        {d7,d6,d5,d4,d3,d2,d1,d0} = 8'h80;
        #10;
        if (vout !== 1'b1 || dut.sim_data_out !== 8'h80) begin
            $display("  FAIL: code=0x80 vout=%b data=%0d", vout, dut.sim_data_out);
            errors = errors + 1;
        end else
            $display("  PASS: 0x80 → vout=1, data=128");

        // Just below mid-scale
        {d7,d6,d5,d4,d3,d2,d1,d0} = 8'h7F;
        #10;
        if (vout !== 1'b0 || dut.sim_data_out !== 8'h7F) begin
            $display("  FAIL: code=0x7F vout=%b data=%0d", vout, dut.sim_data_out);
            errors = errors + 1;
        end else
            $display("  PASS: 0x7F → vout=0, data=127");

        $display("");
        $display("====================================");
        if (errors == 0)
            $display("  RESULT: ALL TESTS PASSED");
        else
            $display("  RESULT: %0d ERRORS", errors);
        $display("====================================");
        $finish;
    end

endmodule
