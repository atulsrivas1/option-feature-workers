"""R26 option-flow-variants1 worker layer: checkpoint lifecycle and run translation.

Consumes the pure evaluator (option_features.variants1) and the shared record
canonicalisation (option_feature_contracts.variants1). Storage is the
VariantDuckDBSink in the storage module; no codec from the I/O package is used.
"""
from .errors import VariantWorkerError
from .checkpoint import make_checkpoint, validate_restore
from .run import run_batch, run_restore

__all__ = ["VariantWorkerError", "make_checkpoint", "validate_restore", "run_batch", "run_restore"]
