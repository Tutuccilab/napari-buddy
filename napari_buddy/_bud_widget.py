"""
napari widget: reassign / create bud <-> mother links by drawing lines.

Workflow
--------
1. Click "New line layer" - adds a 'bud <-> mother links' Shapes layer in
   line-drawing mode.
2. Draw a short line between a bud and its mother (either direction):
     * bud already segmented as its own DIC cell -> that cell is merged into the
       mother;
     * bud missing from the DIC segmentation -> first paint it in the 'bud masks'
       layer (label 1), then draw a line from the painted bud to a nearby DIC
       cell: the painted region is added to that cell.
3. Click "Apply links". The chosen Labels layer is edited in place, the
   'potential buds' and 'mother-bud pairs' rectangles are redrawn, and the
   processed lines are cleared.

Light module (numpy + skimage + magicgui; napari imported lazily).
"""
import numpy as np
from skimage.measure import regionprops, label as cc_label
from magicgui.widgets import Container, PushButton, Label, LineEdit

CELL_LAYER_DEFAULT = "DIC masks"
BUD_LAYER_DEFAULT = "bud masks"
LINKS_LAYER = "bud <-> mother links"
BUD_VALUE = 1


def _at(arr, point):
    """Label value at a (y, x) point, or 0 if out of bounds."""
    y, x = int(round(float(point[0]))), int(round(float(point[1])))
    if 0 <= y < arr.shape[0] and 0 <= x < arr.shape[1]:
        return int(arr[y, x])
    return 0


def _bbox_rect(bbox):
    r0, c0, r1, c1 = bbox
    return np.array([[r0, c0], [r0, c1], [r1, c1], [r1, c0]])


def _layer(viewer, name):
    return viewer.layers[name] if name in viewer.layers else None


def _refresh_overlays(viewer, dic, bud_masks, bud_area_fraction=0.5):
    """Redraw the 'potential buds' (small cells) and 'mother-bud pairs' rectangles.

    'potential buds' are recomputed fresh each time (they're just suggestions).
    'mother-bud pairs' are *kept*: any rectangles already on that layer are read
    back in and the newly computed pairs are added to them (exact duplicates
    dropped), so earlier pairs are never overwritten.
    """
    # potential buds = cells small relative to the median
    props = regionprops(dic)
    areas = np.array([p.area for p in props], dtype=float)
    median = float(np.median(areas)) if areas.size else 0.0
    thr = bud_area_fraction * median
    bud_rects = [_bbox_rect(p.bbox) for p in props if p.area < thr]

    # existing pair rectangles (read them in before we redraw the layer)
    pair_rects = []
    if "mother-bud pairs" in viewer.layers:
        pair_rects = [np.asarray(s) for s in viewer.layers["mother-bud pairs"].data]

    # newly computed pairs = each bud annotation -> the DIC cell under it, boxed
    if bud_masks is not None:
        bud_cc = cc_label(bud_masks == BUD_VALUE, connectivity=2)
        seen = set()
        for comp in range(1, int(bud_cc.max()) + 1):
            under = dic[bud_cc == comp]
            under = under[under > 0]
            if under.size == 0:
                continue
            mother = int(np.bincount(under).argmax())
            if mother in seen:
                continue
            seen.add(mother)
            ys, xs = np.where(dic == mother)
            rect = _bbox_rect((ys.min(), xs.min(), ys.max() + 1, xs.max() + 1))
            if not any(rect.shape == e.shape and np.array_equal(rect, e) for e in pair_rects):
                pair_rects.append(rect)

    for name in ("potential buds", "mother-bud pairs"):
        if name in viewer.layers:
            viewer.layers.remove(viewer.layers[name])
    if bud_rects:
        viewer.add_shapes(bud_rects, name="potential buds", shape_type="rectangle",
                          edge_color="yellow", edge_width=6, face_color="transparent")
    if pair_rects:
        viewer.add_shapes(pair_rects, name="mother-bud pairs", shape_type="rectangle",
                          edge_color="magenta", edge_width=6, face_color="transparent")


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
        cells = _layer(viewer, cell_name.value)
        if cells is None or not hasattr(cells, "data"):
            status.value = f"No labels layer named '{cell_name.value}'."
            return
        links = _links()
        if links is None or len(links.data) == 0:
            status.value = "No lines drawn."
            return

        dic = np.asarray(cells.data)
        buds_layer = _layer(viewer, bud_name.value)
        bud_masks = np.asarray(buds_layer.data).copy() if buds_layer is not None else None
        bud_cc = cc_label(bud_masks == BUD_VALUE, connectivity=2) if bud_masks is not None else None

        merged = created = skipped = 0
        for line in links.data:
            a, b = _at(dic, line[0]), _at(dic, line[-1])
            if a > 0 and b > 0 and a != b:
                # both endpoints on cells -> smaller (bud) into larger (mother)
                bud, mother = (a, b) if (dic == a).sum() <= (dic == b).sum() else (b, a)
                region = dic == bud
                dic[region] = mother
                if bud_masks is not None:
                    bud_masks[region] = BUD_VALUE      # bud stays a bud
                merged += 1
            elif (a > 0) ^ (b > 0):
                # one endpoint on a cell (mother), the other on a painted bud
                mother = a if a > 0 else b
                bud_point = line[-1] if a > 0 else line[0]
                comp = _at(bud_cc, bud_point) if bud_cc is not None else 0
                if comp > 0:
                    region = bud_cc == comp
                    dic[region] = mother               # add the painted bud to the mother
                    if bud_masks is not None:
                        bud_masks[region] = BUD_VALUE  # bud stays a bud
                    created += 1
                else:
                    skipped += 1                       # no painted bud at that end
            else:
                skipped += 1

        cells.data = dic
        cells.refresh()
        if buds_layer is not None:
            buds_layer.data = bud_masks
            buds_layer.refresh()
        links.data = []
        _refresh_overlays(viewer, dic, bud_masks)
        status.value = f"Merged {merged}, created {created}, skipped {skipped}."

    new_line_btn.clicked.connect(_new_line)
    apply_btn.clicked.connect(_apply)

    return Container(widgets=[cell_name, bud_name,
                              new_line_btn, apply_btn, status])
