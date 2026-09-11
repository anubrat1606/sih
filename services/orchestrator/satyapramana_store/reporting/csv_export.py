"""CSV export of a tender's bidder list -- the artifact an officer actually
takes somewhere: a spreadsheet, an email, a physical file.

`bidders_to_csv()` does no database work and no file I/O of its own -- it
returns CSV text, not a file; the caller decides what to do with it. Standard
library only (`csv` + `io.StringIO`), no new dependency.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Mapping

#: Column order. Kept obvious enough that opening the file in a spreadsheet
#: needs no explanation.
_COLUMNS = (
    "bidder_id", "risk_level", "compliance_score", "verification_coverage",
    "evidence_confidence", "collusion_flagged", "collusion_cluster_id",
)


def _cell(value: Any) -> Any:
    """A null metric renders as an empty cell -- never a fabricated 0 and
    never the string "None"/"null", the same honesty rule every other
    renderer in this codebase follows."""
    return "" if value is None else value


def bidders_to_csv(bidders: list[Mapping[str, Any]]) -> str:
    """`bidders` is exactly GET /tenders/{tender_id}/bidders's "bidders" list
    -- each element exactly what GET /bidders/{id} returns, the same shape
    dossier.py and tender_report.py both already consume."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_COLUMNS)
    for b in bidders:
        m = b["metrics"]
        c = b.get("collusion")
        flagged = bool(c and c.get("flagged"))
        writer.writerow([
            b["bidder_id"],
            b["risk"]["level"],
            _cell(m["compliance_score"]),
            _cell(m["verification_coverage"]),
            _cell(m["evidence_confidence"]),
            flagged,
            # An unflagged bidder's cluster id (a tracked-but-isolated node)
            # is not useful information for this export -- only a genuinely
            # flagged bidder's cluster is worth a column.
            c["cluster_id"] if flagged else "",
        ])
    return buf.getvalue()
