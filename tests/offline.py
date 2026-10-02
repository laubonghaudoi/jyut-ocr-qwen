"""What every offline check runs with: a pair-class store of its own, and an
endpoint nothing listens on.

Not a check itself.  Importing it points the pair-class store
(PAIR_CACHE_PATH) at a temporary store of this process's own, with no model
tag, and the default endpoint (PROOFREAD_ENDPOINT) at CLOSED_ENDPOINT, before
any check runs and whatever the environment named; processes the check starts
inherit both.  So a check that runs proofread_pages.main() or
book_profile.main() without saying where reads and writes nothing of the
machine's store (~/.cache/jyut-ocr), and no request of it reaches the
machine's model server.  Found on 2026-09-29 in the machine's store: 20
answers of an offline replay's stand-in kept under the model server's
identity (scripts/_pair_cache.py says how, and why the store no longer keeps
them).  tests/stand_in.py imports it; so does every check that runs the
scripts without it.
"""

from __future__ import annotations

import atexit
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _pair_cache  # noqa: E402

# The discard port, which only root may open: the endpoint of every stand-in
# run, so no request of a check reaches a model server, and the pair-class
# store identifies no server behind it.
CLOSED_ENDPOINT = "http://127.0.0.1:9/v1/chat/completions"
ENDPOINT_ENV = "PROOFREAD_ENDPOINT"


def private_pair_store() -> Path:
    """Point PAIR_CACHE_PATH at a store in a new temporary directory, removed
    when this process exits, drop PAIR_CACHE_MODEL_TAG, and point
    PROOFREAD_ENDPOINT at CLOSED_ENDPOINT.  Returns the store's path."""
    folder = Path(tempfile.mkdtemp(prefix="offline-pair-store-"))
    atexit.register(shutil.rmtree, folder, True)
    os.environ[_pair_cache.PATH_ENV] = str(folder / "pair-class.jsonl")
    os.environ.pop(_pair_cache.TAG_ENV, None)
    os.environ[ENDPOINT_ENV] = CLOSED_ENDPOINT
    return folder / "pair-class.jsonl"


PRIVATE_STORE = private_pair_store()
