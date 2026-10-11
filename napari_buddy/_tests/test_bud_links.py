import numpy as np
from napari_buddy._bud_links import bud_links, links_layer_data


def _example():
    yy, xx = np.ogrid[:100, :100]
    cells = np.zeros((100, 100), np.uint16)
    buds = np.full((100, 100), 2, np.uint8)
    mother, bud = (yy - 30) ** 2 + (xx - 30) ** 2 < 15 ** 2, (yy - 30) ** 2 + (xx - 52) ** 2 < 7 ** 2
    cells[mother | bud] = 1                      # bud merged into its mother (same label)
    buds[bud & ~mother] = 1
    buds[(yy - 80) ** 2 + (xx - 80) ** 2 < 5 ** 2] = 1   # painted bud without a cell
    return cells, buds


def test_bud_links():
    cells, buds = _example()
    pairs, orphans = bud_links(cells, buds)
    assert len(pairs) == 1 and len(orphans) == 1
    (by, bx), (my, mx), mother = pairs[0]
    assert mother == 1 and abs(by - 30) < 1 and bx > 45 and abs(my - 30) < 1 and mx < 32


def test_links_layer_data():
    cells, buds = _example()
    shapes, kwargs, layer_type = links_layer_data(cells, buds)
    assert layer_type == "shapes" and kwargs["shape_type"] == ["line", "ellipse", "ellipse"]
    for shape in shapes:                         # every shape stays near its bud (no huge ellipses)
        assert np.ptp(shape, axis=0).max() < 40 and shape.min() >= -10 and shape.max() <= 110
    shapes, kwargs, _ = links_layer_data(cells, np.full_like(buds, 2))
    assert shapes == []


def test_touching_buds_of_two_mothers():
    """Two buds that touch each other but belong to different mothers give two links."""
    cells = np.zeros((60, 100), np.uint16)
    buds = np.full((60, 100), 2, np.uint8)
    cells[5:25, 10:45] = 1; cells[25:35, 10:45] = 1; buds[25:35, 10:45] = 1      # mother 1 + its bud
    cells[5:25, 55:90] = 2; cells[25:35, 45:90] = 2; buds[25:35, 45:90] = 1      # mother 2 + bud touching bud 1
    pairs, orphans = bud_links(cells, buds)
    assert sorted(m for *_, m in pairs) == [1, 2] and not orphans
