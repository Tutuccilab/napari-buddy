"""
napari widget: show / hide whole groups of layers at once.

napari has no layer groups (yet), so this widget groups layers itself:
  by type     Images (DIC, DAPI) | Raw channels | Filtered channels | Spots | Masks (cell, nucleus, bud masks,
              bud -> mother links, check these buds)
  by channel  every layer of one fluorescence channel (raw, filtered, spots)

A layer's group comes from metadata['group'] / metadata['channel'] (set by the napari-buddy reader),
or is guessed from its name for layers added in other ways. Ticking a box shows the layers of that
group again as they were before it was hidden (all of them if it was never hidden here; only if
their other group is ticked too); unticking hides them. The choices carry over to the next image.

Light module (magicgui only; napari imported lazily).
"""
from magicgui.widgets import Container, CheckBox, Label

TYPE_GROUPS = [("images", "Images (DIC, DAPI)"), ("raw", "Raw channels"), ("filtered", "Filtered channels"),
               ("spots", "Spots"), ("masks", "Masks + buds")]


def layer_group(layer):
    """Type group of a layer: metadata['group'], or guessed from the layer name."""
    group = layer.metadata.get("group") if isinstance(layer.metadata, dict) else None
    if group:
        return group
    name = layer.name.lower()
    if "mask" in name or "bud" in name or "link" in name or "potential" in name:
        return "masks"
    if "spots" in name or "dense regions" in name or "local maxima" in name:
        return "spots"
    if "filtered" in name:
        return "filtered"
    if name in ("dic", "dapi"):
        return "images"
    return "raw" if layer.__class__.__name__ == "Image" else None


def layer_channel(layer):
    return layer.metadata.get("channel") if isinstance(layer.metadata, dict) else None


def layer_groups_widget():
    """
    Checkboxes that show / hide groups of layers (by type and by channel).
    The checkboxes are made once and never removed (only hidden when their group is absent), and the
    choices carry over when the next image is opened: a layer that arrives in an unticked group stays hidden.
    """
    import napari
    viewer = napari.current_viewer()

    wanted = {}     # layer name -> its visibility before this widget hid it

    def _visible(layer):
        g, ch = layer_group(layer), layer_channel(layer)
        on = type_boxes[g].value if g in type_boxes else True
        if ch in channel_boxes:
            on = on and channel_boxes[ch].value
        return on

    def _toggled(kind, key):
        def apply(on):
            members = [l for l in viewer.layers
                       if (kind == "type" and layer_group(l) == key) or (kind == "channel" and layer_channel(l) == key)]
            for l in members:
                if not on:
                    wanted.setdefault(l.name, l.visible)
                    l.visible = False
                elif _visible(l):
                    # as it was before hiding (e.g. the nucleus mask stays hidden); shown if it was never hidden here
                    l.visible = wanted.pop(l.name, True)
        return apply

    # one checkbox per type group, made once
    layers = list(viewer.layers)
    type_boxes = {}
    for key, text in TYPE_GROUPS:
        members = [l for l in layers if layer_group(l) == key]
        box = CheckBox(text=text, value=any(l.visible for l in members) if members else key != "raw")
        box.changed.connect(_toggled("type", key))
        type_boxes[key] = box
    channel_label = Label(value="By channel")
    channel_boxes = {}
    channel_box_container = Container(labels=False)
    status = Label(value="")

    def _add_channel_box(ch):
        box = CheckBox(text=ch, value=True)
        box.changed.connect(_toggled("channel", ch))
        channel_boxes[ch] = box
        channel_box_container.append(box)

    def _update_boxes():
        """Show only the checkboxes of groups / channels that have layers (nothing is removed)."""
        layers = list(viewer.layers)
        present = {layer_group(l) for l in layers}
        channels = {layer_channel(l) for l in layers}
        for key, box in type_boxes.items():
            box.visible = key in present
        for ch, box in channel_boxes.items():
            box.visible = ch in channels
        channel_label.visible = any(ch in channels for ch in channel_boxes)
        status.value = "" if layers else "No layers yet - load an image first."

    def _inserted(event):
        layer = event.value
        ch = layer_channel(layer)
        if ch and ch != "DAPI" and ch not in channel_boxes:
            _add_channel_box(ch)
        if _visible(layer):
            wanted.pop(layer.name, None)          # forget what an earlier image's layer of that name wanted
        else:                                     # arrives in an unticked group: keep it hidden for now
            wanted[layer.name] = layer.visible
            layer.visible = False
        _update_boxes()

    for l in layers:
        ch = layer_channel(l)
        if ch and ch != "DAPI" and ch not in channel_boxes:
            _add_channel_box(ch)
    viewer.layers.events.inserted.connect(_inserted)
    viewer.layers.events.removed.connect(lambda *_: _update_boxes())
    _update_boxes()
    return Container(widgets=[Label(value="By type"), *type_boxes.values(), channel_label, channel_box_container, status],
                     labels=False)
