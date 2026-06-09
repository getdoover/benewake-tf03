from pydoover.docker import run_app

from .app_config import BenewakeTF03Config
from .application import BenewakeTF03


def main():
    """Run the Benewake TF03 LiDAR application."""
    run_app(BenewakeTF03(config=BenewakeTF03Config()))
