from pathlib import Path

from pydoover import ui

from .app_tags import BenewakeTF03Tags

# Datasheet weak/good signal-strength boundary for the TF03. Matches the
# `min_signal_strength` config default; hard-coded here because the static UI
# schema is exported without a config instance.
_MIN_SIGNAL_STRENGTH = 40
_MAX_SIGNAL_STRENGTH = 3500


class BenewakeTF03UI(ui.UI, display_name="$config.app().sensor_name"):
    # The primary reading the user cares about: distance in metres.
    distance = ui.NumericVariable(
        "Distance",
        units="m",
        value=BenewakeTF03Tags.distance_m,
        precision=2,
    )

    comms_warning = ui.WarningIndicator(
        "No communication with sensor",
        hidden=BenewakeTF03Tags.comms_ok,
    )
    signal_warning = ui.WarningIndicator(
        "Weak signal - distance unreliable",
        hidden=BenewakeTF03Tags.signal_warning_hidden,
    )

    # Supporting detail / diagnostics, tucked into a collapsible submodule.
    details = ui.Submodule(
        "Sensor Details",
        children=[
            ui.NumericVariable(
                "Raw Distance",
                units="cm",
                value=BenewakeTF03Tags.distance_raw_cm,
                precision=0,
            ),
            ui.NumericVariable(
                "Signal Strength",
                value=BenewakeTF03Tags.signal_strength,
                precision=0,
                ranges=[
                    ui.Range(
                        "Weak",
                        0,
                        _MIN_SIGNAL_STRENGTH,
                        colour=ui.Colour.yellow,
                    ),
                    ui.Range(
                        "Good",
                        _MIN_SIGNAL_STRENGTH,
                        _MAX_SIGNAL_STRENGTH,
                        colour=ui.Colour.green,
                    ),
                ],
            ),
            ui.Timestamp(
                "Last Read",
                value=BenewakeTF03Tags.last_read,
            ),
        ],
    )


def export():
    BenewakeTF03UI(None, None, None).export(
        Path(__file__).parents[2] / "doover_config.json", "benewake_tf03"
    )
