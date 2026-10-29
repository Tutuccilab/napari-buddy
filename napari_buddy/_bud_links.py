"""
Show which bud belongs to which mother: a line from each bud to its mother.

A bud is linked to its mother by sharing the mother's label in the cell masks ('DIC masks');
the bud itself is marked with 1 in the 'bud masks' layer. The links are computed from these two
layers only, so they always show the current state (bud model, painting by hand, or the
'Reassign buds to mothers' widget):

    red line + dot   from the mother's centre (mother part only) to the bud's centre (dot at the bud)
    white circle     bud without a mother (no cell label under it, or a cell that is only bud)

A bud is the connected bud pixels within one cell (joined through shared edges, as in buddy's bud model), so two
touching buds of different mothers stay separate.

Light module (numpy + skimage); napari is only used through the viewer passed in.
"""
import numpy as np
from skimage.measure import label as cc_label
from skimage.measure import regionprops

try:     # the bud-mask values are defined once, in buddy (shared with its bud model)
    from buddy.buds.bud_tools import BACKGROUND, BUD, MOTHER
except ImportError:                                     # buddy 0.1.0
    from buddy.bud_tools import BUD

LINKS_LAYER = "bud → mother links"
BUD_VALUE = BUD


def bud_mask_colormap():
    """
    Fixed colours for the 'bud masks' layer: bud red, mother a faint white, background (value 2 in the file, or 0
    after the eraser) transparent. Without it napari colours the background and the mothers like any other label.
    """
    from napari.utils.colormaps import DirectLabelColormap
    return DirectLabelColormap(color_dict={BUD: (1.0, 0.0, 0.0, 1.0), MOTHER: (1.0, 1.0, 1.0, 0.25),
                                           BACKGROUND: (0.0, 0.0, 0.0, 0.0), 0: (0.0, 0.0, 0.0, 0.0),
                                           None: (0.0, 0.0, 0.0, 0.0)})
LINK_COLOUR = "red"
ORPHAN_COLOUR = "white"


def bud_links(cell_masks, bud_masks):
    """
    Returns (pairs, orphans):
      pairs   : list of (bud_centre, mother_centre, mother_label), centres as (y, x)
      orphans : list of bounding boxes (y0, x0, y1, x1) of buds without a mother
    """
    cell_masks = np.asarray(cell_masks)
    bud_masks = np.asarray(bud_masks)
    is_bud = bud_masks == BUD_VALUE
    # centre of each mother = centre of its label without the bud pixels
    mother_part = np.where(is_bud, 0, cell_masks)
    mother_centres = {p.label: p.centroid for p in regionprops(mother_part)}

    pairs, orphans = [], []
    # connected bud pixels per cell label (label + 1, so buds painted on background form their own group)
    buds_per_cell = cc_label(np.where(is_bud, cell_masks.astype(np.int64) + 1, 0), background=0, connectivity=1)
    for bud in regionprops(buds_per_cell):
        under = cell_masks[bud.coords[:, 0], bud.coords[:, 1]]
        under = under[under > 0]
        mother = int(np.bincount(under).argmax()) if under.size else 0
        if mother and mother in mother_centres:
            pairs.append((bud.centroid, mother_centres[mother], mother))
        else:
            orphans.append(bud.bbox)
    return pairs, orphans


def _box(y0, x0, y1, x1):
    """Four corners of a box. (napari reads an ellipse given as 2 points as centre + radii, not as 2 corners.)"""
    return np.array([[y0, x0], [y0, x1], [y1, x1], [y1, x0]], dtype=float)


def links_layer_data(cell_masks, bud_masks, visible=True):
    """Layer data tuple (data, kwargs, 'shapes') with the link lines, bud dots and orphan circles."""
    pairs, orphans = bud_links(cell_masks, bud_masks)
    shapes, types, colours, faces, mothers = [], [], [], [], []
    for (by, bx), (my, mx), mother in pairs:
        shapes.append(np.array([[my, mx], [by, bx]]))
        types.append("line"); colours.append(LINK_COLOUR); faces.append("transparent"); mothers.append(mother)
        shapes.append(_box(by - 3, bx - 3, by + 3, bx + 3))                         # dot on the bud end
        types.append("ellipse"); colours.append(LINK_COLOUR); faces.append(LINK_COLOUR); mothers.append(mother)
    for y0, x0, y1, x1 in orphans:
        shapes.append(_box(y0 - 4, x0 - 4, y1 + 4, x1 + 4))
        types.append("ellipse"); colours.append(ORPHAN_COLOUR); faces.append("transparent"); mothers.append(0)

    kwargs = dict(name=LINKS_LAYER, shape_type=types, edge_color=colours, face_color=faces, edge_width=2,
                  features={"mother": mothers}, visible=visible, metadata={"group": "masks"})
    if not shapes:                          # empty layer (napari needs at least the kwargs to be consistent)
        kwargs.update(shape_type="line", edge_color=LINK_COLOUR, face_color="transparent", features=None)
    return shapes, kwargs, "shapes"


def update_links(viewer, cell_layer="DIC masks", bud_layer="bud masks"):
    """
    Redraw the links from the current cell and bud masks; returns (n_pairs, n_orphans).
    The existing links layer is updated in place (no layer is removed or added), so other widgets
    that follow the layer list are not disturbed.
    """
    if cell_layer not in viewer.layers or bud_layer not in viewer.layers:
        return 0, 0
    cells = np.asarray(viewer.layers[cell_layer].data)
    buds = np.asarray(viewer.layers[bud_layer].data)
    shapes, kwargs, _ = links_layer_data(cells, buds)
    types = kwargs["shape_type"] if shapes else []

    if LINKS_LAYER in viewer.layers:
        layer = viewer.layers[LINKS_LAYER]
        layer.data = []                                    # clear, then add the new shapes
        if shapes:
            layer.add(shapes, shape_type=types, edge_color=kwargs["edge_color"],
                      face_color=kwargs["face_color"], edge_width=kwargs["edge_width"])
            layer.features = {"mother": kwargs["features"]["mother"]}
    else:                                                  # first time: add the layer just above the bud masks
        layer = viewer.add_shapes(shapes if shapes else None, **{k: v for k, v in kwargs.items() if v is not None})
        viewer.layers.move(viewer.layers.index(layer), viewer.layers.index(viewer.layers[bud_layer]) + 1)
    pairs = sum(1 for t in types if t == "line")
    return pairs, len(shapes) - 2 * pairs
