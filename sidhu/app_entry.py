"""Absolute-import entry point for PyInstaller."""
from sidhu.app import main

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
