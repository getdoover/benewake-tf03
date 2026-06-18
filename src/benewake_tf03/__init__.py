from pydoover.docker import run_app

from .application import BenewakeTF03


def main():
    """Run the Benewake TF03 LiDAR application."""
    run_app(BenewakeTF03())
