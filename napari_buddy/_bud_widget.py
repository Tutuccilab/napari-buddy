"""
napari widget: reassign / create bud <-> mother links by drawing lines.

Workflow
--------
1. Click "New line layer" - adds a 'draw bud <-> mother lines' Shapes layer in
   line-drawing mode.
2. Draw a short line between a bud and its mother (either direction):
     * bud missing from the DIC segmentation -> first paint it in the 'bud masks' layer (label 1), then
       draw the line from the painted bud to its mother. The end on the painted bud is the bud, so it
       does not matter if the paint overlaps the mother's edge. Painted pixels outside any cell are added
       to the mother; other cells under the paint are not changed.
     * bud segmented as its own DIC cell -> that cell is merged into the mother (painted or not).
3. Click "Apply links". The chosen Labels layer is edited in place, the
   'bud -> mother links' layer (a line from each bud to its mother) and, if shown,
   the 'potential buds' rectangles are redrawn, and the processed lines are cleared.
   Pressing "Apply links" without drawn lines just redraws the links (e.g. after painting); saving in
   the Correct images panel also applies lines you drew but did not apply yet.

Light module (numpy + skimage + magicgui; napari imported lazily).
"""
import numpy as np
from skimage.measure import regionprops, label as cc_label
from magicgui.widgets import Container, PushButton, Label, LineEdit

CELL_LAYER_DEFAULT = "DIC masks"
BUD_LAYER_DEFAULT = "bud masks"
LINKS_LAYER = "draw bud <-> mother lines"   # lines you draw (the result is shown in "bud \u2192 mother links")
BUD_VALUE = 1


def _at(arr, point):
    """Label value at a point (the last two coordinates are y, x; also works in the 3D view), or 0 if outside."""
    y, x = int(round(float(point[-2]))), int(round(float(point[-1])))
    if 0 <= y < arr.shape[0] and 0 <= x < arr.shape[1]:
        return int(arr[y, x])
    return 0


def _bbox_rect(bbox):
    r0, c0, r1, c1 = bbox
    return np.array([[r0, c0], [r0, c1], [r1, c1], [r1, c0]])


def _layer(viewer, name):
    return viewer.layers[name] if name in viewer.layers else None


def _refresh_overlays(viewer, dic, bud_masks, bud_area_fraction=0.5):
    """Redraw the 'bud -> mother links' layer, and the 'potential buds' rectangles if that layer is shown.

    'potential buds' (cells small relative to the median) are suggestions for annotating by hand; they
    are only redrawn when that layer already exists (not after automatic bud classification).
    """
    from ._bud_links import update_links
    if "potential buds" in viewer.layers:
        props = regionprops(dic)
        areas = np.array([p.area for p in props], dtype=float)
        thr = bud_area_fraction * (float(np.median(areas)) if areas.size else 0.0)
        bud_rects = [_bbox_rect(p.bbox) for p in props if p.area < thr]
        layer = viewer.layers["potential buds"]
        layer.data = bud_rects if bud_rects else []
    if "mother-bud pairs" in viewer.layers:             # replaced by the links layer
        viewer.layers.remove(viewer.layers["mother-bud pairs"])
    return update_links(viewer)


def apply_drawn_lines(viewer, cell_layer=CELL_LAYER_DEFAULT, bud_layer=BUD_LAYER_DEFAULT):
    """
    Apply the lines drawn in the 'draw bud <-> mother lines' layer to the cell masks (see the module
    docstring), clear the lines and redraw the bud -> mother links. Returns a short summary.
    Without drawn lines it only redraws the links.
    """
    from ._bud_links import update_links
    cells = _layer(viewer, cell_layer)
    if cells is None or not hasattr(cells, "data"):
        return f"No labels layer named '{cell_layer}'."
    links = _layer(viewer, LINKS_LAYER)
    if links is None or len(links.data) == 0:
        pairs, orphans = update_links(viewer, cell_layer, bud_layer)
        return f"No lines drawn. {pairs} bud(s) linked to a mother, {orphans} without mother."

    dic = np.asarray(cells.data)
    buds_layer = _layer(viewer, bud_layer)
    bud_masks = np.asarray(buds_layer.data).copy() if buds_layer is not None else None
    bud_cc = cc_label(bud_masks == BUD_VALUE, connectivity=2) if bud_masks is not None else None

    merged = created = linked_before = 0
    problems = []
    for n, line in enumerate(links.data, start=1):
        ends = (line[0], line[-1])
        on_bud = [(_at(bud_cc, p) if bud_cc is not None else 0) for p in ends]
        on_cell = [_at(dic, p) for p in ends]

        if (on_bud[0] > 0) != (on_bud[1] > 0):
            # one end on a painted bud (the bud), the other end on the mother
            k = 0 if on_bud[0] > 0 else 1
            mother = on_cell[1 - k]
            if mother == 0:
                problems.append(f"line {n}: the mother end is not on a cell"); continue
            region = bud_cc == on_bud[k]
            changed = False
            # the bud's own cell (the cell at the bud end of the line, and any cell lying mostly under
            # the painted bud) is merged into the mother
            labels, counts = np.unique(dic[region], return_counts=True)
            own = {lab for lab, cnt in zip(labels, counts) if cnt > 0.5 * (dic == lab).sum()} | {on_cell[k]}
            for lab in own - {0, mother}:
                dic[dic == lab] = mother; changed = True
            # painted pixels outside any cell become part of the mother (other cells are never touched)
            empty = region & (dic == 0)
            if empty.any():
                dic[empty] = mother; changed = True
            # paint that spilled onto other cells is not part of this bud: give it back to those cells
            if bud_masks is not None:
                for lab in np.unique(dic[region]):
                    if lab not in (0, mother):
                        spill = region & (dic == lab)
                        bud_masks[spill] = 3 if (bud_masks[(dic == lab) & ~region] == 3).any() else 2
            if changed:
                created += 1
            else:
                linked_before += 1
        elif on_bud[0] == 0 and on_bud[1] == 0 and on_cell[0] > 0 and on_cell[1] > 0 and on_cell[0] != on_cell[1]:
            # both ends on cells, no painted bud: the smaller cell is the bud, merged into the larger
            a, b = on_cell
            bud, mother = (a, b) if (dic == a).sum() <= (dic == b).sum() else (b, a)
            region = dic == bud
            dic[region] = mother
            if bud_masks is not None:
                bud_masks[region] = BUD_VALUE      # bud stays a bud
            merged += 1
        elif on_bud[0] > 0 and on_bud[1] > 0:
            problems.append(f"line {n}: both ends are on a painted bud - end one line on the mother")
        else:
            problems.append(f"line {n}: needs one end on the bud (painted, or its own cell) and one on the mother")

    cells.data = dic
    cells.refresh()
    if buds_layer is not None:
        buds_layer.data = bud_masks
        buds_layer.refresh()
    links.data = []
    pairs, orphans = _refresh_overlays(viewer, dic, bud_masks)
    return (f"Merged {merged} cell(s), added {created} painted bud(s)"
                    + (f", {linked_before} already linked" if linked_before else "")
                    + f". {pairs} bud(s) linked, {orphans} without mother."
                    + ("\n" + "\n".join(problems) if problems else ""))



def reassign_buds_widget():
    """Reassign or create bud <-> mother links by drawing lines."""
    import napari
    viewer = napari.current_viewer()

    cell_name = LineEdit(label="cell masks layer", value=CELL_LAYER_DEFAULT)
    bud_name = LineEdit(label="bud masks layer", value=BUD_LAYER_DEFAULT)
    new_line_btn = PushButton(text="New line layer (draw bud \u2194 mother)")
    apply_btn = PushButton(text="Apply links")
    status = Label(value="Draw a line linking each bud to its mother, then Apply.")

    def _links(create=False):
        if LINKS_LAYER in viewer.layers:
            return viewer.layers[LINKS_LAYER]
        if create:
            layer = viewer.add_shapes(name=LINKS_LAYER, shape_type="line",
                                      edge_color="yellow", edge_width=4)
            layer.mode = "add_line"
            return layer
        return None

    def _new_line(*_):
        layer = _links(create=True)
        layer.mode = "add_line"
        viewer.layers.selection.active = layer
        status.value = "Draw a line from each bud to its mother, then Apply."

    def _apply(*_):
        status.value = apply_drawn_lines(viewer, cell_name.value, bud_name.value)

    new_line_btn.clicked.connect(_new_line)
    apply_btn.clicked.connect(_apply)

    return Container(widgets=[cell_name, bud_name,
                              new_line_btn, apply_btn, status])
