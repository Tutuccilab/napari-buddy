# Changelog

## 0.3.1 (2026-10-20)
- The layer dropdowns of the tabbed panels (e.g. *img_layer* in Spot tuning → Filter) follow the layer list again:
  new, removed, reordered and renamed layers show up without reopening the dock. napari refreshes the dropdowns of
  the widget it docks, which since 0.3.0 is the tab container and not the panels inside it; napari-buddy now
  connects the panels itself (`_tabs._sync_layer_choices`, with a test).
- `cell cycle` layer: the phase labels are larger (12 instead of 9) and keep their size on screen when zooming
  (napari >= 0.6; on older versions they scale with the zoom as before).

## 0.3.0 (2026-10-18)
- **Three tabbed panels** in Plugins → Napari Buddy instead of ten entries: **buddy pipeline** (Pipeline, Config),
  **Spot tuning** (Read image, Filter, Detect, Threshold, Decompose) and **Correct images** (Images, Buds, Layers). Each
  tab is the unchanged panel of before.
- Buds tab: a line from a bud that is already linked to a mother (it shares that cell's label, e.g. a red *close call*
  of the bud model) to another cell moves the bud: its painted pixels are cut out of the old mother's label and merged
  into the new one. Repainting the bud with a new label first is no longer needed. The status line reports
  *moved N bud(s) to another mother*; the old *the paint covers less than half of cell N* refusal is gone.
- Tests for the lines of the Buds tab on synthetic masks (`_tests/test_bud_lines.py`).
- Pipeline panel: the bud model is loaded in the GUI thread before a step starts (and before Omnipose in Run 1-3), and
  the Omnipose networks are released after step 2. Loading the bud model next to Omnipose from a worker thread hung
  now and then on Windows.
- File → Open Sample: the two entries removed (leftovers of the plugin template; one returned a random image, the other
  downloaded a zip from Zenodo and returned nothing). The example data are the "test yourself" set on Zenodo.
- Works with buddy up to 0.4.x.

## 0.2.0 (2026-10-12)
- New **cell cycle** layer (from buddy 0.3.0's `cell_cycle.csv`): the phase (S, G2 or M) written on each budded cell;
  hover a label for the reason buddy gave. G1 and unbudded cells get no label. Shown / hidden with the new
  *Cell-cycle phases* box in Layer groups.
- The fluorescence channels (raw and filtered) open with contrast limits set from the image itself: the background
  noise dark (low limit = a high percentile of the image), the detected spots bright (high limit = the brightness
  of the spots). The slider still covers the full range.
- Works with buddy 0.1.0 up to 0.3.x (the warning for newer buddy versions now starts at 0.4).
- Tests: the widget tests use a viewer without a window (`ViewerModel`), so they also run on the Windows runners
  without OpenGL.

## Tests only, no code change (after 0.1.1)
- Tests rewritten on buddy's test field (reader; spot-tuning panels give the same result as buddy's pipeline);
  GitHub workflow on Linux and Windows. Removed the template leftovers (`test_writer.py`, `tox.ini`).

## 0.1.1 (2026-10-11)
- Works with buddy 0.2.0 (its modules moved into sub-packages: `buddy.spots.gpu`, `buddy.buds.bud_tools`) as well as 0.1.0.
- Warns at import when the installed buddy is older than 0.1.0 or newer than 0.2.x.

## 0.1.0 (2026-10-09)
- New **buddy pipeline** panel: steps 1-5 of the buddy bulk-processing notebook with buttons (background
  run, progress bar, time estimate, "Stop after this image", yes/no question before overwriting).
- Reader: layers are added in groups (DIC + DAPI, raw channels, filtered channels, spots, masks) and tagged
  with their group; loads the bud model's results (`bud masks`, `check these buds`) when present.
- `check these buds` also shows buddy's `cell_flags.csv` (magenta *late-M pair?*, green *high ASH1/CLB2, no bud*).
- New `bud → mother links` layer: a red line from each bud to its mother (white circle = bud without mother);
  replaces the magenta "mother-bud pairs" boxes. Updated by the Reassign-buds widget (**Apply links**; saving also applies drawn lines).
- New `review_images(exp)`: a **Correct images** panel to go through all images (previous / save /
  save + next / skip); `open_for_correction` / `save_corrections` for one image at a time.
- Opening an image as projections loads the saved 2D projections (`projections/`, made on first open if
  missing) instead of the full z-stacks: much faster.
- **Create config file** also writes the new settings: `min_cell_area`, `expand_px`, `remove_edge_cells`,
  `use_gpu`, `gpu_spot_detection`, the `bud_classification` block and `if_already_processed`.
- The spot-tuning panels (Filter out background, Detect spot, Decompose spots) use the GPU when available
  (same result as Big-FISH; Big-FISH on the CPU otherwise).
- New **Layer groups** widget: show / hide groups of layers by type or by channel.
- Default visibility: DIC, DAPI, filtered channels, spots and masks shown; raw channels and nucleus masks hidden.
- Fix: moving to the next image failed with an `IndexError` when a hidden spot layer had fewer spots in the
  new image (napari does not re-slice hidden layers); the failure also skipped the read-ahead of the next
  image, which made every following image slow to open. A layer that cannot be updated in place is now recreated.
- Pipeline panel: the status line shows what buddy is doing right now (image name + step, e.g. *background filter*,
  *bud model*); the progress bar also moves *within* an image (from the time estimate); an image that runs out
  of RAM says so, and the memory of each image is released before the next one.
- **Correct images** in the Plugins menu: choose the config file and go through the images (the panel the
  pipeline's step 4 and `review_images(exp)` open).
- Pipeline panel: **Run 1-3** runs read, segment and spots + buds + counts one after the other (each with its
  own re-run check); starting a step closes the layers in napari to free RAM for the processing.

## 0.0.4
Version used for the manuscript.
