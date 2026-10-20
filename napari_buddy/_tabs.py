"""
The three tabbed panels of the Plugins > Napari Buddy menu. napari lists one flat entry per widget, so the ten
panels are grouped into three docks with tabs instead:

    buddy pipeline    Pipeline | Config
    Spot tuning       Read image | Filter | Detect | Threshold | Decompose
    Correct images    Images | Buds | Layers

Each tab is the unchanged panel of before. The pages are registered with _review._dock_once under their old
names, so code that used to open them as separate docks (the "Create config file..." button of the pipeline
panel, open_for_correction) switches to the tab instead of opening a second copy.
"""


class _TabPage:
    """What _dock_once keeps for a panel that lives in a tab: alive while the tab exists; activate() shows it."""

    def __init__(self, tabs, native):
        self.tabs, self.native = tabs, native

    def isVisible(self):
        return True

    def parent(self):
        return self.tabs

    def activate(self):
        self.tabs.setCurrentWidget(self.native)
        dock = self.tabs.parentWidget()
        while dock is not None and not hasattr(dock, "setFloating"):      # up to the QDockWidget
            dock = dock.parentWidget()
        if dock is not None:
            dock.show()
            dock.raise_()


def _sync_layer_choices(widget, layers):
    """
    Keep the layer dropdowns of a magicgui widget up to date with `layers` (a viewer's LayerList).

    napari does this itself for the widget it docks, but it only sees the QTabWidget here, not the pages inside
    it, so the dropdowns of the tabs would stay as they were when the dock was opened. Same events as napari
    (inserted, removed, reordered), plus layer renames.
    """
    if not hasattr(widget, "reset_choices"):
        return
    for event in (layers.events.inserted, layers.events.removed, layers.events.reordered):
        event.connect(widget.reset_choices)
    for layer in layers:
        layer.events.name.connect(widget.reset_choices)
    layers.events.inserted.connect(lambda event: event.value.events.name.connect(widget.reset_choices))


def _tabbed(pages, register=(), viewer=None):
    """
    A QTabWidget with one tab per (title, factory). register: (dock name, tab title) pairs whose pages are
    registered with _dock_once under that dock name. viewer: the viewer whose layers fill the dropdowns
    (default: the current one).
    """
    import napari
    from qtpy.QtWidgets import QTabWidget

    from ._review import _DOCKED

    if viewer is None:
        viewer = napari.current_viewer()
    tabs = QTabWidget()
    natives = {}
    for title, make in pages:
        widget = make()
        native = getattr(widget, "native", widget)
        tabs.addTab(native, title)
        natives[title] = native
        if viewer is not None:
            _sync_layer_choices(widget, viewer.layers)
    if viewer is not None:
        for dock_name, title in register:
            _DOCKED[(id(viewer), dock_name)] = _TabPage(tabs, natives[title])
    return tabs


def pipeline_tabs():
    """Plugins > Napari Buddy > buddy pipeline: the pipeline panel and the config panel."""
    from ._config_widget import config_widget
    from ._pipeline_widget import pipeline_widget
    return _tabbed([("Pipeline", pipeline_widget), ("Config", config_widget)],
                   register=[("Create config file", "Config")])


def spot_tuning_tabs():
    """Plugins > Napari Buddy > Spot tuning: read an image, then filter, detect, threshold and decompose."""
    from . import _widget
    return _tabbed([("Read image", _widget.read_in_vsi_widget),
                    ("Filter", _widget.background_filtering_magic_widget),
                    ("Detect", _widget.spot_detection_magic_widget),
                    ("Threshold", _widget.spot_thresholding_magic_widget),
                    ("Decompose", _widget.spot_decomposition_magic_widget)])


def correct_tabs():
    """Plugins > Napari Buddy > Correct images: open the images, link buds, show or hide layer groups."""
    from ._bud_widget import reassign_buds_widget
    from ._layer_groups import layer_groups_widget
    from ._review import correct_images_widget
    return _tabbed([("Images", correct_images_widget), ("Buds", reassign_buds_widget), ("Layers", layer_groups_widget)],
                   register=[("Reassign buds to mothers", "Buds"), ("Layer groups", "Layers")])
