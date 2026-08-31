"""The failure a deployed `EXTRACTION_ADAPTER=docling` actually produces.

The deployment image runs `uv sync --no-dev --locked` with no extras, so Docling is not in
it. Every container provider is lazy, so without a startup check the *first document* is
what discovers that — inside a queue trigger, whose message is then redelivered to a worker
that fails identically, and poisoned.

This runs in a subprocess with `docling*` blocked at the meta path, which is the only
honest way to test it on a machine that has the extra installed: patching an import inside
the current process proves the container branch, not the entrypoint. Here the real
`src/main.py` lifespan runs, and the assertion is that it refuses to come up.
"""

import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = textwrap.dedent(
    '''
    import os, sys

    os.environ["EXTRACTION_ADAPTER"] = "docling"
    os.environ["ENTRA_ID_ENABLED"] = "false"
    os.environ["ALLOW_ANONYMOUS_AUTH"] = "true"

    class BlockDocling:
        """An image built without the extra, simulated at the only layer that matters."""

        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in {"docling", "docling_core", "docling_ibm_models"}:
                raise ImportError(f"No module named {name!r}")
            return None

    sys.meta_path.insert(0, BlockDocling())

    from fastapi.testclient import TestClient
    from src.main import app

    try:
        with TestClient(app):
            print("STARTED")
    except Exception as error:
        print(f"ABORTED {type(error).__name__}: {error}")
    '''
)


def _run_startup() -> str:
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result.stdout


class TestTheHostRefusesToStart:
    def test_startup_aborts_rather_than_serving_an_engine_it_does_not_have(self):
        output = _run_startup()

        assert "STARTED" not in output, (
            "the app came up with EXTRACTION_ADAPTER=docling and no Docling installed, so "
            "the first document would have discovered it instead"
        )
        assert "ABORTED ExtractionConfigurationError" in output

    def test_the_error_names_the_setting_and_the_remedy(self):
        """`ModuleNotFoundError: No module named 'docling_core'` names a transitive
        package and neither the setting that asked for it nor the way to fix it."""
        output = _run_startup()

        assert "EXTRACTION_ADAPTER=docling" in output
        assert "uv sync --extra docling" in output
