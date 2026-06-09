import logging

from pydoover.state import StateMachine

# How long the sensor can be silent before we declare the link dead and clear
# the displayed reading.
TIME_TILL_DROPOUT = 60  # seconds

log = logging.getLogger(__name__)


class TF03State:
    """Tracks whether we currently have communications with the TF03 sensor.

    A short period of silence is tolerated (`maybe_no_comms`) before the link is
    declared dead, so a single dropped Modbus response does not blank the UI.
    """

    state: str

    states = [
        {"name": "initial"},
        {"name": "comms"},
        {
            "name": "maybe_no_comms",
            "timeout": TIME_TILL_DROPOUT,
            "on_timeout": "lost_comms",
        },
        {"name": "no_comms"},
    ]

    transitions = [
        {"trigger": "initialise", "source": "initial", "dest": "no_comms"},
        {
            "trigger": "got_comms",
            "source": ["comms", "maybe_no_comms", "no_comms"],
            "dest": "comms",
        },
        {"trigger": "maybe_lost_comms", "source": "comms", "dest": "maybe_no_comms"},
        {"trigger": "lost_comms", "source": "maybe_no_comms", "dest": "no_comms"},
    ]

    def __init__(self):
        self.state_machine = StateMachine(
            states=self.states,
            transitions=self.transitions,
            model=self,
            initial="no_comms",
            queued=True,
        )

    async def spin(self):
        log.debug(f"Current state: {self.state}")
        if self.state == "initial":
            await self.initialise()

    async def register_comms(self):
        """Call whenever the device has successfully read from the sensor."""
        await self.got_comms()

    async def register_no_comms(self):
        """Call whenever a read from the sensor has failed."""
        if self.state == "comms":
            await self.maybe_lost_comms()
