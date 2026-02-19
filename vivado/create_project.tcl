# ==============================================================================
# Vivado Project Creation Script — tt_um_sid on Arty A7-100
# ==============================================================================
# Usage:  vivado -mode batch -source create_project.tcl
#    or:  from Vivado Tcl console: source create_project.tcl
# ==============================================================================

set project_name "tt_um_sid"
set project_dir  [file dirname [file normalize [info script]]]
set src_dir      [file normalize "$project_dir/../src"]

# Create project — Arty A7-100 Rev. D
create_project $project_name "$project_dir/$project_name" -part xc7a100tcsg324-1 -force

# --------------------------------------------------------------------------
# Design sources
# --------------------------------------------------------------------------
add_files -norecurse [list \
    "$project_dir/arty_top.v" \
    "$src_dir/tt_um_sid.v" \
    "$src_dir/pwm_audio.v" \
]

# --------------------------------------------------------------------------
# Constraints — Arty A7-100 pin mapping
# --------------------------------------------------------------------------
add_files -fileset constrs_1 -norecurse "$project_dir/arty_sid.xdc"

# --------------------------------------------------------------------------
# Simulation sources
# --------------------------------------------------------------------------
add_files -fileset sim_1 -norecurse [list \
    "$src_dir/tt_um_sid_tb.v" \
]

# Set simulation top module
set_property top tt_um_sid_tb [get_filesets sim_1]
set_property top_lib xil_defaultlib [get_filesets sim_1]

# --------------------------------------------------------------------------
# Simulation settings
# --------------------------------------------------------------------------
set_property -name {xsim.simulate.runtime} -value {200ms} -objects [get_filesets sim_1]
set_property -name {xsim.simulate.log_all_signals} -value {true} -objects [get_filesets sim_1]

# Set design top module
set_property top arty_top [get_filesets sources_1]

update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

puts "======================================"
puts "  Project created: $project_dir/$project_name"
puts "  Target:          Arty A7-100 (xc7a100tcsg324-1)"
puts "  Design top:      arty_top"
puts "  Simulation top:  tt_um_sid_tb"
puts "  Constraints:     arty_sid.xdc"
puts "======================================"
