"""Run the full pytest entry point only on an explicit, marked synthetic PG17.

Settings are configured before importing the app; .env is never read.
"""

import faulthandler
import os
import runpy
import sys

from scripts.v14_test_database import verified_test_url


def main():
    url = verified_test_url()
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["TUSHARE_TOKEN"] = "synthetic-business-tests"
    os.environ["LLM_ENABLED"] = "false"
    from app.core.config import Settings

    Settings.model_config = {**Settings.model_config, "env_file": None}
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.begin() as db:
            config = Config("alembic.ini")
            config.attributes["connection"] = db
            command.upgrade(config, "head")
    finally:
        engine.dispose()
    sys.argv = ["pytest", *sys.argv[1:]]
    faulthandler.dump_traceback_later(300, repeat=True)
    runpy.run_module("pytest", run_name="__main__")


if __name__ == "__main__":
    main()
