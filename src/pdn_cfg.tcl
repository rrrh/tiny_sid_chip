source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

set secondary []
foreach vdd $::env(VDD_NETS) gnd $::env(GND_NETS) {
    if { $vdd != $::env(VDD_NET)} {
        lappend secondary $vdd

        set db_net [[ord::get_db_block] findNet $vdd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $vdd]
            $net setSpecial
            $net setSigType "POWER"
        }
    }

    if { $gnd != $::env(GND_NET)} {
        lappend secondary $gnd

        set db_net [[ord::get_db_block] findNet $gnd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $gnd]
            $net setSpecial
            $net setSigType "GROUND"
        }
    }
}

set_voltage_domain -name CORE -power $::env(VDD_NET) -ground $::env(GND_NET) \
    -secondary_power $secondary

# Stdcell grid: TopMetal1 vertical stripes
# Stripes at x=32, 112, 192 — last stripe crosses all analog macros
define_pdn_grid \
    -name stdcell_grid \
    -starts_with POWER \
    -voltage_domain CORE \
    -pins "TopMetal1"

add_pdn_stripe \
    -grid stdcell_grid \
    -layer TopMetal1 \
    -width 2.2 \
    -pitch 80.0 \
    -offset 32.0 \
    -spacing 4.0 \
    -starts_with POWER \
    -extend_to_core_ring

# Standard cell rails on Metal1
if { $::env(PDN_ENABLE_RAILS) == 1 } {
    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_RAIL_LAYER) \
        -width $::env(PDN_RAIL_WIDTH) \
        -followpins

    add_pdn_connect \
        -grid stdcell_grid \
        -layers "Metal1 TopMetal1"
}

# Per-macro PDN grids: each places M5 stripes only at power rail
# positions to avoid cross-net overlap with internal MIM cap M5.
# M5 stripe pair: VSS at VSS rail center, VDD at VDD rail center.
# starts_with GROUND puts VSS first (at offset), VDD second.
# Large pitch prevents repeat pairs.

# Helper: define a macro grid with M4 stripes + targeted M5
proc define_analog_macro_grid {name instances vss_y vdd_y macro_h} {
    # M5 stripe spacing = VDD center - VSS center - width
    set m5_width 0.44
    set m5_spacing [expr {$vdd_y - $vss_y - $m5_width}]
    # Pitch large enough for no repeats (2× macro height)
    set m5_pitch [expr {$macro_h * 2.0}]

    define_pdn_grid \
        -macro \
        -name $name \
        -instances $instances \
        -starts_with POWER \
        -halo "0 0"

    # Metal4 vertical stripes (cross M3 horizontal PG pins)
    add_pdn_stripe \
        -grid $name \
        -layer Metal4 \
        -width 0.44 \
        -pitch 10.0 \
        -offset 5.0 \
        -starts_with POWER \
        -spacing 1.0

    # Metal5 horizontal stripes: one pair at power rail positions
    add_pdn_stripe \
        -grid $name \
        -layer Metal5 \
        -width $m5_width \
        -pitch $m5_pitch \
        -offset $vss_y \
        -spacing $m5_spacing \
        -starts_with GROUND

    # Connection chain: M3 → M4 → M5 → TM1
    add_pdn_connect -grid $name -layers "Metal3 Metal4"
    add_pdn_connect -grid $name -layers "Metal4 Metal5"
    add_pdn_connect -grid $name -layers "Metal5 TopMetal1"
}

# r2r_dac_8bit (30µm): VSS rail y=0-1.5, VDD rail y=28.5-30
define_analog_macro_grid "r2r_grid" "u_dac u_ramp_dac" 0.75 29.25 30.0

# svf_2nd (67µm): VSS rail y=0-2, VDD rail y=65-67
define_analog_macro_grid "svf_grid" "u_svf" 1.0 66.0 67.0

# pwm_comp (15µm): VSS rail y=0-2, VDD rail y=13-15
define_analog_macro_grid "comp_grid" "u_comp" 1.0 14.0 15.0
