"""
Check and correct images in napari (step 4 of the buddy bulk-processing notebooks).

    review_images(exp)                               # opens the first image with a 'Correct images' panel:
                                                     # previous / save / save + next / skip buttons
or one image at a time from the notebook:
    my_image, viewer = open_for_correction(exp, i)   # opens image i, ready to correct
    ... correct in napari ...
    save_corrections(viewer, my_image)               # links new buds to mothers, saves the corrected masks

open_for_correction
    Loads all layers of the image (grouped: DIC + DAPI, raw channels, filtered channels, spots, masks),
    opens the Layer groups and Reassign buds to mothers panels, and prepares the 'bud masks' layer for
    painting (1 = bud, 2 = background, 3 = mother):
      * after automatic bud classification: the model's bud masks, the bud -> mother links and the
        'check these buds' boxes (hover a box for the reason)
      * otherwise: small cells pre-marked as buds (yellow boxes), non-round cells circled (cyan)

save_corrections
    Links every newly painted bud to the cell it touches most (its mother) and merges it into that cell,
    redraws the bud -> mother links, and saves corrected/DIC_corrected_masks.tif, DAPI_corrected_masks.tif
    and bud_corrected_masks.tif (what buddy's assign_spots reads).
"""
from pathlib import Path

import numpy as np

BUD = 1
_DOCKED = {}    # (id(viewer), panel name) -> dock widget, so each panel is added to a viewer only once
_PANELS = {}    # id(viewer) -> the Correct images panel
_PREFETCH = {}  # img.json path -> (file times, future with the prepared layers), see _prefetch
_LOADER = None  # one background thread that reads the next image while you correct the current one


def _dock_once(viewer, name, make_widget, replace=False):
    """Add a panel to the napari window once (works with every napari version); replace=True swaps it."""
    window = getattr(viewer, 'window', None)
    if window is None:
        return
    key = (id(viewer), name)
    old = _DOCKED.get(key)
    if old is not None:
        try:
            alive = old.isVisible() or old.parent() is not None
        except RuntimeError:                      # the dock was closed and deleted
            alive = False
        if alive and not replace:
            return
        if alive:
            try:
                window.remove_dock_widget(old)
            except Exception:
                pass
    _DOCKED[key] = window.add_dock_widget(make_widget(), name=name, area='right')


def _show_tooltips():
    """Turn on napari's layer tooltips: hovering a 'check these buds' box shows its flag and reason."""
    try:
        from napari.settings import get_settings
        get_settings().appearance.layer_tooltip_visibility = True
    except Exception:                        # older napari without this setting: the status bar still shows it
        pass


def _prepare_layer(layer_data, max_project):
    """Max-project z-stacks to 2D (and flatten spots to y, x) so all layers overlay the DIC image."""
    data, kwargs, ltype = layer_data
    kwargs = dict(kwargs)
    if ltype == 'points':
        feats = kwargs.get('features')        # 'label' only exists after spot assignment
        if kwargs.get('border_color') == 'label' and (feats is None or 'label' not in getattr(feats, 'columns', [])):
            kwargs['border_color'] = 'red'
        if max_project and data.shape[1] == 3:
            data = data[:, 1:]
    elif ltype == 'image' and max_project:
        if data.ndim == 3:
            data = data.max(axis=0)
        kwargs['blending'] = 'additive'
        lo, hi = float(data.min()), float(data.max())
        if hi > lo:
            kwargs['contrast_limits'] = [lo, hi]
    return data, kwargs, ltype


def _replace_layers(viewer, new_layers, clear=True):
    """
    Show the layers of the next image. Layers that already exist with the same name get the new data in
    place: deleting and re-creating layers is what makes napari slow (it rebuilds display objects and runs
    a memory clean-up for every deleted layer), and updated layers keep the visibility you chose. Layers of
    the previous image that the new image does not have are removed. clear=False: keep the old layers, add
    the new ones.
    """
    if not clear:
        for t in new_layers:
            viewer._add_layer_from_data(*t)
        return
    wanted = {kw['name'] for _, kw, _ in new_layers}
    for layer in list(viewer.layers):                   # drop layers the new image does not have
        if layer.name not in wanted:
            viewer.layers.remove(layer)
    for position, (data, kw, ltype) in enumerate(new_layers):
        name = kw['name']
        old = viewer.layers[name] if name in viewer.layers else None
        same_type = old is not None and type(old).__name__.lower() == ltype
        layer = None
        try:
            if same_type and ltype == 'points' and np.shape(old.data)[1:] == np.shape(data)[1:]:
                _update_points(old, data, kw)
                layer = old
            elif same_type and ltype == 'shapes':
                _update_shapes(old, data, kw)
                layer = old
            elif same_type and ltype in ('image', 'labels') and np.shape(old.data) == np.shape(data):
                if ltype == 'image' and 'contrast_limits' in kw:
                    old.contrast_limits_range = kw['contrast_limits']
                old.data = data
                if ltype == 'image' and 'contrast_limits' in kw:
                    old.contrast_limits = kw['contrast_limits']
                old.metadata = kw.get('metadata', {})
                layer = old
        except Exception as e:                          # an in-place update that napari refuses: recreate the layer
            print(f"could not update layer '{name}' in place ({type(e).__name__}: {e}); recreating it")
            layer = None
        if layer is None:
            if old is not None:
                viewer.layers.remove(old)
            layer = viewer._add_layer_from_data(data, kw, ltype)
            layer = layer[0] if isinstance(layer, list) else layer
        index = viewer.layers.index(layer)
        if index != position:                           # keep the group order of the reader
            viewer.layers.move(index, position)


def _update_points(layer, data, kw):
    """New spots (or flag markers) for an existing points layer, with their features, colours and sizes."""
    features = kw.get('features')
    layer.data = data
    if not layer.visible:
        # napari re-slices a layer only when it is visible; the stale slice of a hidden layer would be applied to
        # the new data when symbol / size are set below (IndexError when the new image has fewer points)
        try:
            layer.refresh(force=True)
        except TypeError:                                # napari < 0.5: refresh() has no force argument
            layer._set_view_slice()
    if features is not None:
        layer.features = features
    for key in ('size', 'symbol', 'face_color', 'border_width', 'border_width_is_relative', 'opacity'):
        if key in kw:
            setattr(layer, key, kw[key])
    if 'border_color' in kw and len(data):
        layer.border_color = kw['border_color']          # 'label' -> coloured by the cell each spot is in
    layer.metadata = kw.get('metadata', {})


def _update_shapes(layer, data, kw):
    """New shapes (the bud -> mother links) for an existing shapes layer."""
    layer.data = []
    if len(data):
        layer.add(data, shape_type=kw.get('shape_type', 'line'), edge_color=kw.get('edge_color', 'red'),
                  face_color=kw.get('face_color', 'transparent'), edge_width=kw.get('edge_width', 2))
        if kw.get('features') is not None:
            layer.features = kw['features']
    layer.metadata = kw.get('metadata', {})


def _seed_bud_layer(viewer, savepath):
    """No bud model output: pre-mark small cells as buds and circle non-round cells (as before)."""
    from skimage import io
    from buddy.bud_tools import classify_cells, build_bud_seed, candidate_rectangles
    cell_masks = np.asarray(viewer.layers['DIC masks'].data)
    info = classify_cells(cell_masks, bud_area_fraction=0.5, min_solidity=0.93, max_round_eccentricity=0.85)
    bud_file = savepath / 'corrected' / 'bud_corrected_masks.tif'
    earlier = io.imread(bud_file) if bud_file.is_file() else None          # keep buds annotated earlier
    if 'bud masks' in viewer.layers:
        viewer.layers.remove(viewer.layers['bud masks'])
    group = {'group': 'masks'}
    viewer.add_labels(build_bud_seed(cell_masks, info['bud_labels'], keep_bud_mask=earlier),
                      name='bud masks', opacity=0.5, metadata=group)
    for labels, name, shape, colour in ((info['bud_labels'], 'potential buds', 'rectangle', 'yellow'),
                                        (info['budded_labels'], 'potentially budded', 'ellipse', 'cyan')):
        rects = candidate_rectangles(info['props'], labels)
        if rects:
            viewer.add_shapes(rects, name=name, shape_type=shape, edge_color=colour, edge_width=6,
                              face_color='transparent', metadata=group)
    return (f"NO BUD MODEL OUTPUT (step 3 has not run for this image): {len(info['bud_labels'])} small cell(s) pre-marked as bud by the old size rule (yellow, not a prediction), "
            f"{len(info['budded_labels'])} non-round cell(s) circled (cyan)")


def open_for_correction(exp, i, max_project=True, clear=True):
    """
    Open image number i of the experiment in napari, ready to correct.
    max_project: show z-stacks as maximum projections (False = full stacks).
    clear: remove the layers of the previously opened image first.
    Returns (my_image, viewer).
    """
    my_image, viewer, summary, timing = _open(exp, i, max_project, clear)
    print(f"image {i + 1}/{len(exp.images)}: {my_image.stem}\n  {summary}\n  {timing}\n"
          f"  paint 1 = bud, 3 = mother (or Plugins > napari-buddy > Reassign buds to mothers), then save")
    return my_image, viewer


def _json_path(exp, i):
    from buddy.rerun_check import _json_of
    return _json_of(exp, list(exp.images.values())[i], 'read')


def _file_times(json_path):
    """Modification times of the files a reopen depends on (to notice changes since prefetching)."""
    folder = Path(json_path).parent
    files = [Path(json_path), *sorted((folder / 'corrected').glob('*.tif')), folder / 'bud_flags.csv',
             folder / 'cell_flags.csv']
    return tuple(f.stat().st_mtime if f.exists() else 0 for f in files)


def _load_layers(json_path, max_project):
    """Read an image's files and prepare its layers (no napari involved: can run in the background)."""
    from ._reader import read_smfish_json
    return [_prepare_layer(t, max_project) for t in read_smfish_json(str(json_path), max_project=max_project)]


def _prefetch(exp, i, max_project):
    """Start reading image i in the background, so opening it later only has to update napari."""
    global _LOADER
    if not 0 <= i < len(exp.images):
        return
    path = _json_path(exp, i)
    if not path.is_file() or str(path) in _PREFETCH:
        return
    if _LOADER is None:
        from concurrent.futures import ThreadPoolExecutor
        _LOADER = ThreadPoolExecutor(max_workers=1)
    _PREFETCH[str(path)] = (_file_times(path), max_project, _LOADER.submit(_load_layers, path, max_project))


def _take_prefetched(path, max_project):
    """The prepared layers of an image if they were read in the background and its files did not change since."""
    entry = _PREFETCH.pop(str(path), None)
    if entry is None:
        return None
    times, mp, future = entry
    if mp != max_project or times != _file_times(path):
        return None
    try:
        return future.result()
    except Exception:
        return None


def _open(exp, i, max_project=True, clear=True):
    """open_for_correction without printing; returns (my_image, viewer, summary, timing)."""
    import time
    import napari
    import pandas as pd
    from buddy.image import Image
    from ._reader import read_smfish_json
    from ._layer_groups import layer_groups_widget
    from ._bud_links import update_links

    images = list(exp.images.values())
    my_image = Image.from_dict(images[i], exp)
    savepath = Path(my_image.savepath)

    viewer = napari.current_viewer() or napari.Viewer()
    _show_tooltips()
    t0 = time.time()
    new_layers = _take_prefetched(savepath / 'img.json', max_project)
    preloaded = new_layers is not None
    if new_layers is None:
        new_layers = _load_layers(savepath / 'img.json', max_project)
    t1 = time.time()
    _replace_layers(viewer, new_layers, clear)
    t2 = time.time()
    _dock_once(viewer, 'Layer groups', layer_groups_widget)
    from ._bud_widget import reassign_buds_widget
    _dock_once(viewer, 'Reassign buds to mothers', reassign_buds_widget)

    flags_file = savepath / 'bud_flags.csv'
    if 'bud masks' in viewer.layers and flags_file.is_file():
        flags = pd.read_csv(flags_file)
        counts = ', '.join(f'{n} {f}' for f, n in flags['flag'].value_counts().items()) if len(flags) else 'none'
        summary = f"bud model result loaded; cells to check: {counts}"
    else:
        summary = _seed_bud_layer(viewer, savepath)
        update_links(viewer)
    cell_flags_file = savepath / 'cell_flags.csv'
    if cell_flags_file.is_file():
        cell_flags = pd.read_csv(cell_flags_file)
        if len(cell_flags):
            summary += '; high ASH1/CLB2: ' + ', '.join(f'{n} {f}' for f, n in cell_flags['flag'].value_counts().items())

    bud_layer = viewer.layers['bud masks']
    bud_layer.selected_label = BUD
    bud_layer.mode = 'paint'
    viewer.layers.selection.active = bud_layer
    t3 = time.time()
    timing = (f"opened in {t3 - t0:.1f} s (files {t1 - t0:.1f} s{' - read in advance' if preloaded else ''}, "
              f"napari {t2 - t1:.1f} s, other {t3 - t2:.1f} s)")
    return my_image, viewer, summary, timing


def save_corrections(viewer, my_image):
    """Link newly painted buds to their mothers, redraw the links and save the corrected masks."""
    print(_save(viewer, my_image))


def _save(viewer, my_image):
    """save_corrections without printing; returns the summary."""
    from skimage import io
    from buddy.bud_tools import assign_buds_to_mothers, merge_buds_into_mothers
    from ._bud_links import update_links
    from ._bud_widget import apply_drawn_lines, LINKS_LAYER

    applied = ''
    if LINKS_LAYER in viewer.layers and len(viewer.layers[LINKS_LAYER].data):   # lines drawn but not applied
        applied = '\n  drawn lines applied: ' + apply_drawn_lines(viewer).split('. ')[0]

    dic = np.asarray(viewer.layers['DIC masks'].data)
    buds = np.asarray(viewer.layers['bud masks'].data)
    _, assignments, unassigned, bud_cc = assign_buds_to_mothers(dic, buds)
    merged = merge_buds_into_mothers(dic, assignments, bud_cc)
    viewer.layers['DIC masks'].data = merged
    for name in ('mother-bud pairs', 'unassigned buds'):          # old box layers, replaced by the links
        if name in viewer.layers:
            viewer.layers.remove(viewer.layers[name])
    pairs, orphans = update_links(viewer)

    corrected = Path(my_image.savepath) / 'corrected'
    corrected.mkdir(parents=True, exist_ok=True)
    io.imsave(corrected / 'DIC_corrected_masks.tif', np.asarray(merged), check_contrast=False)
    io.imsave(corrected / 'bud_corrected_masks.tif', np.asarray(viewer.layers['bud masks'].data), check_contrast=False)
    if 'DAPI masks' in viewer.layers:
        io.imsave(corrected / 'DAPI_corrected_masks.tif', np.asarray(viewer.layers['DAPI masks'].data),
                  check_contrast=False)

    newly = sum(1 for mother, own in assignments.values() if mother is not None and mother != own)
    return (f"saved corrected masks for {my_image.stem}\n"
            f"  {pairs} bud(s) linked to a mother ({newly} newly linked), {orphans} without mother"
            + (" - see the white circles" if orphans else "") + applied)


def review_images(exp, start=0, max_project=True):
    """
    Open image number `start` in napari with a 'Correct images' panel to go through all images
    without going back to the notebook:
        previous       open the previous image (without saving)
        save           link newly painted buds to their mothers and save the corrected masks
        save + next    save, then open the next image
        skip           open the next image without saving
    Returns nothing (so Jupyter does not show a picture of the panel under the cell).
    """
    from magicgui.widgets import Container, PushButton, Label

    n = len(exp.images)
    state = {}
    title, status = Label(), Label()
    previous_btn, save_btn = PushButton(text="\u25c0 previous"), PushButton(text="save")
    next_btn, skip_btn = PushButton(text="save + next \u25b6"), PushButton(text="skip \u25b6")

    def show(i):
        state['i'] = i
        state['image'], state['viewer'], summary, timing = _open(exp, i, max_project)
        title.value = f"image {i + 1}/{n}: {state['image'].stem}"
        status.value = summary
        previous_btn.enabled = i > 0
        next_btn.enabled = skip_btn.enabled = i < n - 1
        print(f"{title.value}\n  {summary}\n  {timing}")
        _prefetch(exp, i + 1, max_project)               # read the next image while you work on this one

    def save(*_):
        import time
        tic = time.time()
        message = _save(state['viewer'], state['image']) + f"\n  saved in {time.time() - tic:.1f} s"
        status.value = message.replace("\n  ", " - ")
        print(message)

    def save_and_next(*_):
        save()
        if state['i'] < n - 1:
            show(state['i'] + 1)
        else:
            status.value += " - that was the last image"

    previous_btn.clicked.connect(lambda *_: show(state['i'] - 1))
    save_btn.clicked.connect(save)
    next_btn.clicked.connect(save_and_next)
    skip_btn.clicked.connect(lambda *_: show(state['i'] + 1))

    show(start)
    panel = Container(widgets=[title, Container(widgets=[previous_btn, save_btn, next_btn, skip_btn],
                                                layout="horizontal", labels=False), status], labels=False)
    _dock_once(state['viewer'], 'Correct images', lambda: panel, replace=True)   # running the cell again replaces it
    _PANELS[id(state["viewer"])] = panel                 # keep a reference (for tests / scripting)


def correct_images_widget():
    """
    Plugins menu -> "Correct images": choose the config file (input / output folders are filled in from it, and
    can be changed), then "Open images" shows the first image with the previous / save / save + next / skip panel.
    From a notebook, review_images(exp) does the same.
    """
    import json
    from magicgui.widgets import Container, FileEdit, Label, PushButton

    cfg_file = FileEdit(label="config file", mode="r", filter="*.json")
    inputdir = FileEdit(label="input folder", mode="d")
    outputdir = FileEdit(label="output folder", mode="d")
    open_btn = PushButton(text="Open images")
    status = Label(value="Choose a config file.")

    def config_chosen(*_):
        path = Path(str(cfg_file.value))
        if not path.is_file():
            return
        try:
            cfg = json.load(open(path))
        except (OSError, ValueError) as e:
            status.value = f"Cannot read {path.name}: {e}"
            return
        if cfg.get("inputdir"):
            inputdir.value = cfg["inputdir"]
        if cfg.get("outputdir"):
            outputdir.value = cfg["outputdir"]
        status.value = f"{path.name} loaded - check the folders, then Open images"

    def open_images(*_):
        from buddy.experiment import Experiment
        path = Path(str(cfg_file.value))
        if not path.is_file():
            status.value = "Choose a config file first."
            return
        exp = Experiment.from_cfg_file(str(path))
        if str(inputdir.value) not in ("", "."):
            exp.inputdir = str(inputdir.value)
        if str(outputdir.value) not in ("", "."):
            exp.outputdir = str(outputdir.value)
        exp.create_image_list()
        if not exp.images:
            status.value = f"No images found in {exp.inputdir}"
            return
        from buddy.rerun_check import _json_of
        n_done = sum(_json_of(exp, item, "read").is_file() for item in exp.images.values())
        status.value = f"{len(exp.images)} image(s), {n_done} processed - see the Correct images panel"
        review_images(exp, start=0)

    cfg_file.changed.connect(config_chosen)
    open_btn.clicked.connect(open_images)
    return Container(widgets=[cfg_file, inputdir, outputdir, open_btn, status])
