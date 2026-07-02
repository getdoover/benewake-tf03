"""Drop detection over the TF03's high-rate height stream.

The sensor streams at ~100 Hz; the main loop runs slower (e.g. 10 Hz) and feeds
every captured frame through :class:`DropDetector`. The detector tracks velocity
frame-to-frame and runs a small state machine that recognises a sudden downward
movement (a hoist "drop"), measures how far it dropped, and emits a structured
:class:`DropEvent` - including a downsampled trace of the event - when it ends.

The detector is pure and synchronous: it does no I/O and reads no clock of its
own (timestamps are supplied per frame), so it can be unit-tested directly.

Sign convention
---------------
Whether a drop makes the measured distance increase or decrease depends on
mounting (sensor fixed overhead looking down at the car vs. on the car looking
at a fixed reference). ``distance_increases_on_drop`` captures that. Internally
the detector works in "descent position" ``p = s * distance`` where ``s = +1``
if distance increases on a drop and ``-1`` otherwise, so ``p`` always *grows* as
the hoist drops and velocity/magnitude maths is sign-agnostic.
"""

from collections import deque
from dataclasses import dataclass


@dataclass
class DropEvent:
    """A completed drop, in real-world units.

    ``start_ts`` is wall-clock seconds (epoch). Distances are the calibrated
    sensor distances at the onset and at the furthest extent of the drop;
    ``magnitude_m`` is how far the hoist fell (always positive). ``trace`` is a
    downsampled ``[(relative_ms, distance_m), ...]`` series of the event.
    """

    start_ts: float
    pre_distance_m: float
    extent_distance_m: float
    magnitude_m: float
    peak_velocity_mps: float
    duration_ms: int
    trace: list[tuple[int, float]]


class DropDetector:
    """Recognise and measure sudden downward movements in a height stream.

    Feed gated (signal-valid, in-range) frames one at a time via :meth:`feed`;
    it returns a :class:`DropEvent` on the frame that *completes* a drop, else
    ``None``. ``last_velocity_mps`` is the most recent descent velocity (positive
    while dropping) for live publishing.
    """

    def __init__(
        self,
        *,
        velocity_threshold_mps: float,
        min_magnitude_m: float,
        persistence_frames: int,
        distance_increases_on_drop: bool,
        release_velocity_mps: float | None = None,
        settle_frames: int = 5,
        trace_max: int = 512,
        trace_points: int = 200,
    ):
        self.v_thresh = velocity_threshold_mps
        self.min_mag = min_magnitude_m
        self.persist = max(1, persistence_frames)
        self.sign = 1.0 if distance_increases_on_drop else -1.0
        # Hysteresis: a drop is considered over once descent velocity falls below
        # this for ``settle_frames`` frames. Defaults to 40% of the trigger.
        self.release_v = (
            release_velocity_mps
            if release_velocity_mps is not None
            else velocity_threshold_mps * 0.4
        )
        self.settle_frames = max(1, settle_frames)
        self.trace_points = max(2, trace_points)

        self.last_velocity_mps: float | None = None

        # Rolling trace of (t_mono, distance_m) for snapshotting events.
        self._trace: deque[tuple[float, float]] = deque(maxlen=trace_max)
        self._prev: tuple[float, float] | None = None  # (p, t_mono)

        # Event state.
        self._active = False
        self._arm_count = 0
        self._settle_count = 0
        self._candidate: tuple[float, float, float] | None = None  # (p, t_mono, t_wall)
        self._pre_p = 0.0
        self._max_p = 0.0
        self._peak_v = 0.0
        self._start_t_mono = 0.0
        self._start_t_wall = 0.0

    def feed(self, distance_m: float, t_mono: float, t_wall: float) -> DropEvent | None:
        """Process one good frame; return a DropEvent if one just completed."""
        p = self.sign * distance_m
        self._trace.append((t_mono, distance_m))

        prev = self._prev
        self._prev = (p, t_mono)
        if prev is None:
            return None
        prev_p, prev_t = prev
        dt = t_mono - prev_t
        if dt <= 0:
            return None  # duplicate/Out-of-order timestamp; skip

        descent_v = (p - prev_p) / dt  # positive while dropping
        self.last_velocity_mps = descent_v

        if not self._active:
            return self._feed_idle(p, prev_p, prev_t, descent_v, t_mono, t_wall)
        return self._feed_active(p, descent_v, t_mono)

    def _feed_idle(self, p, prev_p, prev_t, descent_v, t_mono, t_wall):
        if descent_v < self.v_thresh:
            self._arm_count = 0
            self._candidate = None
            return None

        if self._arm_count == 0:
            # Onset = the sample *before* motion began, so pre-drop height is the
            # level the hoist fell from.
            self._candidate = (prev_p, prev_t, t_wall)
        self._arm_count += 1
        self._peak_v = max(self._peak_v, descent_v)

        if self._arm_count >= self.persist:
            cand_p, cand_t_mono, cand_t_wall = self._candidate
            self._active = True
            self._pre_p = cand_p
            self._max_p = p
            self._start_t_mono = cand_t_mono
            self._start_t_wall = cand_t_wall
            self._settle_count = 0
        return None

    def _feed_active(self, p, descent_v, t_mono):
        self._max_p = max(self._max_p, p)
        self._peak_v = max(self._peak_v, descent_v)

        if descent_v < self.release_v:
            self._settle_count += 1
        else:
            self._settle_count = 0

        if self._settle_count < self.settle_frames:
            return None
        return self._close(t_mono)

    def _close(self, t_mono: float) -> DropEvent | None:
        magnitude = self._max_p - self._pre_p
        peak_v = self._peak_v
        pre_distance = self.sign * self._pre_p
        extent_distance = self.sign * self._max_p
        duration_ms = int(round((t_mono - self._start_t_mono) * 1000))
        start_wall = self._start_t_wall
        start_mono = self._start_t_mono

        self._reset_event()

        if magnitude < self.min_mag:
            return None  # jitter, not a real drop

        return DropEvent(
            start_ts=start_wall,
            pre_distance_m=pre_distance,
            extent_distance_m=extent_distance,
            magnitude_m=magnitude,
            peak_velocity_mps=peak_v,
            duration_ms=duration_ms,
            trace=self._snapshot_trace(start_mono),
        )

    def _reset_event(self):
        self._active = False
        self._arm_count = 0
        self._settle_count = 0
        self._candidate = None
        self._peak_v = 0.0

    def _snapshot_trace(self, start_t_mono: float) -> list[tuple[int, float]]:
        pts = [(t, d) for (t, d) in self._trace if t >= start_t_mono]
        if not pts:
            return []
        # Downsample to at most trace_points by striding.
        stride = max(1, len(pts) // self.trace_points)
        sampled = pts[::stride]
        t0 = pts[0][0]
        return [(int(round((t - t0) * 1000)), round(d, 3)) for (t, d) in sampled]
