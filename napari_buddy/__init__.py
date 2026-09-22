__version__ = "0.0.4"

# Light modules: safe to import eagerly (no torch / no Java / no buddy).
from ._reader import napari_get_reader
from ._sample_data import make_sample_data, smRNAfish_Ecoli_rpoD_rnlAB_hipBA, get_smRNAfish_Ecoli_rpoD_rnlAB_hipBA
from ._config_widget import config_widget, build_config, save_config
from ._bud_widget import reassign_buds_widget

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
    "config_widget",
    "reassign_buds_widget",
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
