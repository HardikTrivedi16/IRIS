"""IRIS-side wiring around the vendored AI/document-intelligence module
(``app.modules.ai`` — copied unmodified from the AI subsystem delivery).

Mirrors the pattern used for the NetworkX integration (see ``app/graph/``):
this package is the only code that should call into ``app.modules.ai``
from a router; it is responsible for keeping AI output non-authoritative
(confidence/provenance always preserved, human-review flags always
surfaced) as it crosses into the rest of the IRIS backend.
"""
