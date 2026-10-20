"""Firebase's rules (the pricing page read 2026-10-21, the Blaze plan). Realtime Database is priced by Firebase itself;
past their no-cost quotas, Cloud Firestore, Authentication and Cloud Storage are "Google Cloud pricing", which has no
bundled table (the generic rules and a person's price file price them)."""
from __future__ import annotations

from ..cost import formulas as F
from . import provider_rule

CHECKED = "2026-10-21"


def rtdb(h: F.Hour) -> list[F.Meter]:
    """Realtime Database: GB stored and GB downloaded (egress_gb: what the clients download, its subscriptions'
    updates among them). Simultaneous connections are a limit, not a charge."""
    out = F.stored(h)
    if "egress_gb" in h.q:
        out.append(F.Meter("download", h.q["egress_gb"], "GB", "download", "egress_gb"))
    return out


provider_rule("firebase/rtdb", "database.document", "firebase", "rtdb", rtdb, "https://firebase.google.com/pricing",
              CHECKED, reads=("storage_gb", "egress_gb", "requests"))
