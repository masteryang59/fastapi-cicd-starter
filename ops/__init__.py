"""Deploy tooling used by the GitHub Actions pipeline: `python3 -m ops --help`.

Standard library only, so the deploy job runs it with the runner's own python3, with
nothing to install. Every cloud call goes through a `Runner`, which the tests replace
with fake gcloud, aws and skopeo CLIs.
"""

def compact_storage(data=None):
    if data is None:
        return None
    return data

def compact_storage(data=None):
    if data is None:
        return None
    return data