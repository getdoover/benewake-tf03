import logging
import time
from typing import TYPE_CHECKING

from pydoover import ui

if TYPE_CHECKING:
    from .app_config import BenewakeTF03Config

log = logging.getLogger()


class BenewakeTF03UI:
    def __init__(self, config: "BenewakeTF03Config"):
        self.config = config

        # The primary reading the user cares about: distance in metres.
        self.distance = ui.NumericVariable(
            "distance",
            "Distance (m)",
            precision=2,
        )

        # Supporting detail / diagnostics.
        self.raw_distance_cm = ui.NumericVariable(
            "rawDistanceCm", "Raw Distance (cm)", precision=0
        )
        self.signal_strength = ui.NumericVariable(
            "signalStrength",
            "Signal Strength",
            precision=0,
            ranges=[
                ui.Range(
                    "Weak",
                    0,
                    self.config.min_signal_strength.default,
                    colour=ui.Colour.yellow,
                ),
                ui.Range(
                    "Good",
                    self.config.min_signal_strength.default,
                    3500,
                    colour=ui.Colour.green,
                ),
            ],
        )
        self.time_last_update = ui.DateTimeVariable(
            "timeLastUpdate", "Time Since Last Read"
        )

        self.comms_warning = ui.WarningIndicator(
            "commsWarning", "No communication with sensor", hidden=True
        )
        self.signal_warning = ui.WarningIndicator(
            "signalWarning", "Weak signal - distance unreliable", hidden=True
        )

        self.details = ui.Submodule(
            "details",
            "Sensor Details",
            children=[
                self.raw_distance_cm,
                self.signal_strength,
                self.time_last_update,
            ],
        )

    def fetch(self):
        return (
            self.distance,
            self.comms_warning,
            self.signal_warning,
            self.details,
        )

    def update(
        self,
        distance_m: float,
        raw_distance_cm: int,
        signal_strength: int,
        reliable: bool,
        last_read_ts: float,
    ) -> None:
        """Push a fresh reading to the UI."""
        self.comms_warning.hidden = True
        self.signal_warning.hidden = reliable

        # When the reading is unreliable, show no distance rather than a bogus value.
        self.distance.update(distance_m if reliable else None)
        self.raw_distance_cm.update(raw_distance_cm)
        self.signal_strength.update(signal_strength)
        self.time_last_update.update(time.time() - last_read_ts)

    def update_no_comms(self) -> None:
        """Blank the UI and raise the comms warning when the sensor is unreachable."""
        self.comms_warning.hidden = False
        self.signal_warning.hidden = True
        self.distance.update(None)
        self.raw_distance_cm.update(None)
        self.signal_strength.update(None)
        self.time_last_update.update(None)
