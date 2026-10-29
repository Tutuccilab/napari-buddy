"""
Widgets to call Big-FISH functions. When PyTorch can use a GPU, the slow filtering steps (background filter,
Laplacian-of-Gaussian + local maxima, decomposition denoising) run on the GPU with buddy.spots.gpu_detection, which
gives the same result as Big-FISH; otherwise Big-FISH runs on the CPU.
"""

from typing import List

import napari
from bigfish import detection, stack
from buddy.config import DECOMPOSITION_DEFAULTS
from buddy.experiment import Experiment
from buddy.image import Image
from buddy.spots import gpu_detection as gpu_spots
from magicgui import magic_factory


def _on_gpu(gpu, cpu):
    """gpu(device) when a GPU is available (Big-FISH on the CPU if that fails), otherwise cpu()."""
    device = gpu_spots.gpu_device()
    if device is not None:
        try:
            return gpu(device)
        except RuntimeError:                       # e.g. GPU out of memory
            import torch
            torch.cuda.empty_cache()
    return cpu()

from pathlib import Path

import numpy as np
import pandas as pd
from skimage import io


@magic_factory(
    cfg_file={"label": "Config file"},
    vsi_file={"label": "VSI file"},
    cell_file={"label": "DIC file"},
)
def read_in_vsi_widget(
        cfg_file=Path.home(),
        vsi_file=Path.home(),
        cell_file=Path.home(),
) -> List[napari.types.LayerDataTuple]:
    """Read one microscope image (the .vsi and its DIC file) with the config's channels; fields start at the example set."""

    img = Image.from_dict(params={ "vsi_file": vsi_file, "cell_file": cell_file }, exp=Experiment.from_cfg_file(cfg_file=cfg_file))
    img.read_image()   # -> img.mrna[ch]['data']
    img.read_cells()   # -> img.cells (the DIC image)

    # DIC image + one layer per fluorescence channel (raw, unaligned: spot-based
    # alignment happens later in the pipeline, once spots and masks exist).
    # prefer the aligned DIC if a previous run produced it, else the raw DIC
    dic = img.cells
    savepath = getattr(img, 'savepath', None)
    if savepath:
        aligned_dic = Path(savepath) / 'aligned_DIC.tif'
        if aligned_dic.is_file():
            dic = io.imread(aligned_dic)

    layer_data_tuples = []
    layer_data_tuples.append((dic, { 'name': "DIC", 'colormap': 'grey', 'visible': True, 'blending': 'additive' }, 'image'))
    for ch, data in reversed(img.mrna.items()):
        colormap = img.experiment.channels[ch].get('colormap', 'gray')
        layer_data_tuples.append((data['data'], { 'name': ch, 'colormap': colormap, 'visible': False, 'blending': 'additive' }, 'image'))

    return layer_data_tuples


@magic_factory(
    sigma_z={"widget_type": "FloatSlider", "max": 5},
    sigma_yx={"widget_type": "FloatSlider", "max": 5},
    auto_call=False
)
def background_filtering_magic_widget(
    img_layer: "napari.layers.Image", sigma_z: "float" = 0.75, sigma_yx: "float" = 2.3
) -> "napari.types.LayerDataTuple":
    sigma = (sigma_z, sigma_yx, sigma_yx)
    filtered = _on_gpu(lambda device: gpu_spots.remove_background(img_layer.data, sigma, device=device),
                       lambda: stack.remove_background_gaussian(img_layer.data, sigma))
    return (filtered,
            { 'name': f'{img_layer.name} background filtered', 'metadata': { 'channel' : img_layer.name } }, 'image')


@magic_factory(
    threshold={"widget_type": "IntSlider", "min": 0, "max": 200},
    scale_z={"widget_type": "FloatSlider", "max": 2000},
    scale_yx={"widget_type": "FloatSlider", "max": 2000},
    spot_radius_z={"widget_type": "FloatSlider", "max": 2000},
    spot_radius_yx={"widget_type": "FloatSlider", "max": 2000},
    auto_call=False
)
def spot_detection_magic_widget(
    viewer: "napari.Viewer",
    img_layer: "napari.layers.Image",
    threshold: int=50,
    scale_z: float=200, scale_yx: float=65,
    spot_radius_z: float=800, spot_radius_yx: float=120,
) -> List[napari.types.LayerDataTuple]:
    # if we return the mask and the LoG filtered image as layers, then we can re-threshold
    # the spots *after* spot detection

    # spot radius
    spot_radius_px = detection.get_object_radius_pixel(
        voxel_size_nm=(scale_z, scale_yx, scale_yx),
        object_radius_nm=(spot_radius_z, spot_radius_yx, spot_radius_yx),
        ndim=3)

    # LoG filter + local maximum detection (on the GPU when available)
    voxel, radius = (scale_z, scale_yx, scale_yx), (spot_radius_z, spot_radius_yx, spot_radius_yx)
    def _cpu():
        rna_log = stack.log_filter(img_layer.data, sigma=spot_radius_px)
        return rna_log, detection.local_maximum_detection(rna_log, min_distance=spot_radius_px)
    rna_log, mask = _on_gpu(lambda device: gpu_spots.log_and_local_maxima(img_layer.data, voxel, radius, device=device),
                            _cpu)

    spots, features = threshold_spots(rna_log, mask, threshold)

    # if we have DIC masks, we add the cell labels to the spot
    # features for display purposes
    if 'DIC masks' in viewer.layers:
        cell_masks = viewer.layers['DIC masks'].data
        features['label'], features['in_cell'] = get_labels(cell_masks, spots)

    spots_metadata = dict(img_layer.metadata)      # a copy: the layers must not share one dict
    channel = spots_metadata['channel']
    spots_metadata.update({
        'threshold': threshold,
        'scale': (scale_z, scale_yx, scale_yx),
        'spot_radius': (spot_radius_z, spot_radius_yx, spot_radius_yx)
    })

    # the LoG image and the local maxima are kept (hidden) so that Threshold can re-threshold without recomputing
    return [
        (rna_log, { 'name': f'{channel} LoG filtered', 'metadata': img_layer.metadata, 'visible': False }, 'image'),
        (mask, { 'name': f'{channel} local maxima', 'metadata': img_layer.metadata, 'visible': False }, 'labels'),
        (spots, {
            'name': f'{channel} spots detected thr={threshold}',
            'features': features,
            'metadata': spots_metadata,
            'symbol': 'disc',
            'size': 10,
            'border_width': 0.1,
            'border_color': 'in_cell',
            'border_color_cycle': _border_cycle(features),
            'face_color': 'transparent',
            'opacity': 0.5,
            'out_of_slice_display': True
            },
         'points'),
    ]


def threshold_spots(rna_log, mask, threshold):
    spots, _ = detection.spots_thresholding(rna_log, mask, threshold)
    log_intensities = np.resize(np.array([rna_log[s[0], s[1], s[2]] for s in spots]), (len(spots), 1))

    spots_with_intensities = np.concatenate((spots, log_intensities), axis=1)
    features = pd.DataFrame(spots_with_intensities, columns=['z', 'y', 'x', 'intensity_LoG'])
    features['label'] = -1
    features['in_cell'] = pd.Series([IN_CELL] * len(features), dtype='string')

    return spots, features


@magic_factory(
    threshold={"widget_type": "IntSlider", "min": 0, "max": 2000},
    auto_call=False
)
def spot_thresholding_magic_widget(
    viewer: "napari.Viewer",
    img_layer: "napari.layers.Points", threshold: float=50,
) -> "napari.types.LayerDataTuple":
    spots_metadata = dict(img_layer.metadata)      # a copy: the layers must not share one dict
    spots_metadata.update({ 'threshold': threshold})
    channel = spots_metadata['channel']

    rna_log = viewer.layers[f'{channel} LoG filtered'].data
    mask = viewer.layers[f'{channel} local maxima'].data.astype(bool)
    spots, features = threshold_spots(rna_log, mask, threshold)

    # if we have DIC masks, we add the cell labels to the spot
    # features for display purposes
    if 'DIC masks' in viewer.layers:
        cell_masks = viewer.layers['DIC masks'].data
        features['label'], features['in_cell'] = get_labels(cell_masks, spots)

    return (spots, {
        'name': f'{channel} spots thresholded thr={threshold}',
        'features': features,
        'metadata': spots_metadata,
        'symbol': 'disc',
        'size': 10,
        'border_width': 0.1,
        'border_color': 'in_cell',
        # this breaks if we don't have features, ie when reading img.json
        # actually we do have features when reading img.json
        'border_color_cycle': _border_cycle(features),
        'face_color': 'transparent',
        'opacity': 0.5,
        'out_of_slice_display': True
    },
            'points')


IN_CELL, OUTSIDE = 'in a cell', 'outside'           # the in_cell feature of the spot layers (text, so napari takes it as
                                                    # categorical without the "looks like categorical data" warning)


def get_labels(cell_masks, spots):
    labels = [ cell_masks[y, x] for (y, x) in spots[:, 1:3] ]
    in_cell = [ OUTSIDE if l == 0 else IN_CELL for l in labels ]
    return pd.Series(labels, dtype='int64'), pd.Series(in_cell, dtype='string')


def _border_cycle(features):
    """cyan for spots in a cell, red outside - in the order napari meets the values (first row first)."""
    return ['cyan', 'red'] if features.iloc[0]['in_cell'] == IN_CELL else ['red', 'cyan']


@magic_factory(
    auto_call=False,
    alpha={"min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "intensity of one molecule as a fraction of the reference spot; lower = more molecules per dense region"},
    beta={"min": 0.0, "max": 100.0, "step": 0.5, "tooltip": "a dense region must be at least beta x the reference spot; lower = more regions"},
    gamma={"min": 0.0, "max": 10.0, "step": 0.5, "tooltip": "width of the denoising filter before the regions are found (x spot radius)"},
)
def spot_decomposition_magic_widget(
    viewer: "napari.Viewer",
    point_layer: "napari.layers.Points",
    alpha: float = DECOMPOSITION_DEFAULTS["alpha"],
    beta: float = DECOMPOSITION_DEFAULTS["beta"],
    gamma: float = DECOMPOSITION_DEFAULTS["gamma"],
) -> List[napari.types.LayerDataTuple]:
    """Big-FISH decompose_dense on a spots layer; alpha / beta / gamma are the "decomposition" settings of the config's "spots" block."""
    spots = point_layer.data
    metadata = dict(point_layer.metadata)           # a copy: the layers must not share one dict
    channel = metadata['channel']

    rna = viewer.layers[f'{channel}'].data

    settings = dict(alpha=alpha, beta=beta, gamma=gamma)
    decomp_spots, dense_regions, reference_spot = _on_gpu(
        lambda device: gpu_spots.decompose_dense(rna, spots, metadata['scale'], metadata['spot_radius'],
                                                   device=device, **settings),
        lambda: detection.decompose_dense(rna, spots, voxel_size=metadata['scale'],
                                          spot_radius=metadata['spot_radius'], **settings))

    features = pd.DataFrame(decomp_spots, columns=['z', 'y', 'x'])
    features['label'] = -1
    features['in_cell'] = pd.Series([IN_CELL] * len(features), dtype='string')
    # if we have DIC masks, we add the cell labels to the spot
    # features for display purposes
    if 'DIC masks' in viewer.layers:
        cell_masks = viewer.layers['DIC masks'].data
        features['label'], features['in_cell'] = get_labels(cell_masks, decomp_spots)

    metadata.update({'decomposed': 1, 'decomposition': settings})

    regions = pd.DataFrame(dense_regions[:, 3:5], columns=['nb_rna', 'area'])
    return [
        (dense_regions[:, 0:3], {                      # z, y, x: shown on their own z plane, as rings around the spots
            'name': f'{channel} dense regions thr={metadata["threshold"]}',
            'features': regions,
            'symbol': 'ring',
            'size': 16,
            'border_width': 0.15,
            'border_color': 'cyan',
            'face_color': 'transparent',
            'opacity': 0.8
        },
         'points'),
        (decomp_spots, {
            'name': f'{channel} spots decomposed thr={metadata["threshold"]}',
            'features': features,
            'metadata': metadata,
            'symbol': 'x',
            'size': 10,
            'border_width': 0.1,
            'border_color': 'in_cell',
            'border_color_cycle': _border_cycle(features),
            'face_color': 'transparent',
            'opacity': 0.5
        },
         'points')
    ]
