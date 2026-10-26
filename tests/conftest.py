import os

# The app only answers for known Host headers; Starlette's TestClient uses "testserver".
os.environ.setdefault("LINEAGELENS_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")

import os
import tempfile

import pytest

# Keep all test databases out of the user's real data folder.
os.environ["LINEAGELENS_HOME"] = tempfile.mkdtemp(prefix="lineagelens-test-")

from lineagelens.builder import build  # noqa: E402
from lineagelens.config import SAMPLES_DIR, load_config  # noqa: E402

NET_AMOUNT = "dbt:model.retail_analytics.fct_sales.NET_AMOUNT"
NET_SALES_CARD = "rpt:RetailSales:visual:a1b2c3d4e5f60718:c0ffee000000000001"


@pytest.fixture(scope="session")
def scan():
    return build(load_config(None))


@pytest.fixture(scope="session")
def graph(scan):
    return scan.graph


@pytest.fixture(scope="session")
def samples():
    return SAMPLES_DIR
