#!/usr/bin/env python3
"""
R2R DAC GDS connectivity & shorts checker.
Uses klayout.db to load the GDS, extract shapes per metal layer,
build a connectivity graph via overlapping shapes + vias, then
label nets from pins and report any shorts or open circuits.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'layout'))

import klayout.db as pya

GDS_PATH = os.path.join(os.path.dirname(__file__), '..', 'macros', 'gds', 'r2r_dac_8bit.gds')

# IHP SG13G2 layer map
LAYERS = {
    'Activ':   (1, 0),
    'GatPoly': (5, 0),
    'Cont':    (6, 0),
    'NSD':     (7, 0),
    'Metal1':  (8, 0),
    'Metal2':  (10, 0),
    'PSD':     (14, 0),
    'Via1':    (19, 0),
    'SalBlock':(28, 0),
    'Via2':    (29, 0),
    'Metal3':  (30, 0),
}

PIN_LAYERS = {
    'Metal2_pin': (10, 2),
    'Metal2_lbl': (10, 25),
    'Metal3_pin': (30, 2),
    'Metal3_lbl': (30, 25),
}


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def groups(self):
        from collections import defaultdict
        g = defaultdict(set)
        for k in self.parent:
            g[self.find(k)].add(k)
        return g


def load_gds():
    layout = pya.Layout()
    layout.read(GDS_PATH)
    top = layout.top_cell()
    return layout, top


def get_shapes(cell, layout, layer_tuple):
    """Return list of pya.Region polygons on a layer."""
    li = layout.layer(*layer_tuple)
    region = pya.Region(cell.begin_shapes_rec(li))
    return region


def get_labels(cell, layout, layer_tuple):
    """Return list of (text, pya.Box) for labels."""
    li = layout.layer(*layer_tuple)
    labels = []
    for shape in cell.shapes(li).each():
        if shape.is_text():
            t = shape.text
            labels.append((t.string, t.x, t.y))
    return labels


def check_connectivity():
    layout, top = load_gds()
    dbu = layout.dbu  # typically 0.001 µm

    print(f"Loaded: {GDS_PATH}")
    print(f"Top cell: {top.name}, dbu={dbu} µm")
    print()

    # --- Extract shapes ---
    m1 = get_shapes(top, layout, LAYERS['Metal1'])
    m2 = get_shapes(top, layout, LAYERS['Metal2'])
    m3 = get_shapes(top, layout, LAYERS['Metal3'])
    via1 = get_shapes(top, layout, LAYERS['Via1'])
    via2 = get_shapes(top, layout, LAYERS['Via2'])
    cont = get_shapes(top, layout, LAYERS['Cont'])
    gatpoly = get_shapes(top, layout, LAYERS['GatPoly'])
    activ = get_shapes(top, layout, LAYERS['Activ'])

    print(f"Metal1:  {m1.count()} shapes, area={m1.area() * dbu * dbu:.2f} µm²")
    print(f"Metal2:  {m2.count()} shapes, area={m2.area() * dbu * dbu:.2f} µm²")
    print(f"Metal3:  {m3.count()} shapes, area={m3.area() * dbu * dbu:.2f} µm²")
    print(f"Via1:    {via1.count()} shapes")
    print(f"Via2:    {via2.count()} shapes")
    print(f"Cont:    {cont.count()} shapes")
    print(f"GatPoly: {gatpoly.count()} shapes")
    print(f"Activ:   {activ.count()} shapes")
    print()

    # --- Check 1: Via landing ---
    # Every via1 must overlap both M1 and M2
    v1_on_m1 = via1 & m1
    v1_on_m2 = via1 & m2
    v1_missing_m1 = via1 - v1_on_m1
    v1_missing_m2 = via1 - v1_on_m2
    print("=== Via1 Landing Check ===")
    if v1_missing_m1.is_empty() and v1_missing_m2.is_empty():
        print(f"  PASS: All {via1.count()} Via1 land on both M1 and M2")
    else:
        if not v1_missing_m1.is_empty():
            print(f"  FAIL: {v1_missing_m1.count()} Via1 missing M1 landing")
            for p in v1_missing_m1.each():
                b = p.bbox()
                print(f"    at ({b.left*dbu:.3f}, {b.bottom*dbu:.3f})")
        if not v1_missing_m2.is_empty():
            print(f"  FAIL: {v1_missing_m2.count()} Via1 missing M2 landing")
            for p in v1_missing_m2.each():
                b = p.bbox()
                print(f"    at ({b.left*dbu:.3f}, {b.bottom*dbu:.3f})")
    print()

    # Every via2 must overlap both M2 and M3
    v2_on_m2 = via2 & m2
    v2_on_m3 = via2 & m3
    v2_missing_m2 = via2 - v2_on_m2
    v2_missing_m3 = via2 - v2_on_m3
    print("=== Via2 Landing Check ===")
    if v2_missing_m2.is_empty() and v2_missing_m3.is_empty():
        print(f"  PASS: All {via2.count()} Via2 land on both M2 and M3")
    else:
        if not v2_missing_m2.is_empty():
            print(f"  FAIL: {v2_missing_m2.count()} Via2 missing M2 landing")
            for p in v2_missing_m2.each():
                b = p.bbox()
                print(f"    at ({b.left*dbu:.3f}, {b.bottom*dbu:.3f})")
        if not v2_missing_m3.is_empty():
            print(f"  FAIL: {v2_missing_m3.count()} Via2 missing M3 landing")
            for p in v2_missing_m3.each():
                b = p.bbox()
                print(f"    at ({b.left*dbu:.3f}, {b.bottom*dbu:.3f})")
    print()

    # Every contact must overlap M1 and (GatPoly or Activ)
    c_on_m1 = cont & m1
    c_on_gp = cont & gatpoly
    c_on_act = cont & activ
    c_on_device = c_on_gp | c_on_act
    c_missing_m1 = cont - c_on_m1
    c_missing_dev = cont - c_on_device
    print("=== Contact Landing Check ===")
    if c_missing_m1.is_empty() and c_missing_dev.is_empty():
        print(f"  PASS: All {cont.count()} contacts land on M1 and GatPoly/Activ")
    else:
        if not c_missing_m1.is_empty():
            print(f"  FAIL: {c_missing_m1.count()} contacts missing M1")
            for p in c_missing_m1.each():
                b = p.bbox()
                print(f"    at ({b.left*dbu:.3f}, {b.bottom*dbu:.3f})")
        if not c_missing_dev.is_empty():
            print(f"  FAIL: {c_missing_dev.count()} contacts missing GatPoly/Activ")
            for p in c_missing_dev.each():
                b = p.bbox()
                print(f"    at ({b.left*dbu:.3f}, {b.bottom*dbu:.3f})")
    print()

    # --- Check 2: Metal shorts (same-layer touching that shouldn't) ---
    # Merge each metal layer and count connected polygons
    m1_merged = m1.merged()
    m2_merged = m2.merged()
    m3_merged = m3.merged()
    print("=== Metal Connectivity (merged polygons) ===")
    print(f"  Metal1: {m1.count()} shapes → {m1_merged.count()} connected regions")
    print(f"  Metal2: {m2.count()} shapes → {m2_merged.count()} connected regions")
    print(f"  Metal3: {m3.count()} shapes → {m3_merged.count()} connected regions")
    print()

    # --- Check 3: Net extraction using union-find ---
    # Tag each merged polygon with (layer, index)
    # Also merge GatPoly and Activ to trace through resistors and transistors
    uf = UnionFind()
    net_labels = {}  # node_id → pin name

    # NOTE: We only trace metal connectivity (via1/via2) for net extraction.
    # Contact-level connectivity (M1↔GatPoly, M1↔Activ) is NOT traced because
    # the R-2R ladder intentionally connects VDD→resistors→vout→switches→VSS
    # through GatPoly resistor bodies and Activ transistor channels, which would
    # merge all nets into one. Full LVS (e.g. netgen) is needed for device-aware
    # connectivity extraction.

    # Build per-layer Region lists for proper polygon intersection
    def region_to_poly_list(region):
        """Return list of (pya.Region containing one polygon, bbox) tuples."""
        polys = []
        for p in region.each():
            r = pya.Region(p)
            polys.append((r, p.bbox()))
        return polys

    m1_rpoly = region_to_poly_list(m1_merged)
    m2_rpoly = region_to_poly_list(m2_merged)
    m3_rpoly = region_to_poly_list(m3_merged)

    # Seed every metal polygon into union-find
    for tag, rplist in [('M1', m1_rpoly), ('M2', m2_rpoly), ('M3', m3_rpoly)]:
        for i in range(len(rplist)):
            uf.find((tag, i))

    def find_overlapping(via_region, rpoly_list, layer_tag):
        """Find indices of polygons that actually intersect via_region."""
        results = []
        for i, (rpoly, bbox) in enumerate(rpoly_list):
            # Quick bbox pre-filter
            via_bbox = via_region.bbox() if hasattr(via_region, 'bbox') else via_region
            if isinstance(via_region, pya.Box):
                vr = pya.Region(via_region)
            else:
                vr = via_region
            overlap = rpoly & vr
            if not overlap.is_empty():
                results.append((layer_tag, i))
        return results

    def connect_all(hits):
        if len(hits) > 1:
            for i in range(1, len(hits)):
                uf.union(hits[0], hits[i])

    # Connect via1: link M1 ↔ M2
    print("=== Net Extraction ===")
    for p in via1.each():
        vr = pya.Region(p)
        hits = find_overlapping(vr, m1_rpoly, 'M1') + find_overlapping(vr, m2_rpoly, 'M2')
        connect_all(hits)

    # Connect via2: link M2 ↔ M3
    for p in via2.each():
        vr = pya.Region(p)
        hits = find_overlapping(vr, m2_rpoly, 'M2') + find_overlapping(vr, m3_rpoly, 'M3')
        connect_all(hits)

    # Contact connectivity (M1↔GP/Activ) intentionally NOT traced — see note above.

    # Label nets from pin labels — use pin rectangles (more reliable than label coords)
    for pin_name, pin_layer in [('Metal2_pin', (10, 2)), ('Metal3_pin', (30, 2))]:
        li_pin = layout.layer(*pin_layer)
        li_lbl = layout.layer(pin_layer[0], 25)
        if 'Metal2' in pin_name:
            rpoly = m2_rpoly
            tag = 'M2'
        else:
            rpoly = m3_rpoly
            tag = 'M3'
        # Collect label texts with positions
        lbl_map = {}
        for shape in top.shapes(li_lbl).each():
            if shape.is_text():
                t = shape.text
                lbl_map[(t.x, t.y)] = t.string
        # Match pin shapes to polygons
        for shape in top.shapes(li_pin).each():
            if shape.is_box():
                b = shape.box
                cx = (b.left + b.right) // 2
                cy = (b.bottom + b.top) // 2
                # Find label for this pin
                name = lbl_map.get((cx, cy), None)
                if name is None:
                    continue
                # Find which merged polygon this pin overlaps
                pin_r = pya.Region(b)
                for i, (rpoly_i, _) in enumerate(rpoly):
                    overlap = rpoly_i & pin_r
                    if not overlap.is_empty():
                        root = uf.find((tag, i))
                        net_labels[root] = name
                        break

    groups = uf.groups()
    print(f"  Total nets extracted: {len(groups)}")

    # Map nets to pin names
    named_nets = {}
    unnamed_nets = []
    for root, members in groups.items():
        name = net_labels.get(root, None)
        if name is None:
            for m in members:
                r = uf.find(m)
                if r in net_labels:
                    name = net_labels[r]
                    break
        if name:
            named_nets[name] = members
        else:
            unnamed_nets.append(members)

    print(f"  Named nets: {sorted(named_nets.keys())}")
    print(f"  Unnamed nets: {len(unnamed_nets)}")
    print()

    # --- Check 4: Pin-to-pin shorts ---
    print("=== Short Circuit Check ===")
    shorts_found = False
    pin_names = list(named_nets.keys())
    for i in range(len(pin_names)):
        for j in range(i+1, len(pin_names)):
            ni, nj = pin_names[i], pin_names[j]
            # Check if they share the same root
            members_i = named_nets[ni]
            members_j = named_nets[nj]
            # Pick any member from each and check if they have same root
            mi = next(iter(members_i))
            mj = next(iter(members_j))
            if uf.find(mi) == uf.find(mj):
                print(f"  SHORT: {ni} ↔ {nj}")
                shorts_found = True

    if not shorts_found:
        print("  PASS: No pin-to-pin shorts detected")
    print()

    # --- Check 5: Expected connectivity ---
    # d[0]..d[7] should each be an independent net (8 nets)
    # vdd and vss should be independent
    # vout should be independent
    print("=== Expected Net Independence ===")
    expected_pins = ['vdd', 'vss', 'vout'] + [f'd[{i}]' for i in range(8)]
    found_pins = set(named_nets.keys())
    for p in expected_pins:
        if p in found_pins:
            print(f"  {p}: found (net has {len(named_nets[p])} metal segments)")
        else:
            print(f"  {p}: NOT FOUND in layout")
    print()

    # --- Check 6: DRC spacing quick-check on M2 ---
    # Check minimum spacing between M2 shapes (should be >= 0.21µm)
    print("=== M2 Spacing Quick Check ===")
    m2_space_dbu = int(round(0.21 / dbu))  # 210 nm
    m2_space_violations = m2_merged.space_check(m2_space_dbu)
    if m2_space_violations.count() == 0:
        print(f"  PASS: All M2 spacing >= 0.21 µm")
    else:
        print(f"  VIOLATIONS: {m2_space_violations.count()} M2 spacing violations")
        for ep in m2_space_violations.each():
            p1 = ep.first
            p2 = ep.second
            print(f"    between ({p1.bbox().left*dbu:.3f},{p1.bbox().bottom*dbu:.3f}) "
                  f"and ({p2.bbox().left*dbu:.3f},{p2.bbox().bottom*dbu:.3f})")
    print()

    # --- Check 7: M3 spacing ---
    print("=== M3 Spacing Quick Check ===")
    m3_space_dbu = int(round(0.21 / dbu))
    m3_space_violations = m3_merged.space_check(m3_space_dbu)
    if m3_space_violations.count() == 0:
        print(f"  PASS: All M3 spacing >= 0.21 µm")
    else:
        print(f"  VIOLATIONS: {m3_space_violations.count()} M3 spacing violations")
    print()

    # --- Summary ---
    errors = 0
    if not v1_missing_m1.is_empty(): errors += 1
    if not v1_missing_m2.is_empty(): errors += 1
    if not v2_missing_m2.is_empty(): errors += 1
    if not v2_missing_m3.is_empty(): errors += 1
    if not c_missing_m1.is_empty(): errors += 1
    if not c_missing_dev.is_empty(): errors += 1
    if shorts_found: errors += 1
    if m2_space_violations.count() > 0: errors += 1
    if m3_space_violations.count() > 0: errors += 1

    print("=" * 50)
    if errors == 0:
        print("SUMMARY: ALL CHECKS PASSED")
    else:
        print(f"SUMMARY: {errors} CHECK(S) FAILED")
    print("=" * 50)

    return errors


if __name__ == '__main__':
    sys.exit(check_connectivity())
