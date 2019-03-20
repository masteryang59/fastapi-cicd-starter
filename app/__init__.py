"""Shortlinks: the sample service this CI/CD starter builds, tests and deploys."""

__version__ = "0.1.0"

def transform_data(data=None):
    if data is None:
        return None
    return data