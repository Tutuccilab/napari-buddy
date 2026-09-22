"""
This module is an example of a barebones numpy reader plugin for napari.

It implements the Reader specification, but your plugin may choose to
implement multiple readers or even other plugin contributions. see:
https://napari.org/stable/plugins/guides.html?#readers
"""
import numpy as np
import pandas as pd
import json
from skimage import io
from pathlib import Path
from skimage import io
from textwrap import dedent
from napari.utils.notifications import show_info

def napari_get_reader(path):
    """A basic implementation of a Reader contribution.

    Parameters
    ----------
    path : str or list of str
        Path to file, or list of paths.

    Returns
    -------
    function or None
        If the path is a recognized format, return a function that accepts the
        same path or list of paths, and returns a list of layer data tuples.
    """
    if isinstance(path, list):
        # reader plugins may be handed single path, or a list of paths.
        # if it is a list, it is assumed to be an image stack...
        # so we are only going to look at the first file.
        path = path[0]

    # if we know we cannot read the file, we immediately return None.
    if not path.endswith(".json"):
        return None

    # otherwise we return the *function* that can read ``path``.
    return reader_function


def reader_function(path):
    """Take a path or list of paths and return a list of LayerData tuples.

    Readers are expected to return data as a list of tuples, where each tuple
    is (data, [add_kwargs, [layer_type]]), "add_kwargs" and "layer_type" are
    both optional.

    Parameters
    ----------
    path : str
        Path to img.json file

    Returns
    -------
    layer_data : list of tuples
        A list of LayerData tuples where each tuple in the list contains
        (data, metadata, layer_type), where data is a numpy array, metadata is
        a dict of keyword arguments for the corresponding viewer.add_* method
        in napari, and layer_type is a lower-case string naming the type of
        layer. Both "meta", and "layer_type" are optional. napari will
        default to layer_type=="image" if not provided
    """
    # handle both a string and a list of strings
    # paths = [path] if isinstance(path, str) else path
    # # load all files into array
    # arrays = [np.load(_path) for _path in paths]
    # # stack arrays into single array
    # data = np.squeeze(np.stack(arrays))
    #
    # # optional kwargs for the corresponding viewer.add_* method
    # add_kwargs = {}
    #
    # layer_type = "image"  # optional, default is "image"
    #
    # return [(data, add_kwargs, layer_type)]

    layer_tuples = read_smfish_json(path)
    pass
    return layer_tuples

def read_smfish_json(path):
    import json
    import numpy as np
    import pandas as pd
    from pathlib import Path
    from skimage import io

    # Choose the best available version of a layer. Masks prefer the manually
    # corrected copy, then the aligned copy, then the raw segmentation. The DIC
    # image prefers its aligned copy. Returns the first candidate that exists
    # (or the last one, which is then skipped if it is also missing).
    _base = Path(path).parent
    def _prefer(*candidates):
        for c in candidates:
            if (_base / c).exists():
                return c
        return candidates[-1]

    # cell-mask file used both as a layer and to colour spots by their cell label
    dic_mask_file = _prefer('corrected/DIC_corrected_masks.tif', 'aligned_DIC_masks.tif', 'DIC_masks_pp.tif')
    _mp = _base / dic_mask_file
    cell_mask = io.imread(_mp) if _mp.exists() else None

    layer_list = [
        # Static layers
        { 'file': _prefer('aligned_DIC.tif', 'DIC.tif'), 'layer_type': "image",
          'add_kwargs': { 'name': "DIC", 'colormap': 'grey', 'visible': True, 'blending': 'additive' } },
        { 'file': dic_mask_file, 'layer_type': 'labels',
          'add_kwargs': { 'name': "DIC masks", 'visible': False, 'blending': 'additive', 'opacity': 0.2 } },
        { 'file': 'DAPI.tif', 'layer_type': "image",
          'add_kwargs': { 'name': "DAPI", 'colormap': 'blue', 'visible': True, 'blending': 'additive' } },
        { 'file': _prefer('corrected/DAPI_corrected_masks.tif', 'DAPI_masks.tif'), 'layer_type': 'labels',
          'add_kwargs': { 'name': "DAPI masks", 'visible': False, 'blending': 'additive', 'opacity': 0.2 } },
    ]

    layer_tuples = []

    with open(path, "r") as f:
        img = json.load(f)
        # a real fluorescence channel has a 'colormap' in its results entry;
        # skip non-channel keys such as 'alignment' that align() adds to results.
        channel_keys = [k for k, v in img['results'].items()
                        if isinstance(v, dict) and 'colormap' in v]
        colors = { k: img['results'][k].get('colormap', 'gray') for k in channel_keys }

        for ch in channel_keys:
            metadata = { 'channel': ch, **img['parameters'] }
            threshold = img['results'][ch].get('threshold', 0)
            metadata.update({'threshold': threshold})

            layer_list.extend([
                { 'file': f'{ch}.tif', 'layer_type': "image",
                  'add_kwargs': { 'name': f'{ch}', 'metadata': metadata,
                                  'colormap': colors.get(ch, 'gray'), 'visible': False } },
                { 'file': f'{ch}_filtered.tif', 'layer_type': "image",
                  'add_kwargs': { 'name': f'{ch} background filtered', 'metadata': metadata,
                                  'colormap': colors.get(ch, 'gray'), 'visible': True } },
                { 'file': f'{ch}_spots.npy', 'layer_type': "points",
                  'add_kwargs': { 'name': f'{ch} spots detected thr={threshold}', 'metadata': metadata,
                                  'symbol': 'disc', 'size': 10, 'opacity': 0.5, 'face_color': 'transparent',
                                  'border_color': 'label' } },
                { 'file': f'{ch}_decomposed_spots.npy', 'layer_type': "points",
                  'add_kwargs': { 'name': f'{ch} decomposed spots', 'metadata': metadata,
                                  'symbol': 'disc', 'size': 10, 'opacity': 0.5, 'face_color': 'transparent',
                                  'border_color': colors.get(ch, 'gray') } }
            ])

    for l in layer_list:
        file = Path(path).parent / l['file']
        if not file.exists():
            continue

        if file.suffix == '.tif':
            data = io.imread(file)
        elif file.suffix == '.npy':
            data = np.load(file)
            if l['layer_type'] == "points" and "spots" in l['file']:

                # Old code 
                #    features = pd.DataFrame(data, columns=['z', 'y', 'x', 'intensity', 'filtered_intensity', 'label'])
                #    data = data[:, :3]
                #    l['add_kwargs']['features'] = features

                # Define column names
                n_cols = data.shape[-1]

                if n_cols == 3:
                    columns = ['z', 'y', 'x']
                elif n_cols == 5:
                    # format written by Image.detect_spots_channel
                    columns = ['z', 'y', 'x', 'intensity', 'filtered_intensity']
                elif n_cols == 6:
                    columns = ['z', 'y', 'x', 'intensity', 'filtered_intensity', 'label']
                else:
                    raise ValueError(f"Unexpected number of columns in data: {n_cols}")

                features = pd.DataFrame(data, columns=columns)
                data = data[:, :3]

                # colour spots by the cell they fall in: add a 'label' feature
                # (the DIC-mask label at each spot's y,x). Falls back to a solid
                # border colour if no cell mask is available.
                if 'label' not in features.columns and cell_mask is not None:
                    ys = data[:, 1].astype(int)
                    xs = data[:, 2].astype(int)
                    h, w = cell_mask.shape
                    inb = (ys >= 0) & (ys < h) & (xs >= 0) & (xs < w)
                    lab = np.zeros(len(data), dtype=int)
                    lab[inb] = cell_mask[ys[inb], xs[inb]]
                    features['label'] = lab

                if l['add_kwargs'].get('border_color') == 'label' and 'label' not in features.columns:
                    l['add_kwargs']['border_color'] = 'red'

                l['add_kwargs']['features'] = features
        else:
            continue

        layer_tuples.append((data, l['add_kwargs'], l['layer_type']))

    return layer_tuples
