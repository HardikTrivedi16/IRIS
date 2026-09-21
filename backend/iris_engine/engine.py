"""
Top-level Engine facade (Phase 7 §2).

Usage:
    ds = RegulatoryDataset.load("regulatory-data")
    engine = Engine(ds)
    decision = engine.evaluate_requirement(
        project_id="PROJ-TEST-001",
        requirement_id="REQ-0004",
        project_facts={"project.industry": "FOOD", ...},
        evaluation_mode=EvaluationMode.NON_PRODUCTION,  # all Rule Versions are DRAFT today
    )
"""
from __future__ import annotations

from .loader import RegulatoryDataset
from .rules import EvaluationMode
from .decision import build_requirement_decision


class Engine:
    def __init__(self, dataset: RegulatoryDataset):
        self.dataset = dataset

    def evaluate_requirement(
        self,
        project_id: str,
        requirement_id: str,
        project_facts: dict,
        evaluation_mode: EvaluationMode = EvaluationMode.PRODUCTION,
        evaluated_at: str | None = None,
    ) -> dict:
        return build_requirement_decision(
            project_id=project_id,
            requirement_id=requirement_id,
            dataset=self.dataset,
            project_facts=project_facts,
            evaluation_mode=evaluation_mode,
            evaluated_at=evaluated_at,
        )

    def evaluate_all_requirements(
        self,
        project_id: str,
        project_facts: dict,
        evaluation_mode: EvaluationMode = EvaluationMode.PRODUCTION,
        evaluated_at: str | None = None,
    ) -> list:
        return [
            self.evaluate_requirement(
                project_id, req_id, project_facts, evaluation_mode, evaluated_at
            )
            for req_id in self.dataset.requirements
        ]
