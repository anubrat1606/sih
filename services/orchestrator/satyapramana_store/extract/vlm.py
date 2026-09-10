"""The vision stage, and its honest absence.

A scanned document with no text layer needs OCR to produce word boxes and a
model to classify the page. Neither is configured, so this stage reports that
plainly rather than guessing.

It follows the same shape as the verification adapters deliberately: a missing
capability is a registered thing that says NOT_CAPABLE, not an empty branch.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class StageUnavailable:
    stage: str
    reason: str


class UnconfiguredVisionStage:
    """Placeholder for SEGMENT and the candidate half of EXTRACT.

    Configure a provider and this is replaced, exactly as a verification
    adapter is. Until then a page with no text layer yields EXTRACTION_FAILED
    with a stated reason -- never a guessed field value, and never a plausible
    identifier invented to fill a gap.
    """

    stage_id = "vision@unconfigured"

    def available(self) -> bool:
        return bool(os.environ.get("SATYAPRAMANA_VLM_PROVIDER"))

    def segment(self, page) -> StageUnavailable:
        return StageUnavailable(
            "SEGMENT",
            "No vision provider configured (SATYAPRAMANA_VLM_PROVIDER unset). "
            "Page classification was not attempted.")

    def candidates(self, page) -> StageUnavailable:
        return StageUnavailable(
            "EXTRACT",
            "No vision provider configured (SATYAPRAMANA_VLM_PROVIDER unset). "
            "This page has no text layer, so no field could be read from it.")
