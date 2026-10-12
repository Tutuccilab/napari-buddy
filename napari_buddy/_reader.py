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

# Layer groups (see _layer_groups.py). The reader adds the layers group by group, from the bottom
# of napari's layer list to the top, so the layers of a group sit together.
GROUP_ORDER = ["images", "raw", "filtered", "spots", "masks", "cellcycle"]
FLAG_COLOURS = {"close call": "red", "bud without mother": "orange",
                "weak pair": "yellow", "possible missed bud": "yellow",
                # cell_flags.csv (buddy/cell_flags.py): unbudded cells with high ASH1/CLB2
                "late-M pair?": "magenta", "high ASH1/CLB2, no bud": "lime"}


def bud_layer_data(base, cell_mask=None):
    """
    Layer data tuples for the bud results in an image folder (all in the 'masks' group):
      bud masks           corrected/bud_corrected_masks.tif (1 = bud, 2 = background, 3 = mother)
      bud -> mother links a line from each bud to its mother (see _bud_links.py)
      check these buds    boxes around the cells the bud model was unsure about (bud_flags.csv) and the
                          unbudded cells with high ASH1/CLB2 (cell_flags.csv: late M / early S)
    Missing files are skipped.
    """
    from ._bud_links import links_layer_data
    base = Path(base)
    tuples = []
    bud_file = base / 'corrected' / 'bud_corrected_masks.tif'
    if bud_file.exists():
        bud_masks = io.imread(bud_file)
        tuples.append((bud_masks, {'name': 'bud masks', 'opacity': 0.5, 'visible': True,
                                   'metadata': {'group': 'masks'}}, 'labels'))
        if cell_mask is not None:
            tuples.append(links_layer_data(cell_mask, bud_masks))
    tables = [pd.read_csv(f) for f in (base / 'bud_flags.csv', base / 'cell_flags.csv') if f.exists()]
    tables = [t for t in tables if len(t)]
    if tables:
        flags = pd.concat(tables, ignore_index=True)
        if len(flags):
            # square markers (a points layer, not shapes: napari shows a points layer's features when the
            # mouse is over a marker, so the flag and reason appear only on hover)
            centres = np.c_[(flags['y0'] + flags['y1']) / 2, (flags['x0'] + flags['x1']) / 2]
            sizes = np.maximum(flags['y1'] - flags['y0'], flags['x1'] - flags['x0']) + 10
            tuples.append((centres, {
                'name': 'check these buds', 'symbol': 'square', 'size': sizes.to_numpy(),
                'face_color': 'transparent', 'border_width': 4, 'border_width_is_relative': False,
                'border_color': [FLAG_COLOURS.get(f, 'white') for f in flags['flag']],
                'features': flags[['flag', 'reason', 'label']].reset_index(drop=True),
                'metadata': {'group': 'masks'}}, 'points'))
    return tuples


# cell-cycle phases (buddy >= 0.3.0, cell_cycle.csv): only budded phases are coloured; G1 / unbudded cells are not
PHASE_COLOURS = {"S": "#55A868", "G2": "#C44E52", "M": "#8172B3"}


def cell_cycle_layer_data(base, cell_mask):
    """
    Layer data tuples for buddy's cell-cycle phases (cell_cycle.csv, written by buddy >= 0.3.0), in the 'cellcycle'
    group:
      cell cycle          the cells in S, G2 and M filled with the colour of their phase (G1 / unbudded / NA: not shown)
      cell cycle (text)   the phase written on each of those cells; hover for the reason buddy gave
    Nothing is returned when the file or the cell mask is missing, or no cell is in S, G2 or M.
    """
    from scipy import ndimage as ndi
    table_file = Path(base) / 'cell_cycle.csv'
    if cell_mask is None or not table_file.exists():
        return []
    table = pd.read_csv(table_file)
    shown = table[table['cell_cycle_phase'].isin(list(PHASE_COLOURS))]
    if not len(shown):
        return []
    codes = {p: i for i, p in enumerate(PHASE_COLOURS, start=1)}            # S = 1, G2 = 2, M = 3
    lut = np.zeros(int(max(cell_mask.max(), table['image_cell_id'].max())) + 1, np.uint8)
    lut[shown['image_cell_id'].to_numpy(int)] = [codes[p] for p in shown['cell_cycle_phase']]
    phase_map = lut[cell_mask]
    try:
        from napari.utils.colormaps import DirectLabelColormap
        colormap = DirectLabelColormap(color_dict={None: 'transparent', 0: 'transparent',
                                                   **{codes[p]: c for p, c in PHASE_COLOURS.items()}})
        colour_kwargs = {'colormap': colormap}
    except ImportError:                    # older napari
        colour_kwargs = {'color': {0: 'transparent', **{codes[p]: c for p, c in PHASE_COLOURS.items()}}}
    tuples = [(phase_map, {'name': 'cell cycle', 'opacity': 0.45, 'visible': True, **colour_kwargs,
                           'metadata': {'group': 'cellcycle'}}, 'labels')]
    labels = shown['image_cell_id'].to_numpy(int)
    centres = np.array(ndi.center_of_mass(np.ones_like(cell_mask), cell_mask, labels)).reshape(-1, 2)
    keep = np.isfinite(centres).all(axis=1)                                   # cells missing from the mask
    features = shown[['cell_cycle_phase', 'why', 'image_cell_id']].reset_index(drop=True)[keep].reset_index(drop=True)
    tuples.append((centres[keep], {
        'name': 'cell cycle (text)', 'size': 1, 'face_color': 'transparent', 'border_width': 0,
        'features': features,
        'text': {'string': '{cell_cycle_phase}', 'color': 'white', 'size': 9, 'anchor': 'center'},
        'metadata': {'group': 'cellcycle'}}, 'points'))
    return tuples


def max_projection(stack_file):
    """
    2D maximum projection of a z-stack file, from projections/<name>_max.tif (written by buddy, or made
    here the first time and saved for next time). Remade when the stack is newer than the saved projection.
    Reading these small files instead of the full stacks makes opening an image much faster.
    """
    stack_file = Path(stack_file)
    cache = stack_file.parent / 'projections' / f'{stack_file.stem}_max.tif'
    if cache.exists() and cache.stat().st_mtime >= stack_file.stat().st_mtime:
        return io.imread(cache)
    data = io.imread(stack_file)
    if data.ndim != 3:
        return data
    projection = data.max(axis=0)
    try:
        cache.parent.mkdir(exist_ok=True)
        io.imsave(cache, projection, check_contrast=False)
    except OSError:                       # read-only folder: just do not save it
        pass
    return projection


def read_smfish_json(path, max_project=False):
    """
    All layers of one image (from its img.json), grouped and ordered (bottom to top):
      images    DIC, DAPI                                   (visible)
      raw       {channel}                                   (hidden)
      filtered  {channel} background filtered               (visible)
      spots     detected + decomposed spots per channel     (visible)
      masks     DIC masks (visible), DAPI masks (hidden), bud masks, bud -> mother links, check these buds
      cellcycle cell cycle (cells in S, G2, M coloured by phase) + cell cycle (text)   (buddy >= 0.3.0)
    Every layer gets metadata['group'] (and metadata['channel'] for channel layers), used by the
    Layer groups widget to show / hide whole groups.
    max_project=True: z-stacks are loaded as 2D maximum projections (from projections/, see max_projection).
    """
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
        { 'file': _prefer('aligned_DIC.tif', 'DIC.tif'), 'layer_type': "image", 'group': 'images',
          'add_kwargs': { 'name': "DIC", 'colormap': 'grey', 'visible': True, 'blending': 'additive' } },
        { 'file': 'DAPI.tif', 'layer_type': "image", 'group': 'images',
          'add_kwargs': { 'name': "DAPI", 'colormap': 'blue', 'visible': True, 'blending': 'additive' } },
        { 'file': dic_mask_file, 'layer_type': 'labels', 'group': 'masks',
          'add_kwargs': { 'name': "DIC masks", 'visible': True, 'blending': 'additive', 'opacity': 0.2 } },
        { 'file': _prefer('corrected/DAPI_corrected_masks.tif', 'DAPI_masks.tif'), 'layer_type': 'labels', 'group': 'masks',
          'add_kwargs': { 'name': "DAPI masks", 'visible': False, 'blending': 'additive', 'opacity': 0.2 } },
    ]

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
                { 'file': f'{ch}.tif', 'layer_type': "image", 'group': 'raw',
                  'add_kwargs': { 'name': f'{ch}', 'metadata': metadata,
                                  'colormap': colors.get(ch, 'gray'), 'visible': False } },
                { 'file': f'{ch}_filtered.tif', 'layer_type': "image", 'group': 'filtered',
                  'add_kwargs': { 'name': f'{ch} background filtered', 'metadata': metadata,
                                  'colormap': colors.get(ch, 'gray'), 'visible': True } },
                { 'file': f'{ch}_spots.npy', 'layer_type': "points", 'group': 'spots',
                  'add_kwargs': { 'name': f'{ch} spots detected thr={threshold}', 'metadata': metadata,
                                  'symbol': 'disc', 'size': 10, 'opacity': 0.5, 'face_color': 'transparent',
                                  'border_color': 'label' } },
                { 'file': f'{ch}_decomposed_spots.npy', 'layer_type': "points", 'group': 'spots',
                  'add_kwargs': { 'name': f'{ch} decomposed spots', 'metadata': metadata,
                                  'symbol': 'disc', 'size': 10, 'opacity': 0.5, 'face_color': 'transparent',
                                  'border_color': colors.get(ch, 'gray') } }
            ])

    tuples_by_group = {g: [] for g in GROUP_ORDER}
    for l in layer_list:
        file = Path(path).parent / l['file']
        if not file.exists():
            continue

        if file.suffix == '.tif':
            if l['file'] == dic_mask_file and cell_mask is not None:
                data = cell_mask                          # already read above (for the spot colours)
            elif max_project and l['layer_type'] == 'image':
                data = max_projection(file)
            else:
                data = io.imread(file)
        elif file.suffix == '.npy':
            data = np.load(file)
            if l['layer_type'] == "points" and "spots" in l['file']:
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

        kwargs = dict(l['add_kwargs'])
        kwargs['metadata'] = {**kwargs.get('metadata', {}), 'group': l['group']}   # own copy per layer
        tuples_by_group[l['group']].append((data, kwargs, l['layer_type']))

    tuples_by_group['masks'].extend(bud_layer_data(_base, cell_mask))
    tuples_by_group['cellcycle'].extend(cell_cycle_layer_data(_base, cell_mask))
    return [t for g in GROUP_ORDER for t in tuples_by_group[g]]
