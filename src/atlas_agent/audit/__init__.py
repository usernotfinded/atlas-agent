# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    audit/__init__.py
# PURPOSE: Public surface of the audit domain: write events, verify them later.
#          The hashing internals (chain, manifest) stay private — callers must not
#          be able to compute their own event hashes.
# DEPS:    audit.models, audit.writer, audit.verify
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.audit.models import AuditEvent, AuditEventType, VerificationResult, AuditManifest, ManifestVerificationResult
from atlas_agent.audit.verify import verify_audit_log, verify_run_manifest
from atlas_agent.audit.writer import AuditWriter


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = [
    "AuditEvent",
    "AuditEventType",
    "AuditWriter",
    "VerificationResult",
    "AuditManifest",
    "ManifestVerificationResult",
    "verify_audit_log",
    "verify_run_manifest",
]
