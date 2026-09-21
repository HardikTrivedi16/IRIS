"""IRIS <-> NetworkX Dependency & Workflow Graph Engine integration.

This package is the ONLY code in the IRIS backend that imports
``dependency_engine`` (the vendored, unmodified NetworkX package — see
``backend/dependency_engine/``). Routers must go through
``app.graph.service``, never import ``dependency_engine`` directly, so the
raw-object boundary stays enforced in one place.
"""
