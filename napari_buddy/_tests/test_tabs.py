"""
The layer dropdowns of the tabbed panels follow the layer list (_tabs._sync_layer_choices), with napari's
ViewerModel (no window). napari only refreshes the dropdowns of the widget it docks, which is the tab container.
"""
import numpy as np
from napari.components import ViewerModel

from napari_buddy._tabs import _sync_layer_choices


class _Widget:
    """Stands in for a magicgui widget: counts how often napari-buddy asks it to refresh its dropdowns."""

    def __init__(self):
        self.resets = 0

    def reset_choices(self, *_):
        self.resets += 1


def test_dropdowns_refresh_when_layers_change():
    v = ViewerModel()
    v.add_image(np.zeros((4, 4)), name="first")
    w = _Widget()
    _sync_layer_choices(w, v.layers)
    assert w.resets == 0

    v.add_image(np.zeros((4, 4)), name="second")                    # a new layer
    assert w.resets == 1
    v.layers["second"].name = "second renamed"                       # renaming the new one
    assert w.resets == 2
    v.layers["first"].name = "first renamed"                         # renaming one that existed before
    assert w.resets == 3
    v.layers.move(0, 2)                                              # reordering
    assert w.resets == 4
    v.layers.remove("first renamed")                                 # removing
    assert w.resets == 5


def test_widgets_without_dropdowns_are_left_alone():
    v = ViewerModel()
    _sync_layer_choices(object(), v.layers)                          # no reset_choices: nothing to connect
    v.add_image(np.zeros((4, 4)))
