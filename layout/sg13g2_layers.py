"""
IHP SG13G2 130nm PDK — Layer Map and Design Rules
Source: /data/Projects/chip/IHP-Open-PDK/ihp-sg13g2/libs.tech/klayout/tech/drc/rule_decks/
"""

# ===========================================================================
# GDS Layer Numbers (layer, datatype)
# ===========================================================================
L_ACTIV      = (1, 0)
L_GATPOLY    = (5, 0)
L_CONT       = (6, 0)
L_NSD        = (7, 0)
L_METAL1     = (8, 0)
L_METAL2     = (10, 0)
L_PSD        = (14, 0)
L_VIA1       = (19, 0)
L_SALBLOCK   = (28, 0)
L_VIA2       = (29, 0)
L_METAL3     = (30, 0)
L_NWELL      = (31, 0)
L_CMIM       = (36, 0)
L_THICKGOX   = (44, 0)
L_PWELL      = (46, 0)
L_VIA3       = (49, 0)
L_METAL4     = (50, 0)
L_VIA4       = (66, 0)
L_METAL5     = (67, 0)
L_TOPVIA1    = (125, 0)
L_TOPMETAL1  = (126, 0)
L_TOPVIA2    = (133, 0)
L_TOPMETAL2  = (134, 0)

# Pin/label datatypes
L_METAL1_PIN  = (8, 2)
L_METAL1_LBL  = (8, 25)
L_METAL2_PIN  = (10, 2)
L_METAL2_LBL  = (10, 25)
L_METAL3_PIN  = (30, 2)
L_METAL3_LBL  = (30, 25)

# ===========================================================================
# Design Rules (µm) — from DRC rule decks
# ===========================================================================

# Contact (enclosures include +0.01 µm design margin over DRC min)
CONT_SIZE       = 0.16
CONT_SPACE      = 0.18
CONT_ENC_ACTIV  = 0.08   # DRC min 0.07, +0.01 margin
CONT_ENC_GATPOLY = 0.08  # DRC min 0.07, +0.01 margin
CONT_ENC_M1     = 0.04   # DRC min 0.01, +0.03 margin (ensures M1 pad ≥ 0.24 µm > M1_WIDTH)

# Metal1
M1_WIDTH        = 0.16
M1_SPACE        = 0.18

# Metal2+
M2_WIDTH        = 0.20
M2_SPACE        = 0.21

# Via1
VIA1_SIZE       = 0.19
VIA1_SPACE      = 0.22
VIA1_ENC_M1     = 0.01
VIA1_ENC_M2     = 0.005

# Via2
VIA2_SIZE       = 0.19
VIA2_SPACE      = 0.22
VIA2_ENC_M2     = 0.005
VIA2_ENC_M3     = 0.005

# Via3
VIA3_SIZE       = 0.19
VIA3_SPACE      = 0.22

# Via4
VIA4_SIZE       = 0.19
VIA4_SPACE      = 0.22

# GatPoly
GATPOLY_WIDTH   = 0.13  # min gate length (1.2V)
GATPOLY_SPACE   = 0.18
GATPOLY_EXT     = 0.18  # extension past Activ

# Activ
ACTIV_WIDTH     = 0.15
ACTIV_SPACE     = 0.21

# NWell
NWELL_WIDTH     = 0.62
NWELL_SPACE     = 0.62
NWELL_ENC_ACTIV = 0.31

# SalBlock (for resistors)
SAL_ENC_GATPOLY = 0.20
SAL_SPACE_CONT  = 0.20
SAL_MIN_LEN     = 0.50

# MIM capacitor
MIM_MIN_SIZE    = 1.14
MIM_SPACE       = 0.60
MIM_ENC_M5      = 0.60   # Metal5 enclosure of Cmim

# rppd resistor
RPPD_SHEET_R    = 315.0   # Ω/sq (typical)
MIM_CAP_DENSITY = 1.5     # fF/µm²


# ===========================================================================
# Helper: create a KLayout layout with the layer map registered
# ===========================================================================
import klayout.db as pya

def new_layout(dbu=0.001):
    """Create a layout with dbu in µm (0.001 = 1nm grid)."""
    layout = pya.Layout()
    layout.dbu = dbu
    return layout

def um(val):
    """Convert µm to database units (1nm grid)."""
    return int(round(val / 0.001))

def rect(x1, y1, x2, y2):
    """Create a pya.Box from µm coordinates."""
    return pya.Box(um(x1), um(y1), um(x2), um(y2))

def add_pin_label(cell, layer_pin, layer_lbl, box, name, layout):
    """Add a pin rectangle and text label."""
    li_pin = layout.layer(*layer_pin)
    li_lbl = layout.layer(*layer_lbl)
    cell.shapes(li_pin).insert(box)
    cx = (box.left + box.right) // 2
    cy = (box.bottom + box.top) // 2
    cell.shapes(li_lbl).insert(pya.Text(name, pya.Trans(cx, cy)))
