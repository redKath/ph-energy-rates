from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from ph_energy_data.config import Settings
from ph_energy_data.domain.enums import RateStatus
from ph_energy_data.domain.models import ExtractedRate


class Verdict(StrEnum):
    PASS = "pass"
    FLAG = "flag"
    REJECT = "reject"


@dataclass(frozen=True)
class RuleResult:
    verdict: Verdict
    code: str | None = None


@dataclass(frozen=True)
class Context:
    settings: Settings
    previous_rate: Decimal | None = None


Rule = Callable[[ExtractedRate, Context], RuleResult]

_PASS = RuleResult(Verdict.PASS)


def rate_in_range(rate: ExtractedRate, ctx: Context) -> RuleResult:
    if ctx.settings.rate_min <= rate.rate_per_kwh <= ctx.settings.rate_max:
        return _PASS
    return RuleResult(Verdict.REJECT, "rate_out_of_range")


def month_over_month_change(rate: ExtractedRate, ctx: Context) -> RuleResult:
    if not ctx.previous_rate:
        return _PASS
    change = abs(rate.rate_per_kwh - ctx.previous_rate) / ctx.previous_rate
    if change > ctx.settings.mom_change_threshold:
        return RuleResult(Verdict.FLAG, "mom_change_exceeds_threshold")
    return _PASS


def generation_below_total(rate: ExtractedRate, ctx: Context) -> RuleResult:
    generation = rate.generation_charge_per_kwh
    if generation is not None and generation >= rate.rate_per_kwh:
        return RuleResult(Verdict.REJECT, "generation_not_below_total")
    return _PASS


def confidence_above_minimum(rate: ExtractedRate, ctx: Context) -> RuleResult:
    if rate.confidence is not None and rate.confidence < ctx.settings.confidence_min:
        return RuleResult(Verdict.FLAG, "low_confidence")
    return _PASS


RULES: list[Rule] = [
    rate_in_range,
    month_over_month_change,
    generation_below_total,
    confidence_above_minimum,
]


def validate(rate: ExtractedRate, ctx: Context) -> tuple[RateStatus, list[str]]:
    results = [rule(rate, ctx) for rule in RULES]
    codes = [r.code for r in results if r.code is not None]
    if any(r.verdict is Verdict.REJECT for r in results):
        return RateStatus.REJECTED, codes
    if any(r.verdict is Verdict.FLAG for r in results):
        return RateStatus.FLAGGED, codes
    return RateStatus.PUBLISHED, codes
