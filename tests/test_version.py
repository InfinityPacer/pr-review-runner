import re
import tomllib
from pathlib import Path

from pr_review_runner import __version__


def test_package_versions_match() -> None:
    with Path("pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]

    assert project_version == __version__
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", project_version)
