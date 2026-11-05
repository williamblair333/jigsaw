"""Reports read from a decision log.

concordance: per game and kind of decision, how often the escalated rung agreed with the
cheap one. Where agreement is high, the gate can stop asking (the spec's 95% rule).

A row counts as *compared* when it escalated, a cheap rung had answered (cheap_choice is
set), and a higher rung then decided (its rung is above cheap_rung). Rows where no higher rung
answered, or where no cheap rung did (novelty), are escalations but can't be compared.
"""

from collections import defaultdict

from pydantic import BaseModel

from jigsaw.decision_log import DecisionLog


class ConcordanceRow(BaseModel):
    game: str
    kind: str
    decisions: int
    escalated: int
    compared: int
    agreed: int

    @property
    def agreement(self) -> float | None:
        """agreed / compared, or None when nothing could be compared."""
        return self.agreed / self.compared if self.compared else None


def concordance(log: DecisionLog, game: str | None = None) -> list[ConcordanceRow]:
    counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for d in log.query(game=game):
        c = counts[(d.game, d.kind)]
        c[0] += 1
        if not d.escalated_because:
            continue
        c[1] += 1
        if d.cheap_choice is not None and d.cheap_rung is not None and d.rung > d.cheap_rung:
            c[2] += 1
            c[3] += d.choice == d.cheap_choice
    return [
        ConcordanceRow(game=g, kind=k, decisions=n, escalated=e, compared=cmp, agreed=a)
        for (g, k), (n, e, cmp, a) in sorted(counts.items())
    ]


def concordance_table(rows: list[ConcordanceRow]) -> str:
    header = ["game", "kind", "decisions", "escalated", "compared", "agreed", "agreement"]
    body = [
        [r.game, r.kind, str(r.decisions), str(r.escalated), str(r.compared), str(r.agreed),
         "-" if r.agreement is None else f"{r.agreement:.0%}"]
        for r in rows
    ]
    widths = [max(len(row[i]) for row in [header, *body]) for i in range(len(header))]
    return "\n".join("  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip()
                     for row in [header, *body])
