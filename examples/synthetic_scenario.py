"""Original synthetic scenario; no provider observations or inferred completeness.

These declared complete populations are true only of this finite generated toy
universe. They certify no external feed. Numbers are inputs, not expected model
answers and not independent numerical acceptance fixtures.
"""
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import math

from option_feature_contracts import (
    ActivityWindow, CivilDateBinding, CoverageCertificate, Definition,
    Eligibility, InputBinding, ModelFact, Quote, QuoteCoverageWindow, Request,
    R25_LIMITS, Snapshot, SolverConfig, Spot, Trade,
)

YEAR_NS = 31536000000000000
OUTPUTS = ("contract.dte", "contract.moneyness", "contract.multiplier",
           "liquidity.spread_bps", "quality.quote_coverage", "greeks.delta",
           "greeks.gamma", "volatility.implied_volatility", "chain.activity")


def scenario(variant: str = "complete") -> tuple[Snapshot, Request]:
    if variant not in ("complete", "unsupported", "missing_spot", "future_spot", "partial_quotes"):
        raise ValueError("Unknown closed synthetic scenario")
    # Adapter-side source evidence binds the exact original generator source
    # plus selected variant, independently of canonical snapshot hashing.
    source_digest = sha256(Path(__file__).read_bytes() + b"\nvariant=" + variant.encode()).hexdigest()
    binding = InputBinding("synthetic", "original-r25-worker-demo", "1-" + variant,
                           source_digest,
                           "synthetic", "original-r25-worker-demo1")
    definition = Definition(
        contract_id="TOY-CALL", underlying_id="TOY-UNDERLYING", right="call",
        strike=Decimal("100"), currency="USD", multiplier=Decimal("100"),
        deliverable="scalar_underlying", action_basis_id="toy-unadjusted1",
        exercise="american" if variant == "unsupported" else "european",
        model_profile_admission="certified_vanilla_continuous_carry",
        settlement="cash", last_trade_ns=YEAR_NS + 10, fixing_ns=YEAR_NS + 10,
        payment_ns=YEAR_NS + 10, expiry_ordinal=719528, timezone_id="Etc/UTC",
        civil_binding_id="toy-civil1", revision_id="1", effective_from_ns=0,
        effective_to_ns=None, known_at_ns=0, input_binding_id="synthetic")
    spot = Spot("TOY-UNDERLYING", Decimal("100"), "USD", "toy-unadjusted1",
                9, 11 if variant == "future_spot" else 9, "1", "synthetic")
    facts = tuple(ModelFact("TOY-UNDERLYING", None, kind, value, "option-bsm1", "USD",
                            "toy-unadjusted1", 0, None, 0, "1", "synthetic")
                  for kind, value in (("rate", 0.02), ("carry", 0.01), ("volatility", 0.2)))
    quotes = (Quote("TOY-CALL", "slot-1", Decimal("8"), Decimal("9"), "USD",
                    "per_underlying_payoff_unit", 8, 8, 0, "1", "synthetic"),
              Quote("TOY-CALL", "slot-2", Decimal("8.1"), Decimal("9.1"), "USD",
                    "per_underlying_payoff_unit", 9, 9, 0, "1", "synthetic"))
    if variant == "partial_quotes":
        quotes = quotes[:1]
    certificates = (
        CoverageCertificate("samples", "quote_samples", ("TOY-CALL",), 0, 10, 10, True, "synthetic"),
        CoverageCertificate("trades", "trade_events", ("TOY-CALL",), 0, 10, 10, True, "synthetic"),
        CoverageCertificate("current", "current_quotes", ("TOY-CALL",), 10, 10, 10, True, "synthetic"),
    )
    snapshot = Snapshot(
        "option-canonical1", (binding,),
        (CivilDateBinding("toy-civil1", 10, 719163, "Etc/UTC", 0, "synthetic"),
         CivilDateBinding("toy-civil1", YEAR_NS + 10, 719528, "Etc/UTC", 0, "synthetic")),
        (definition,), () if variant == "missing_spot" else (spot,), facts, quotes, (),
        (Trade("toy-trade", "TOY-CALL", Decimal("1"), "contracts", "regular", 8, 8, "1", "synthetic"),),
        certificates,
        (QuoteCoverageWindow("TOY-CALL", 10, 0, 10, ("slot-1", "slot-2"), "toy-slots1", "samples", "synthetic"),),
        ActivityWindow("toy-population1", "TOY-UNDERLYING", ("TOY-CALL",), 10, 0, 10,
                       ("toy-trade",), "toy-regular1", "trades", "current", "synthetic"))
    request = Request(
        "option-request1", ("TOY-CALL",), OUTPUTS, "computed_only", "exact_only",
        10, 10, 719163, "toy-civil1", "option-bsm1", "r25-formulas1",
        Eligibility(10, 10, 10),
        SolverConfig("bisection1", "midpoint", 4.0, 256, 1e-10, 1e-10, 1e-10, 1e-10),
        R25_LIMITS)
    return snapshot, request


def assert_scenario_results(variant: str, results: tuple) -> None:
    """Independent finite-scenario semantic checks, not a pricing oracle.

    These expectations derive from the declared toy inputs and frozen profile,
    never from another call to production evaluation. Broad model sign/range
    assertions detect unavailable output, not independent numerical accuracy.
    """
    rows = {row.output_id: row for row in results}
    if set(rows) != set(OUTPUTS) or len(results) != len(OUTPUTS):
        raise AssertionError("Synthetic scenario did not return the exact nine outputs")
    model_outputs = ("greeks.delta", "greeks.gamma", "volatility.implied_volatility")
    missing_affected = ("contract.moneyness",) + model_outputs
    expected_unavailable = (model_outputs if variant == "unsupported" else
                            missing_affected if variant in ("missing_spot", "future_spot") else ())
    for name, row in rows.items():
        if name in expected_unavailable:
            status, reason = ({"unsupported": ("unsupported_profile", "unsupported_exercise"),
                               "missing_spot": ("missing_input", "missing_spot"),
                               "future_spot": ("ineligible_input", "future_known")}[variant])
            if (row.status, row.reason, row.value) != (status, reason, None):
                raise AssertionError(f"{variant}/{name}: wrong unavailable semantics")
        elif row.status != "available" or row.reason != "ok" or row.value is None or not math.isfinite(row.value):
            raise AssertionError(f"{variant}/{name}: expected a finite available value")
    for name, value in (("contract.dte", 365.0), ("contract.multiplier", 100.0),
                        ("chain.activity", 100.0)):
        if rows[name].value != value:
            raise AssertionError(f"{variant}/{name}: finite-scenario value differs")
    if "contract.moneyness" not in expected_unavailable and rows["contract.moneyness"].value != 1.0:
        raise AssertionError("Equal strike/spot must yield unit moneyness")
    coverage = rows["quality.quote_coverage"]
    expected_observed = 1 if variant == "partial_quotes" else 2
    expected_ratio = 0.5 if variant == "partial_quotes" else 1.0
    if (coverage.value != expected_ratio or coverage.coverage is None
            or coverage.coverage.observed != expected_observed or coverage.coverage.expected != 2
            or coverage.coverage.population_complete is not True
            or coverage.coverage.sampling != "event_count"):
        raise AssertionError("Declared sampling population coverage semantics differ")
    if ("partial_quote_coverage" in coverage.quality_flags) != (variant == "partial_quotes"):
        raise AssertionError("Partial quote coverage flag differs from declared missing slot")
    if not expected_unavailable:
        delta, gamma, iv = (rows[name] for name in model_outputs)
        if not (0.0 < delta.value < 1.0 and gamma.value > 0.0 and 0.0 < iv.value < 4.0):
            raise AssertionError("Admitted positive-time vanilla model output signs/ranges differ")
        if any(row.origin != "computed" or row.model_id != "option-bsm1" for row in (delta, gamma, iv)):
            raise AssertionError("Model output provenance is not admitted computed BSM")
        if delta.pricing_evidence is None or gamma.pricing_evidence is None:
            raise AssertionError("Available model Greeks lack required price-enclosure evidence")
        if iv.solver_evidence is None or iv.solver_evidence.converged is not True:
            raise AssertionError("Available synthetic IV lacks converged solver evidence")
