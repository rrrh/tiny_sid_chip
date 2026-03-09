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

# Analog macro grid: connect Metal3 PG pins to TopMetal1 stripes
# via intermediate Metal4 (vertical) and Metal5 (horizontal) stripes.
# M4 width=1.0 ensures multi-cut via pads fit within the stripe
# (avoids M4.b notch violations from via enclosure extending beyond stripe).
# PDN connect is net-aware: VDD stripes only connect to VDD pins.
# TopMetal1 OBS in macro LEFs is narrowed to leave 4um at edges
# for the M5-TM1 via connection.
define_pdn_grid \
    -macro \
    -default \
    -name macro_grid \
    -starts_with POWER \
    -halo "0 0"

# Metal4 vertical stripes inside macros (cross M3 horizontal PG pins)
add_pdn_stripe \
    -grid macro_grid \
    -layer Metal4 \
    -width 1.0 \
    -pitch 14.0 \
    -offset 7.0 \
    -starts_with POWER \
    -spacing 3.0

# Metal5 horizontal stripes inside macros (cross M4 vertical stripes)
add_pdn_stripe \
    -grid macro_grid \
    -layer Metal5 \
    -width 1.0 \
    -pitch 4.0 \
    -offset 2.0 \
    -starts_with POWER \
    -spacing 1.0

# Connection chain: M3 → Via3 → M4 → Via4 → M5 → TopVia1 → TM1
add_pdn_connect \
    -grid macro_grid \
    -layers "Metal3 Metal4"

add_pdn_connect \
    -grid macro_grid \
    -layers "Metal4 Metal5"

add_pdn_connect \
    -grid macro_grid \
    -layers "Metal5 TopMetal1"
