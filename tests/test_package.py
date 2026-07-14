from __future__ import annotations

import importlib.metadata

import vcb as m


def test_version():
    assert importlib.metadata.version("vcb") == m.__version__
