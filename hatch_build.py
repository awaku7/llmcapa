"""Generate the SQLite catalog when building a distributable wheel."""

import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if version == "editable":
            # Development installs still use the source JSON catalogs.
            return

        root = Path(self.root)
        sys.path.insert(0, str(root / "src"))
        try:
            from llmcapa._catalog_db import build_catalog

            database = root / "build" / "llmcapa-catalog" / "catalog.sqlite3"
            build_catalog(database)
        finally:
            sys.path.pop(0)

        build_data["force_include"][str(database)] = "llmcapa/data/catalog.sqlite3"
