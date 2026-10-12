__version__ = "0.2.0"

# buddy versions this plugin works with: from MIN_BUDDY up to and including the MAX_BUDDY minor version
MIN_BUDDY = (0, 1, 0)
MAX_BUDDY = (0, 3)


def _check_buddy():
    """Warn (once, at import) when the installed buddy is older or newer than this napari-buddy supports."""
    import re
    import warnings
    from importlib.metadata import PackageNotFoundError, version
    try:
        installed = version("buddy")
    except PackageNotFoundError:
        return                                  # buddy missing: the plugin's own imports say so
    v = tuple(int(x) for x in re.findall(r"\d+", installed)[:3])
    if v < MIN_BUDDY:
        warnings.warn(f"buddy {installed} is too old for napari-buddy {__version__}: update buddy to "
                      f"{'.'.join(map(str, MIN_BUDDY))} or newer", stacklevel=2)
    elif v[:2] > MAX_BUDDY:
        warnings.warn(f"buddy {installed} is newer than napari-buddy {__version__} knows (up to "
                      f"{'.'.join(map(str, MAX_BUDDY))}.x): update napari-buddy", stacklevel=2)


try:
    _check_buddy()
except Exception:      # a version check must never stop the plugin from loading
    pass

# Light modules: safe to import eagerly (no torch / no Java / no buddy).
from ._reader import napari_get_reader
from ._sample_data import make_sample_data, smRNAfish_Ecoli_rpoD_rnlAB_hipBA, get_smRNAfish_Ecoli_rpoD_rnlAB_hipBA
from ._config_widget import config_widget, build_config, save_config
from ._bud_widget import reassign_buds_widget
from ._layer_groups import layer_groups_widget
from ._bud_links import update_links
from ._review import open_for_correction, save_corrections, review_images
from ._pipeline_widget import pipeline_widget

# Heavy widgets live in ._widget, which imports buddy (-> big-fish / omnipose /
# bio-formats). Importing that at package load makes *everything* slow - even
# opening the config widget or using the reader. So we expose those names lazily
# via PEP 562: they are imported only when actually accessed (i.e. when napari
# instantiates that specific widget).
_LAZY_WIDGETS = {
    "read_in_vsi_widget",
    "background_filtering_magic_widget",
    "spot_detection_magic_widget",
    "spot_thresholding_magic_widget",
    "spot_decomposition_magic_widget",
}


def __getattr__(name):
    if name in _LAZY_WIDGETS:
        import importlib
        module = importlib.import_module("._widget", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = (
    "napari_get_reader",
    "pipeline_widget",
    "config_widget",
    "reassign_buds_widget",
    "layer_groups_widget",
    "update_links",
    "open_for_correction",
    "save_corrections",
    "review_images",
    "build_config",
    "save_config",
    "read_in_vsi_widget",
    "background_filtering_magic_widget",
    "spot_detection_magic_widget",
    "spot_thresholding_magic_widget",
    "spot_decomposition_magic_widget",
    "make_sample_data",
    "smRNAfish_Ecoli_rpoD_rnlAB_hipBA",
    "get_smRNAfish_Ecoli_rpoD_rnlAB_hipBA",
)
