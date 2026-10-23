"""R26 option-flow-variants1 worker layer: checkpoint lifecycle and run translation.

Consumes the pure evaluator (option_features.variants1) and the strict codec
(option_feature_io.variants1). Storage and sink adapters are not part of this
module; a run that needs a sink is reported as not executed.
"""
from .errors import VariantWorkerError
from .checkpoint import make_checkpoint, validate_restore
from .run import run_batch, run_restore

__all__ = ["VariantWorkerError", "make_checkpoint", "validate_restore", "run_batch", "run_restore"]
