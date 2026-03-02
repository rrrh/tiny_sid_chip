#!/usr/bin/env python3
"""
Render annotated R2R DAC layout screenshot from GDS using matplotlib.
Reads the GDS, draws each layer with its standard color, and overlays
annotation callouts for the major blocks.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'layout'))

import klayout.db as pya
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# ── Layer colors (IHP SG13G2 convention, alpha-blended) ──────────────
LAYER_STYLE = {
    # (layer, datatype): (color, alpha, zorder, label)
    (1, 0):   ('#22aa22', 0.45, 2,  'Activ'),
    (5, 0):   ('#cc2222', 0.40, 3,  'GatPoly'),
    (6, 0):   ('#111111', 0.80, 8,  'Cont'),
    (7, 0):   ('#44cc44', 0.15, 1,  'nSD'),
    (8, 0):   ('#2266dd', 0.40, 5,  'Metal1'),
    (10, 0):  ('#cc66cc', 0.35, 6,  'Metal2'),
    (14, 0):  ('#aacc44', 0.12, 1,  'pSD'),
    (19, 0):  ('#444444', 0.80, 8,  'Via1'),
    (28, 0):  ('#ffaa00', 0.18, 1,  'SalBlock'),
    (29, 0):  ('#666666', 0.80, 8,  'Via2'),
    (30, 0):  ('#33bbbb', 0.25, 4,  'Metal3'),
    (46, 0):  ('#ddddaa', 0.08, 0,  'PWell'),
    # Pin/label layers — skip rendering
    (8, 2):   None,
    (8, 25):  None,
    (10, 2):  None,
    (10, 25): None,
    (30, 2):  None,
    (30, 25): None,
    (189, 0): None,  # PR boundary
}


def shapes_to_rects(cell, layer_idx, dbu):
    """Extract all box/polygon shapes as (x1,y1,x2,y2) in µm."""
    rects = []
    for shape in cell.shapes(layer_idx).each():
        b = shape.bbox()
        rects.append((b.left * dbu, b.bottom * dbu,
                       b.right * dbu, b.top * dbu))
    return rects


def draw_layer(ax, rects, color, alpha, zorder):
    for x1, y1, x2, y2 in rects:
        ax.add_patch(mpatches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=0.15, edgecolor=color, facecolor=color,
            alpha=alpha, zorder=zorder))


def add_annotation(ax, text, xy, xytext, color='#222222', fontsize=8,
                   arrowcolor='#555555', bbox_fc='white', bold=False):
    """Add a callout annotation with arrow."""
    weight = 'bold' if bold else 'normal'
    ax.annotate(text, xy=xy, xytext=xytext,
                fontsize=fontsize, fontweight=weight, color=color,
                ha='center', va='center',
                bbox=dict(boxstyle='round,pad=0.3', fc=bbox_fc, ec=arrowcolor,
                          alpha=0.92, lw=0.8),
                arrowprops=dict(arrowstyle='->', color=arrowcolor, lw=1.0,
                                connectionstyle='arc3,rad=0.15'))


def main():
    gds_path = os.path.join(os.path.dirname(__file__), '..', 'macros', 'gds',
                            'r2r_dac_8bit.gds')
    layout = pya.Layout()
    layout.read(gds_path)
    dbu = layout.dbu
    top = layout.top_cell()
    bb = top.dbbox()
    xmin, ymin = bb.left, bb.bottom
    xmax, ymax = bb.right, bb.top

    # ── Figure ────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(16, 12), dpi=180)
    ax.set_xlim(xmin - 1, xmax + 1)
    ax.set_ylim(ymin - 1, ymax + 1)
    ax.set_aspect('equal')
    ax.set_facecolor('#1a1a2e')
    fig.patch.set_facecolor('#0f0f1a')

    # Draw macro boundary
    ax.add_patch(mpatches.Rectangle(
        (xmin, ymin), xmax - xmin, ymax - ymin,
        linewidth=1.5, edgecolor='#667788', facecolor='#1e1e30',
        linestyle='--', zorder=0))

    # ── Render each GDS layer ────────────────────────────────────────
    legend_entries = []
    for li_idx in layout.layer_indices():
        info = layout.get_info(li_idx)
        key = (info.layer, info.datatype)
        style = LAYER_STYLE.get(key)
        if style is None:
            continue  # skip pin/label/boundary
        color, alpha, zorder, label = style
        rects = shapes_to_rects(top, li_idx, dbu)
        if not rects:
            continue
        draw_layer(ax, rects, color, alpha, zorder)
        legend_entries.append(mpatches.Patch(facecolor=color, alpha=min(alpha + 0.2, 1.0),
                                             edgecolor=color, label=label))

    # ── Annotations ──────────────────────────────────────────────────

    # Title
    ax.text((xmin + xmax) / 2, ymax + 0.6,
            '8-bit R-2R DAC Layout — IHP SG13G2 130nm',
            fontsize=13, fontweight='bold', color='white', ha='center',
            va='bottom')
    ax.text((xmin + xmax) / 2, ymax + 0.2,
            f'{xmax - xmin:.0f} × {ymax - ymin:.0f} µm  |  R=2kΩ (rhigh)  |  NMOS W=2µm L=0.13µm',
            fontsize=8, color='#aaaacc', ha='center', va='bottom')

    # VDD rail (top Metal3)
    add_annotation(ax, 'VDD Rail\n(Metal3)', xy=(19, 44), xytext=(30, 46.5),
                   color='#33bbbb', fontsize=9, bold=True, bbox_fc='#1a2a2a',
                   arrowcolor='#33bbbb')

    # VSS rail (bottom Metal3)
    add_annotation(ax, 'VSS Rail\n(Metal3)', xy=(19, 1), xytext=(30, -1.5),
                   color='#33bbbb', fontsize=9, bold=True, bbox_fc='#1a2a2a',
                   arrowcolor='#33bbbb')

    # Series R chain (y ≈ 35)
    add_annotation(ax, 'Series R chain (8 × 2kΩ)\nrhigh poly, horizontal',
                   xy=(19, 36), xytext=(34, 40),
                   color='#cc2222', fontsize=8, bold=True, bbox_fc='#2a1a1a',
                   arrowcolor='#cc4444')

    # 2R shunt resistors (vertical, around y ≈ 27-34)
    add_annotation(ax, '2R shunt\n(4kΩ vertical)', xy=(7, 28), xytext=(-2, 32),
                   color='#cc2222', fontsize=8, bbox_fc='#2a1a1a',
                   arrowcolor='#cc4444')

    # NMOS switches (y ≈ 24-26)
    add_annotation(ax, 'NMOS switches\n(W=2µm, L=0.13µm)', xy=(19, 25), xytext=(34, 28),
                   color='#22aa22', fontsize=8, bold=True, bbox_fc='#1a2a1a',
                   arrowcolor='#44cc44')

    # M1 junction bridges
    add_annotation(ax, 'M1 bridges\n(R→2R junctions)', xy=(12, 34.5), xytext=(-2, 37),
                   color='#2266dd', fontsize=7, bbox_fc='#1a1a2a',
                   arrowcolor='#4488ff')

    # Gate contacts (the fix!)
    add_annotation(ax, 'Gate contacts\n(GatPoly+Cont+M1→Via1)\n★ NEW FIX',
                   xy=(7, 22.5), xytext=(-3, 18),
                   color='#ffcc00', fontsize=8, bold=True, bbox_fc='#2a2a1a',
                   arrowcolor='#ffcc00')

    # M2 digital input routes
    add_annotation(ax, 'd[7:0] input pins\n(Metal2, left edge)',
                   xy=(0.5, 17), xytext=(-4, 10),
                   color='#cc66cc', fontsize=8, bold=True, bbox_fc='#2a1a2a',
                   arrowcolor='#cc66cc')

    # Vout pin
    add_annotation(ax, 'Vout pin\n(Metal2)', xy=(37.5, 21), xytext=(40, 16),
                   color='#cc66cc', fontsize=8, bold=True, bbox_fc='#2a1a2a',
                   arrowcolor='#cc66cc')

    # VSS bus (M1 horizontal)
    add_annotation(ax, 'VSS M1 bus\n(sources → rail)', xy=(10, 23.8), xytext=(-3, 25.5),
                   color='#2266dd', fontsize=7, bbox_fc='#1a1a2a',
                   arrowcolor='#4488ff')

    # Vref → VDD route
    add_annotation(ax, 'Vref→VDD\n(M1→Via1→Via2→M3)',
                   xy=(2, 40), xytext=(-3, 43),
                   color='#33bbbb', fontsize=7, bbox_fc='#1a2a2a',
                   arrowcolor='#33bbbb')

    # Substrate taps
    add_annotation(ax, 'P+ substrate\ntaps (6×)', xy=(15, 21.2), xytext=(24, 18),
                   color='#aacc44', fontsize=7, bbox_fc='#2a2a1a',
                   arrowcolor='#aacc44')

    # Bit labels along d[n] pins
    for bit in range(8):
        pin_y = 3.0 + bit * 4.0
        ax.text(-0.8, pin_y, f'd[{bit}]', fontsize=5.5, color='#cc99cc',
                ha='right', va='center', fontstyle='italic')

    ax.text(38.8, 21, 'Vout', fontsize=5.5, color='#cc99cc',
            ha='left', va='center', fontstyle='italic')

    # ── Legend ────────────────────────────────────────────────────────
    legend = ax.legend(handles=legend_entries, loc='lower right',
                       fontsize=6.5, framealpha=0.85,
                       facecolor='#1a1a2e', edgecolor='#555566',
                       labelcolor='white', ncol=2,
                       title='GDS Layers', title_fontsize=7)
    legend.get_title().set_color('white')

    # ── Axes styling ─────────────────────────────────────────────────
    ax.set_xlabel('X (µm)', fontsize=9, color='#aaaacc')
    ax.set_ylabel('Y (µm)', fontsize=9, color='#aaaacc')
    ax.tick_params(colors='#888899', labelsize=7)
    for spine in ax.spines.values():
        spine.set_color('#444466')

    plt.tight_layout()
    out_path = os.path.join(os.path.dirname(__file__), 'r2r_dac_8bit_layout.png')
    fig.savefig(out_path, dpi=180, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"Wrote {out_path}")


if __name__ == '__main__':
    main()
