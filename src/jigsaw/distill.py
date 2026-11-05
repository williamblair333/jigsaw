"""Distillation from logged holdings (STANDARDS idea holdings-for-distillation, spec section 7).

A model rung can attach a Holding to its verdict: "when the treasury is under 500, choose
spears". The log keeps it with the row it came from. holdings() reads them back, with that row
id as provenance. HoldingsDecider applies them as a rung-1 rule. evaluate_holdings() checks each
one against every logged decision of its kind: on how many it applies, and how often the
logged answer was the one it would have given. That is the idea's test: at least 5 holdings
that agree on 90%+ of the cases they match.

Spec section 7 says a distilled rule should run in shadow before it is promoted, and should be
judged on outcomes, not only on agreement. Run a HoldingsDecider in a Ladder with shadow_rate set
before trusting it.
"""

from collections.abc import Iterable

from pydantic import BaseModel

from jigsaw.decision_log import DecisionLog
from jigsaw.intent import Holding
from jigsaw.ladder import Request, Verdict

__all__ = ["Holding", "HoldingEval", "HoldingsDecider", "evaluate_holdings", "holdings"]


def holdings(log: DecisionLog, game: str | None = None, kind: str | None = None) -> list[Holding]:
    """Every logged holding, oldest first, with its kind and source row id."""
    found: list[Holding] = []
    for d in reversed(log.query(game=game, kind=kind)):
        if d.holding is None:
            continue
        h = Holding.model_validate(d.holding)
        found.append(h.model_copy(update={"kind": d.kind, "source_id": d.id}))
    return found


class HoldingsDecider:
    """A rung-1 rule made of holdings: the first one that matches the request answers.

    A holding matches when its kind is the request's kind (or empty), its conditions hold on
    request.context, and its choice is one of the request's options (when it has options).
    """

    def __init__(self, rules: Iterable[Holding], rung: int = 1) -> None:
        self.rules = list(rules)
        self.rung = rung

    def decide(self, req: Request) -> Verdict | None:
        names = {o.name for o in req.options}
        for h in self.rules:
            if h.kind and h.kind != req.kind:
                continue
            if names and h.choose not in names:
                continue
            if h.matches(req.context):
                source = f" from decision #{h.source_id}" if h.source_id is not None else ""
                return Verdict(choice=h.choose, rung=self.rung, reason=f"holding{source}")
        return None


class HoldingEval(BaseModel):
    holding: Holding
    matched: int
    agreed: int

    @property
    def agreement(self) -> float | None:
        return self.agreed / self.matched if self.matched else None


def evaluate_holdings(log: DecisionLog, game: str | None = None) -> list[HoldingEval]:
    """Each logged holding against every logged decision of its kind that stored its request."""
    rows = [d for d in log.query(game=game) if d.request is not None]
    results: list[HoldingEval] = []
    for h in holdings(log, game=game):
        matched = agreed = 0
        for d in rows:
            if d.kind != h.kind:
                continue
            req = Request.model_validate(d.request)
            if h.matches(req.context):
                matched += 1
                agreed += d.choice == h.choose
        results.append(HoldingEval(holding=h, matched=matched, agreed=agreed))
    return results


def holdings_table(evals: list[HoldingEval]) -> str:
    header = ["source", "kind", "choose", "when", "matched", "agreed", "agreement"]
    body = [
        [f"#{e.holding.source_id}", e.holding.kind, e.holding.choose,
         ",".join(f"{k}={v}" for k, v in e.holding.when.items()) or "(always)",
         str(e.matched), str(e.agreed),
         "-" if e.agreement is None else f"{e.agreement:.0%}"]
        for e in evals
    ]
    widths = [max(len(r[i]) for r in [header, *body]) for i in range(len(header))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()
                     for r in [header, *body])
