import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    if os.getenv("RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_INTEGRATION=1 to run integration tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


# Import every model module so the shared SQLAlchemy metadata contains all
# tables and cross-module foreign keys (e.g. retention holds referencing
# connector source extracts) resolve in every test process, mirroring
# migrations/env.py.
from app.auth import models as auth_models  # noqa: E402, F401
from app.browser import models as browser_models  # noqa: E402, F401
from app.connectors import models as connector_models  # noqa: E402, F401
from app.events import models as event_models  # noqa: E402, F401
from app.evidence import models as evidence_models  # noqa: E402, F401
from app.hypotheses import models as hypothesis_models  # noqa: E402, F401  # noqa
from app.incidents import models as incident_models  # noqa: E402, F401
from app.metrics import models as metric_models  # noqa: E402, F401
