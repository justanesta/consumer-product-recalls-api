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
    "Recall severity/hazard classification in the source's NATIVE vocabulary (FDA: 1/2/3, NC=Not "
    "Yet Classified; USDA: Class I/II/III, Public Health Alert; USCG: H/L/M/S). NOT normalized "
    "across sources. ⚠ USCG's H/L/M/S are passed through verbatim from the USCG directory; their "
    "official severity semantics are NOT publicly documented (the public USCG recall index exposes "
    "no severity; 33 CFR 179 defines none) — do NOT assume an ordered scale. Provisional working "
    "assumption (pending USCG confirmation): H/M/L ≈ High/Medium/Low; S unverified. Sources: FDA, "
    "USDA, USCG (null for CPSC/NHTSA)."
)
