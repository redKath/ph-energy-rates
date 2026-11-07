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


def rate_in_range(rate: ExtractedRate, context: Context) -> RuleResult:
    if context.settings.rate_min <= rate.rate_per_kwh <= context.settings.rate_max:
        return _PASS
    return RuleResult(Verdict.REJECT, "rate_out_of_range")


def month_over_month_change(rate: ExtractedRate, context: Context) -> RuleResult:
    if not context.previous_rate:
        return _PASS
    change = abs(rate.rate_per_kwh - context.previous_rate) / context.previous_rate
    if change > context.settings.mom_change_threshold:
        return RuleResult(Verdict.FLAG, "mom_change_exceeds_threshold")
    return _PASS


def generation_below_total(rate: ExtractedRate, context: Context) -> RuleResult:
    generation = rate.generation_charge_per_kwh
    if generation is not None and generation >= rate.rate_per_kwh:
        return RuleResult(Verdict.REJECT, "generation_not_below_total")
    return _PASS


def confidence_above_minimum(rate: ExtractedRate, context: Context) -> RuleResult:
    if rate.confidence is not None and rate.confidence < context.settings.confidence_min:
        return RuleResult(Verdict.FLAG, "low_confidence")
    return _PASS


RULES: tuple[Rule, ...] = (
    rate_in_range,
    month_over_month_change,
    generation_below_total,
    confidence_above_minimum,
)


def validate(rate: ExtractedRate, context: Context) -> tuple[RateStatus, list[str]]:
    results = [rule(rate, context) for rule in RULES]
    codes = [result.code for result in results if result.code is not None]
    if any(result.verdict is Verdict.REJECT for result in results):
        return RateStatus.REJECTED, codes
    if any(result.verdict is Verdict.FLAG for result in results):
        return RateStatus.FLAGGED, codes
    return RateStatus.PUBLISHED, codes
