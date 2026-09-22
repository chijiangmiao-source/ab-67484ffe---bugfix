import pytest

from server_util import RunningServer


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "shotnumbers.db"


@pytest.fixture
def server(db_path):
    srv = RunningServer(db_path)
    srv.start()
    yield srv
    srv.stop()
