"""
The lines of the Buds tab (apply_drawn_lines) on small synthetic masks, with napari's ViewerModel (no window).

Layout (60 x 60 px): cell 1 on the left, cell 2 on the right, a painted bud (bud masks = 1) between them.
"""
import numpy as np
from napari.components import ViewerModel

from napari_buddy._bud_links import BACKGROUND, BUD, MOTHER, bud_links
from napari_buddy._bud_widget import LINKS_LAYER, apply_drawn_lines

MOTHER_A = (slice(10, 50), slice(5, 25))        # label 1
MOTHER_B = (slice(10, 50), slice(35, 55))       # label 2
BUD_PX = (slice(25, 35), slice(25, 35))         # the bud, touching both cells


def _viewer(bud_in_label):
    """Cells 1 and 2 with the bud painted; the bud's label in DIC masks is `bud_in_label` (0 = own nothing)."""
    dic = np.zeros((60, 60), np.int32)
    dic[MOTHER_A] = 1
    dic[MOTHER_B] = 2
    dic[BUD_PX] = bud_in_label
    buds = np.full((60, 60), BACKGROUND, np.uint8)
    buds[dic > 0] = MOTHER
    buds[BUD_PX] = BUD
    v = ViewerModel()
    v.add_labels(dic, name="DIC masks")
    v.add_labels(buds, name="bud masks")
    return v


def _line(v, start, end):
    v.add_shapes([np.array([start, end], float)], shape_type="line", name=LINKS_LAYER)


def test_line_moves_a_linked_bud_to_the_other_mother():
    v = _viewer(bud_in_label=1)                              # the model linked the bud to cell 1
    _line(v, (30, 30), (30, 45))                             # from the bud to cell 2
    msg = apply_drawn_lines(v)
    dic = np.asarray(v.layers["DIC masks"].data)
    buds = np.asarray(v.layers["bud masks"].data)
    assert "moved 1 bud(s) to another mother" in msg and "less than half" not in msg
    assert (dic[BUD_PX] == 2).all()                          # the bud now belongs to cell 2
    assert (dic[MOTHER_A] == 1).all()                        # the rest of cell 1 is untouched
    assert (buds[BUD_PX] == BUD).all()                       # and is still marked as bud
    pairs, orphans = bud_links(dic, buds)
    assert [m for _, _, m in pairs] == [2] and not orphans
    assert len(v.layers[LINKS_LAYER].data) == 0             # the drawn line is cleared


def test_line_to_the_current_mother_changes_nothing():
    v = _viewer(bud_in_label=1)
    _line(v, (30, 30), (30, 15))                             # from the bud to its own mother
    msg = apply_drawn_lines(v)
    assert "1 already linked" in msg
    assert (np.asarray(v.layers["DIC masks"].data)[BUD_PX] == 1).all()


def test_painted_bud_on_background_is_added_to_the_mother():
    v = _viewer(bud_in_label=0)                              # painted bud, not part of any cell
    _line(v, (30, 30), (30, 45))
    msg = apply_drawn_lines(v)
    assert "added 1 painted bud(s)" in msg
    assert (np.asarray(v.layers["DIC masks"].data)[BUD_PX] == 2).all()


def test_two_unpainted_cells_merge_the_smaller_into_the_larger():
    v = _viewer(bud_in_label=0)
    dic = np.asarray(v.layers["DIC masks"].data).copy()
    buds = np.asarray(v.layers["bud masks"].data).copy()
    dic[BUD_PX] = 3; buds[BUD_PX] = MOTHER                   # the bud is a small cell of its own, unpainted
    v.layers["DIC masks"].data = dic; v.layers["bud masks"].data = buds
    _line(v, (30, 30), (30, 15))
    msg = apply_drawn_lines(v)
    assert "Merged 1 cell(s)" in msg
    assert (np.asarray(v.layers["DIC masks"].data)[BUD_PX] == 1).all()
    assert (np.asarray(v.layers["bud masks"].data)[BUD_PX] == BUD).all()


def test_bud_mask_colormap_hides_background_and_paints_buds_red():
    from napari_buddy._bud_links import bud_mask_colormap
    cmap = bud_mask_colormap()
    rgba = cmap.map(np.array([BACKGROUND, BUD, MOTHER, 0]))
    assert rgba[0][3] == 0 and rgba[3][3] == 0                  # background (file value 2, or 0 after erasing): transparent
    assert tuple(rgba[1][:3]) == (1.0, 0.0, 0.0) and rgba[1][3] == 1.0   # bud: red
    assert 0 < rgba[2][3] < 0.5                                 # mother: faint
