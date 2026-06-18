from pydoover.tags import Boolean, Number, Tags


class BenewakeTF03Tags(Tags):
    """Published tag values for the Benewake TF03 LiDAR app.

    UI elements bind to these (see ``app_ui.py``), so the dashboard updates
    purely by the main loop setting tags - no imperative UI pushes needed.
    """

    # Headline distance in metres. ``None`` when the reading is unreliable or
    # comms are lost. ``live`` so a watching UI gets fresh values each loop
    # rather than waiting for a periodic flush.
    distance_m = Number(default=None, live=True)

    # Supporting diagnostics.
    distance_raw_cm = Number(default=None)
    signal_strength = Number(default=None)

    # Whether the latest distance passed the strength / range checks. Published
    # for other apps and the cloud to consume.
    reading_reliable = Boolean(default=False)

    # True while we have communication with the sensor. Drives the comms
    # warning (``hidden=comms_ok``): hidden when comms are fine, shown when not.
    comms_ok = Boolean(default=False)

    # Resolved visibility for the weak-signal warning. True (hidden) unless the
    # sensor is talking *and* the reading is unreliable - so it never stacks on
    # top of the no-comms warning.
    signal_warning_hidden = Boolean(default=True)

    # Epoch milliseconds of the last successful read; drives "time since" in UI.
    last_read = Number(default=None)
