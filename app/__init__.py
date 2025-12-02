"""Flask app factory wrapper to keep run.py stable while modularizing.

This module exposes `create_app()` which loads the existing `app` instance
from the top-level `app.py` via importlib, avoiding name collisions with
this package named `app`.
"""

from typing import Any
import importlib.util
import os

def create_app() -> Any:
    # Resolve path to top-level app.py (legacy module with Flask instance `app`)
    base_dir = os.path.dirname(os.path.dirname(__file__))
    legacy_app_path = os.path.join(base_dir, "app.py")
    spec = importlib.util.spec_from_file_location("legacy_app", legacy_app_path)
    if spec is None or spec.loader is None:
        raise ImportError("No se pudo cargar el módulo legacy app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.app  # type: ignore[attr-defined]
    except AttributeError:
        raise ImportError("El módulo app.py no expone la instancia Flask 'app'")
