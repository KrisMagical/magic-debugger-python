"""Import smoke tests for the GDB adapter and main entry module."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_gdb_adapter_importable():
    import adapters.gdb as gdb

    assert gdb.GDBAdapter is not None
    assert gdb.GDBConfig is not None
    assert gdb.check_gdb_installation is not None


def test_main_importable():
    import main

    assert main.MagicDebug is not None
