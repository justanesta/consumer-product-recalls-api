"""Cross-module field descriptions — the single source of truth for caveats that would otherwise
drift across response models.

``classification`` is documented identically on ``RecallSummary``/``RecallDetail`` (recalls),
``ProductSearchHit`` (products), and ``ClassificationCount`` (stats). Keeping the string here means
the USCG ``H/L/M/S`` honesty caveat (and any future edit) lives in exactly one place instead of
three copies that already disagreed.
"""

from __future__ import annotations

# The USCG H/L/M/S codes are passed through verbatim, but their official severity meaning is NOT
# publicly documented (the public USCG recall index exposes no severity column, and 33 CFR 179 —
# the recall regulation — defines no such taxonomy). The caveat below keeps programmatic consumers
# from treating them as a confirmed ordered scale; it mirrors the tone on UscgManufacturer.status.
D_CLASSIFICATION = (
    "Recall severity in each agency's own scale (FDA: 1/2/3, NC = Not Yet Classified; USDA: Class "
    "I/II/III, Public Health Alert; USCG: H/L/M/S). Not comparable across agencies. ⚠ USCG's "
    "H/L/M/S are passed through from the USCG directory, but their official meaning is not "
    "publicly documented (the public USCG recall index shows no severity, and 33 CFR 179 defines "
    "none), so do not assume an ordered scale. Best current guess, pending confirmation from USCG: "
    "H/M/L roughly map to High/Medium/Low, and S is unverified. Sources: FDA, USDA, USCG (null for "
    "CPSC/NHTSA)."
)
