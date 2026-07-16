from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict[str, object]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_withdrawn_five_colorset_template_can_never_claim_acceptance() -> None:
    manifest = _json(
        "examples/project_templates/irena30/openmc2donjon.project.json"
    )
    decision = _json(
        "examples/project_templates/irena30/acceptance/decision.json"
    )

    assert "withdrawn" in str(manifest["name"]).lower()
    assert manifest["template"] == "irena30-colorset-core"
    assert "withdrawn-diagnostic" in str(manifest["workflow"])
    assert manifest["lifecycle"] == "withdrawn-diagnostic"
    consumer = manifest["consumer"]
    assert isinstance(consumer, dict)
    assert "mode=irena30-colorset-core" in str(consumer["href"])
    assert "mode=irena30-component-core" not in str(consumer["href"])

    assert decision["status"] == "rejected"
    criteria = decision["criteria"]
    assert isinstance(criteria, list) and criteria
    assert all(row["status"] == "failed" for row in criteria)
    assert "cannot establish" in str(decision["summary"])


def test_strict_fullcore_template_has_a_real_hold_decision() -> None:
    manifest = _json(
        "examples/project_templates/irena30_fullcore/openmc2donjon.project.json"
    )
    decision = _json(
        "examples/project_templates/irena30_fullcore/acceptance/decision.json"
    )

    assert manifest["template"] == "irena30-fullcore-physical"
    acceptance = manifest["acceptance"]
    assert acceptance["decision"] == "acceptance/decision.json"
    assert acceptance["validator"] == {
        "contract": "irena30-orbit-fullcore-v1",
        "summary": "fullcore/handoff/fullcore_validation.json",
        "component": "fullcore",
    }
    components = manifest["components"]
    assert isinstance(components, list) and len(components) == 1
    assert "identity" not in components[0]
    assert components[0]["metadata"]["node_side_cm"] == 17.5 / (3.0**0.5)
    assert decision["status"] == "pending"
    assert "HOLD" in str(decision["summary"])
    assert "no accepted IRENA" in str(decision["summary"])
    criteria = decision["criteria"]
    assert isinstance(criteria, list) and len(criteria) == 4
    assert all(row["status"] == "pending" for row in criteria)


def test_withdrawn_colorset_runner_and_summary_cannot_emit_acceptance() -> None:
    runner = (
        ROOT
        / "examples/irena30_sph_stage2_csd/run_physical_closure.sh"
    ).read_text(encoding="utf-8")
    summary = (
        ROOT
        / "examples/irena30_sph_stage2_csd/summarize_physical_closure.py"
    ).read_text(encoding="utf-8")

    assert "OPENMC2DONJON_ALLOW_WITHDRAWN_COLORSET_DIAGNOSTIC" in runner
    assert '!= "1"' in runner
    assert "--production" not in runner
    assert "--require-physical-sph" not in runner
    assert "accepted physical closure" not in runner.lower()
    assert '"decision": "withdrawn_diagnostic_rejected"' in summary
    assert '"physics_accepted": False' in summary
    assert '"production_ready": False' in summary
    assert '"decision": "accepted"' not in summary


def test_product_docs_name_the_current_irena_domain_route() -> None:
    handoff = (ROOT / "docs/HANDOFF_SNAPSHOT.md").read_text(encoding="utf-8")
    product = (ROOT / "docs/PRODUCT_MODEL.md").read_text(encoding="utf-8")
    fast = (ROOT / "docs/FAST_SPECTRUM_WORKFLOW.md").read_text(encoding="utf-8")
    stage3 = (
        ROOT / "examples/irena30_sph_stage3_fullcore/README.md"
    ).read_text(encoding="utf-8")

    for text in (handoff, product, fast, stage3):
        assert "91 independent" in text
        assert "21 exact" in text
    assert "91-position, five-component DONJON core" not in handoff
    assert "production correction is generated one seven-assembly colorset" not in stage3
    assert "withdrawn" in stage3.lower()


def test_archived_stage3_cannot_emit_physics_acceptance() -> None:
    comparison = (
        ROOT / "examples/irena30_sph_stage3_fullcore/compare_keff.py"
    ).read_text(encoding="utf-8")
    runner = (
        ROOT / "examples/irena30_sph_stage3_fullcore/run_stage3.sh"
    ).read_text(encoding="utf-8")

    assert 'summary["stage3_accepted"] = False' in comparison
    assert '"physics_accepted": False' in comparison
    assert 'status = "ACCEPTED"' not in comparison
    assert "WITHDRAWN / REJECTED" in comparison
    assert "ALLOW_REJECTED_FULLCORE_SPH" in runner
    assert "closure and acceptance decision" not in runner
