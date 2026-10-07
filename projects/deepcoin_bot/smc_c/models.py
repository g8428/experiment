"""Shared SMC-C research records; no exchange or legacy-bot dependencies."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class EntryIntent:
    strategy: str
    direction: int
    decision_bar: int
    limit_price: float
    stop_price: float
    targets: List[float]
    source: str
    lecture_refs: str
    tags: List[str] = field(default_factory=list)
    expires_bar: Optional[int] = None


@dataclass
class TradeResult:
    strategy: str
    direction: int
    signal_bar: int
    entry_bar: int
    exit_bar: int
    entry: float
    stop: float
    exit_price: float
    risk_fraction: float
    gross_r: float
    net_r: float
    fees_fraction: float
    exit_reason: str
    source: str
    lecture_refs: str
    tags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategySpec:
    id: str
    name: str
    lecture_refs: str
    category: str
    status: str  # mechanical, interpreted, context-only, or deferred
    assumptions: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RiskConfig:
    tick_size: float
    fee_per_side: float
    slippage_per_side: float
    partial_fraction: float = 0.5
    stop_first_on_tie: bool = True
    one_tick_buffer: bool = True
    max_one_trade_per_setup: bool = True
