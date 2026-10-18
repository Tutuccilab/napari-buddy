"""
napari panel "buddy pipeline": the steps of 01_fish_bulk_processing.ipynb with buttons.

    config file, input folder, output folder      (input / output are filled in from the config file)
    Create config file...                         opens the Create config file panel
    1 Read | 2 Segment | 3 Spots + buds           run in the background (napari stays usable), with a
    5 Reassign spots                              progress bar and a time estimate
    4 Check and correct                           opens the Correct images panel (previous / save / save + next / skip)
    Run 1-3                                       the automatic steps one after the other (step 4 is by hand)
    Stop after this image

Starting a step closes the layers in napari (and the read-ahead cache of the Correct images panel): a step-3
image needs several GB of RAM, which open layers would compete with.

The steps run the same functions as the notebook (buddy/pipeline.py), with the same re-run check: images
already processed with the same settings are skipped; for images processed with other settings a yes/no
question lists what changed ("if_already_processed": "skip" / "overwrite" in the config answer it for you).

Time estimate: at the start from the step times saved in img.json of images processed before (or a rough
default), then from the images of this run (the more images are done, the more they count).

Light module: buddy (big-fish, Omnipose, torch) is imported only when a step starts.
"""
import gc
import time
from pathlib import Path

from magicgui.widgets import Container, FileEdit, Label, ProgressBar, PushButton

# rough seconds per image when there is nothing to go on (laptop with GPU, ~2.5 GB images)
DEFAULT_SECONDS = {'read': 35, 'segment': 50, 'spots_a': 80, 'spots_b': 20, 'reassign': 15}


# ---------------------------------------------------------------------------------------------
# time estimate
# ---------------------------------------------------------------------------------------------
def prior_seconds(json_files, keys):
    """Median time per image of earlier runs: the sum of `keys` in img.json -> time, or None."""
    import json
    import statistics
    totals = []
    for f in json_files:
        try:
            times = json.load(open(f)).get('time', {})
        except (OSError, ValueError):
            continue
        values = [times[k] for k in keys if isinstance(times.get(k), (int, float))]
        if values:
            totals.append(sum(values))
    return statistics.median(totals) if totals else None


def format_seconds(s):
    if s < 60:
        return f"{max(1, round(s))} s"
    if s < 3600:
        return f"{round(s / 60)} min"
    return f"{s / 3600:.1f} h"


class Estimate:
    """
    Time left for a step made of phases (e.g. step 3: 'spots_a' for all images, then 'spots_b').
    phases: {name: (number of images, prior seconds per image)}. Every finished image counts as one
    measurement (the time since the previous one finished, so parallel work is counted as throughput);
    the prior counts as two measurements, so after a few images this run's own speed takes over.
    """
    PRIOR_WEIGHT = 2

    def __init__(self, phases):
        self.phases = {name: {'left': n, 'prior': prior, 'times': []} for name, (n, prior) in phases.items()}
        self.total = sum(n for n, _ in phases.values())
        self.done = 0
        self.last = time.time()

    def image_done(self, phase, now=None):
        now = time.time() if now is None else now
        p = self.phases[phase]
        p['times'].append(now - self.last)
        p['left'] -= 1
        self.done += 1
        self.last = now

    def restart_clock(self, now=None):
        """Call when a phase starts after a pause (e.g. after loading a model), so the pause is not counted."""
        self.last = time.time() if now is None else now

    def seconds_per_image(self, phase):
        p = self.phases[phase]
        weight = self.PRIOR_WEIGHT if p['prior'] else 0
        n = len(p['times'])
        if n + weight == 0:
            return None
        return ((p['prior'] or 0) * weight + sum(p['times'])) / (weight + n)

    def seconds_left(self):
        total = 0.0
        for name, p in self.phases.items():
            if p['left'] <= 0:
                continue
            s = self.seconds_per_image(name)
            if s is None:
                return None
            total += p['left'] * s
        return total

    def text(self):
        left = self.seconds_left()
        when = "estimating..." if left is None else ("almost done" if left < 1 else f"about {format_seconds(left)} left")
        return f"{self.done}/{self.total} · {when}"


# ---------------------------------------------------------------------------------------------
# the panel
# ---------------------------------------------------------------------------------------------
STEPS = [('read', '1  Read images'), ('segment', '2  Segment cells + nuclei'),
         ('spots', '3  Spots + buds + counts'), ('review', '4  Check and correct'),
         ('reassign', '5  Reassign spots')]
ALL_STEPS = ('read', 'segment', 'spots')         # the "Run 1-3" button: the automatic steps, one after the other


def _ask_dialog(text):
    """Yes/no dialog (answer No if there is no window)."""
    try:
        from qtpy.QtWidgets import QMessageBox
        answer = QMessageBox.question(None, "buddy pipeline: already processed", text,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer == QMessageBox.Yes
    except Exception:
        return False


def pipeline_widget(ask=None):
    """
    The buddy pipeline panel. ask: yes/no question for overwriting (default: a dialog; tests pass a function).
    """
    import napari
    viewer = napari.current_viewer()
    ask = ask or _ask_dialog

    cfg_file = FileEdit(label="config file", filter="*.json")
    inputdir = FileEdit(label="input folder", mode="d")
    outputdir = FileEdit(label="output folder", mode="d")
    create_btn = PushButton(text="Create config file...")
    buttons = {key: PushButton(text=text) for key, text in STEPS}
    all_btn = PushButton(text="Run 1-3  (read, segment, spots + buds + counts)")
    stop_btn = PushButton(text="Stop after this image", enabled=False)
    progress = ProgressBar(value=0, min=0, max=1, label="progress")
    status = Label(value="Choose a config file.")
    step_status = {key: Label(value="") for key, _ in STEPS}
    state = {'exp': None, 'worker': None, 'stop': False, 'models': {}, 'chain': []}

    # ---- config ------------------------------------------------------------------------------
    def _config_chosen(*_):
        import json
        path = Path(str(cfg_file.value))
        if not path.is_file():
            return
        try:
            cfg = json.load(open(path))
        except ValueError as e:
            status.value = f"Cannot read {path.name}: {e}"
            return
        if cfg.get('inputdir'):
            inputdir.value = cfg['inputdir']
        if cfg.get('outputdir'):
            outputdir.value = cfg['outputdir']
        status.value = f"Config: {path.name}"
        _show_done()

    cfg_file.changed.connect(_config_chosen)
    outputdir.changed.connect(lambda *_: _show_done())

    def _create_config(*_):
        from ._config_widget import config_widget
        from ._review import _dock_once
        _dock_once(viewer, 'Create config file', config_widget)

    create_btn.clicked.connect(_create_config)

    def _experiment():
        """A fresh Experiment from the config file and the chosen folders (models of the previous one are reused)."""
        from buddy.experiment import Experiment
        path = Path(str(cfg_file.value))
        if not path.is_file():
            raise ValueError("choose a config file first")
        for name, folder in (('input', inputdir.value), ('output', outputdir.value)):
            if str(folder) in ('', '.'):
                raise ValueError(f"choose the {name} folder first")
        exp = Experiment.from_cfg_file(str(path))
        exp.inputdir, exp.outputdir = str(inputdir.value), str(outputdir.value)
        Path(exp.outputdir).mkdir(parents=True, exist_ok=True)
        old = state['exp']
        if old is not None:          # keep loaded models when the settings they depend on did not change
            if getattr(old, 'cell_model', None) is not None and old.use_gpu == exp.use_gpu:
                exp.cell_model, exp.nuclei_model, exp.use_GPU = old.cell_model, old.nuclei_model, old.use_GPU
            if hasattr(old, 'bud_model') and old.bud_classification == exp.bud_classification \
                    and old.use_gpu == exp.use_gpu:
                exp.bud_model = old.bud_model
        state['exp'] = exp
        return exp

    def _show_done():
        """How many images each step has done (from img.json -> last_run)."""
        import json
        out = Path(str(outputdir.value))
        files = sorted(out.glob('*/img.json')) if out.is_dir() else []
        stages = []
        for f in files:
            try:
                stages.append(json.load(open(f)).get('last_run'))
            except (OSError, ValueError):
                stages.append(None)
        order = ['configure', 'segment', 'spots']
        for key, stage in (('read', 'configure'), ('segment', 'segment'), ('spots', 'spots')):
            n = sum(1 for s in stages if s in order and order.index(s) >= order.index(stage))
            if not (state['worker'] and state.get('running') == key):
                step_status[key].value = f"{n} image(s) done" if files else ""

    # ---- running a step in the background ------------------------------------------------------
    def _busy(on, key=None):
        state['running'] = key if on else None
        for k, b in buttons.items():
            b.enabled = not on
        all_btn.enabled = not on
        create_btn.enabled = cfg_file.enabled = inputdir.enabled = outputdir.enabled = not on
        stop_btn.enabled = on
        if not on:
            stop_btn.text = "Stop after this image"

    SMOOTH = 1000                       # progress bar units per image: moves during an image, not only between images

    def _on_message(message):
        kind, key, *rest = message
        if kind == 'progress':
            done, total, text, seconds_left = rest
            units_left = max(total - done, 1)
            state['progress'] = (done, max(total, 1), (seconds_left or 0) / units_left, time.time())
            _tick()
            step_status[key].value = text
        elif kind == 'status':
            status.value = rest[0]

    def _tick(*_):
        """Advance the bar within the current image, from the time estimate (never beyond 95% of the image),
        and show what buddy is doing right now (pipeline.progress_callback, set while a step runs)."""
        sub = state.get('substep')
        if sub and sub != state.get('substep_shown'):
            status.value = sub
            state['substep_shown'] = sub
        if 'progress' not in state:
            return
        done, total, expected, since = state['progress']
        part = min((time.time() - since) / expected, 0.95) if expected > 0 else 0.0
        progress.max = total * SMOOTH
        progress.value = int((done + part) * SMOOTH)

    from qtpy.QtCore import QTimer
    ticker = QTimer()
    ticker.setInterval(500)
    ticker.timeout.connect(_tick)

    def _release_omnipose(exp):
        """Drop the Omnipose networks and free the GPU when step 2 is done, so that step 3 loads the bud model
        on a clean GPU (loading it next to the resident Omnipose models hung or crashed now and then). A later
        step 2 loads Omnipose again."""
        exp.cell_model = exp.nuclei_model = None
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _free_viewer_memory():
        """Close the layers in napari and drop the read-ahead cache of the Correct-images panel: a step-3 image
        needs several GB, and the open layers of a reviewed image compete with it for RAM."""
        import napari
        viewer = napari.current_viewer()
        if viewer is not None and len(viewer.layers):
            viewer.layers.clear()
        try:
            from . import _review
            _review._PREFETCH.clear()
        except Exception:
            pass
        gc.collect()

    def _start(key, generator_function, todo):
        from napari.qt.threading import thread_worker
        _free_viewer_memory()
        _busy(True, key)
        progress.value = 0
        state.pop('progress', None)
        state.pop('substep', None); state.pop('substep_shown', None)
        from buddy import pipeline
        if hasattr(pipeline, 'progress_callback'):                      # buddy >= 0.1.0: what is happening right now
            pipeline.progress_callback = lambda stem, text: state.__setitem__('substep', f"{stem}: {text}")
        ticker.start()
        worker = thread_worker(generator_function, start_thread=False)(todo)
        worker.yielded.connect(_on_message)

        def finished(*_):
            ticker.stop()
            if hasattr(pipeline, 'progress_callback'):
                pipeline.progress_callback = None
            state.pop('substep', None)
            state['worker'] = None
            _busy(False)
            _show_done()
            _continue_chain()

        def errored(e):
            status.value = f"Stopped by an error: {e!r} (see the terminal for details)"

        worker.errored.connect(errored)
        worker.finished.connect(finished)
        state['worker'] = worker
        worker.start()

    def _stop(*_):
        state['stop'] = True
        stop_btn.enabled = False
        stop_btn.text = "Stopping after this image..."

    stop_btn.clicked.connect(_stop)

    def _serial(key, phase, function, todo, estimate, label):
        """Run function(item) for each image, yielding progress; returns (done, failed)."""
        import logging
        done = failed = 0
        estimate.restart_clock()
        for item in todo:
            if state['stop']:
                break
            try:
                function(item)
                done += 1
            except MemoryError:                   # the computer's RAM, not the GPU
                failed += 1
                logging.exception(f"{label}: image {item} failed")
                yield ('status', key, f"{label}: {Path(str(item)).parent.name or item} failed: out of memory (RAM). "
                       "Close images in napari or other programs, or run this step from the notebook.")
            except Exception as e:                # one failing image does not stop the batch
                failed += 1
                logging.exception(f"{label}: image {item} failed")
                yield ('status', key, f"{label}: {Path(str(item)).parent.name or item} failed: {e!r}")
            gc.collect()                          # free the image's stacks before the next one
            estimate.image_done(phase)
            yield ('progress', key, estimate.done, estimate.total, f"{label}: {estimate.text()}", estimate.seconds_left())
        return done, failed

    def _summary(key, label, done, failed, total, started):
        text = f"{label}: {done} of {total} image(s) done in {format_seconds(time.time() - started)}"
        if failed:
            text += f", {failed} failed (see the terminal)"
        if state['stop'] and done + failed < total:
            text += " - stopped"
        return ('status', key, text)

    # ---- the steps -------------------------------------------------------------------------------
    def _run(key, chain=()):
        """Run one step in the background; chain: the steps to run after it (the Run 1-3 button)."""
        state['stop'] = False
        state['chain'] = list(chain)
        _run_step(key)

    def _continue_chain():
        if state['chain'] and not state['stop']:
            _run_step(state['chain'].pop(0))
        else:
            state['chain'] = []

    def _preload_bud_model(exp, key):
        """Load the bud model in the GUI thread, before the step's worker starts. Loading it from a worker thread
        (the first CUDA call of that thread) stalled forever now and then on Windows; from the main thread it has
        not. Done for step 3, and for step 2 when step 3 follows in the chain (Run 1-3)."""
        if not exp.bud_classification['enabled'] or hasattr(exp, 'bud_model'):
            return
        if key == 'spots' or (key == 'segment' and 'spots' in state['chain']):
            status.value = "Loading the bud model..."
            from qtpy.QtWidgets import QApplication
            QApplication.processEvents()
            exp.init_bud_model()

    def _run_step(key):
        try:
            exp = _experiment()
            _preload_bud_model(exp, key)
        except Exception as e:
            status.value = f"Cannot start: {e}"
            state['chain'] = []
            return
        from buddy.rerun_check import select_images
        if key == 'read':
            exp.create_image_list()
            if not exp.images:
                status.value = f"No .vsi images or TIFF stacks (with a DIC image) found in {exp.inputdir}"
                state['chain'] = []
                return
            todo = select_images(exp, 'read', ask=ask)
        elif key in ('segment', 'spots'):
            exp.read_image_list_from_jsons()
            todo = select_images(exp, key, ask=ask)
        else:                                       # reassign: all images
            exp.read_image_list_from_jsons()
            todo = list(exp.json_files)
        if not todo:
            step_status[key].value = f"{dict(STEPS)[key].split('  ')[1]}: nothing to do"
            _continue_chain()                       # in a chain: on to the next step
            return
        status.value = f"{dict(STEPS)[key].split('  ')[1]}: {len(todo)} image(s)"
        _start(key, {'read': _read, 'segment': _segment, 'spots': _spots, 'reassign': _reassign}[key], todo)

    def _earlier(exp):
        return sorted(Path(exp.outputdir).glob('*/img.json'))

    def _read(todo):
        from buddy.parallel import default_workers, iter_parallel, read_one
        exp, started = state['exp'], time.time()
        workers = min(default_workers(gb_per_image=4), len(todo))
        prior = prior_seconds(_earlier(exp), ['01-configure'])
        estimate = Estimate({'read': (len(todo), (prior or DEFAULT_SECONDS['read']) / workers)})
        mode = f'parallel ({workers} workers)'
        yield ('status', 'read', f"Read: {len(todo)} image(s), {workers} at a time")
        yield ('progress', 'read', 0, len(todo), f"Read: {estimate.text()}", estimate.seconds_left())
        jobs = [(params, exp.cfg_file, exp.inputdir, exp.outputdir, mode) for params in todo]
        done = failed = 0
        for job, result, error in iter_parallel(read_one, jobs, workers, should_stop=lambda: state['stop']):
            done, failed = done + (error is None), failed + (error is not None)
            estimate.image_done('read')
            yield ('progress', 'read', estimate.done, estimate.total, f"Read: {estimate.text()}", estimate.seconds_left())
        yield _summary('read', 'Read', done, failed, len(todo), started)

    def _segment(todo):
        from buddy import pipeline
        exp, started = state['exp'], time.time()
        prior = prior_seconds(_earlier(exp), pipeline.STEP_TIMES['segment'])
        estimate = Estimate({'segment': (len(todo), prior or DEFAULT_SECONDS['segment'])})
        yield ('progress', 'segment', 0, len(todo), f"Segment: {estimate.text()}", estimate.seconds_left())
        if 'spots' in state['chain'] and exp.bud_classification['enabled'] and not hasattr(exp, 'bud_model'):
            # Run 1-3: load the bud model now, before Omnipose, on an untouched GPU. Loading it in step 3, after
            # Omnipose ran in another thread, stalled in the first CUDA call now and then (an idle, empty GPU;
            # torch waits forever). The model is kept on the Experiment for step 3.
            yield ('status', 'segment', "Segment: loading the bud model (for step 3)...")
            exp.init_bud_model()
        if getattr(exp, 'cell_model', None) is None:
            yield ('status', 'segment', "Segment: loading Omnipose...")
            exp.init_omnipose()
        yield ('status', 'segment', f"Segment: {len(todo)} image(s) on the {'GPU' if exp.use_GPU else 'CPU'}")
        done, failed = yield from _serial('segment', 'segment', lambda f: pipeline.segment_image(f, exp),
                                          todo, estimate, 'Segment')
        _release_omnipose(exp)
        yield _summary('segment', 'Segment', done, failed, len(todo), started)

    def _spots(todo):
        from buddy import pipeline
        from buddy.experiment import gpu_available
        from buddy.parallel import default_workers, iter_parallel, spots_one
        exp, started = state['exp'], time.time()
        earlier = _earlier(exp)
        gpu_spots = exp.parameters.get('gpu_spot_detection', True) and gpu_available(exp.use_gpu)
        workers = 1 if gpu_spots else min(default_workers(gb_per_image=4), len(todo))
        mode = ('serial' if workers == 1 else f'parallel ({workers} workers)') + (' + GPU spot detection' if gpu_spots else '')
        prior_a = prior_seconds(earlier, ['03-detect-spots', '04-decompose-spots', 'align'])
        prior_b = prior_seconds(earlier, ['bud-classification', '05-assign-spots'])
        estimate = Estimate({'spots_a': (len(todo), (prior_a or DEFAULT_SECONDS['spots_a']) / workers),
                             'spots_b': (len(todo), prior_b or DEFAULT_SECONDS['spots_b'])})
        yield ('status', 'spots', f"Spots: {len(todo)} image(s), {mode}")
        yield ('progress', 'spots', 0, estimate.total, f"Spots: {estimate.text()}", estimate.seconds_left())

        def load_bud_model():
            if not hasattr(exp, 'bud_model'):
                yield ('status', 'spots', "Spots: loading the bud model..." if exp.bud_classification['enabled']
                       else "Spots: running")
                # loading has hung now and then (napari, after step 2): if it takes more than a minute, print
                # the stack of every thread to the terminal, so the hang shows where it sits
                import faulthandler, sys
                try:                                   # sys.__stderr__: the real terminal, not napari's redirect
                    faulthandler.dump_traceback_later(60, repeat=True, file=sys.__stderr__)
                except Exception:
                    pass
                try:
                    exp.init_bud_model()
                finally:
                    faulthandler.cancel_dump_traceback_later()
                estimate.restart_clock()

        def both(f):                       # 3a + 3b for one image
            pipeline.spots_image(f, exp, mode)
            estimate.image_done('spots_a')
            pipeline.buds_and_counts(f, exp)

        if workers == 1:
            # on the GPU: one image after the other, 3a (spots, alignment) and 3b (bud model, counts) together
            yield from load_bud_model()
            estimate.phases['spots_a']['left'], estimate.phases['spots_b']['left'] = len(todo), len(todo)
            done, failed = yield from _serial('spots', 'spots_b', both, todo, estimate, 'Spots')
        else:
            # without a GPU: 3a for all images in parallel, then 3b one after the other
            jobs = [(f, exp.cfg_file, exp.inputdir, exp.outputdir, mode) for f in todo]
            ok, failed = [], 0
            for job, result, error in iter_parallel(spots_one, jobs, workers, should_stop=lambda: state['stop']):
                (ok.append(job[0]) if error is None else None)
                failed += error is not None
                estimate.image_done('spots_a')
                yield ('progress', 'spots', estimate.done, estimate.total, f"Spots (3a): {estimate.text()}", estimate.seconds_left())
            estimate.phases['spots_a']['left'] = 0
            estimate.phases['spots_b']['left'] = len(ok)
            estimate.total = estimate.done + len(ok)
            # images that finished 3a always get 3b (also after Stop), so none is left half done
            stop, state['stop'] = state['stop'], False
            yield from load_bud_model()
            done, failed_b = yield from _serial('spots', 'spots_b', lambda f: pipeline.buds_and_counts(f, exp),
                                                ok, estimate, 'Spots (3b)')
            state['stop'], failed = stop, failed + failed_b
        yield _summary('spots', 'Spots + buds + counts', done, failed, len(todo), started)

    def _reassign(todo):
        from buddy import pipeline
        exp, started = state['exp'], time.time()
        prior = prior_seconds(_earlier(exp), ['05-assign-spots'])
        estimate = Estimate({'reassign': (len(todo), prior or DEFAULT_SECONDS['reassign'])})
        yield ('progress', 'reassign', 0, len(todo), f"Reassign: {estimate.text()}", estimate.seconds_left())
        done, failed = yield from _serial('reassign', 'reassign', lambda f: pipeline.reassign_image(f, exp),
                                          todo, estimate, 'Reassign')
        yield _summary('reassign', 'Reassign spots', done, failed, len(todo), started)

    def _review(*_):
        try:
            exp = _experiment()
        except Exception as e:
            status.value = f"Cannot start: {e}"
            return
        exp.create_image_list()
        if not exp.images:
            status.value = f"No images found in {exp.inputdir}"
            return
        from ._review import review_images
        status.value = "Check and correct: use the Correct images panel (previous / save / save + next / skip)"
        review_images(exp, start=0)

    for key, button in buttons.items():
        button.clicked.connect(_review if key == 'review' else (lambda *_, k=key: _run(k)))
    all_btn.clicked.connect(lambda *_: _run(ALL_STEPS[0], chain=ALL_STEPS[1:]))

    rows = []
    for key, _ in STEPS:
        rows += [buttons[key], step_status[key]]
    return Container(widgets=[cfg_file, inputdir, outputdir, create_btn, Label(value="Steps"), *rows, all_btn,
                              progress, stop_btn, status])
