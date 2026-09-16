"""Database-free fictional signed Power and versioned domain contract tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.card import CardDetail
from importer.execution_design.materializer import PayloadContent
from importer.projection.domain import project_printings
from importer.projection.projector import validate_fragment
from importer.schemas import ImportCard
from importer.staging.domain import PrintingFingerprint, PrintingRecord, validate_printings
from importer.staging.models import CardFields
from tests.test_execution_design import context as execution_context
from tests.test_execution_design import prepare


@pytest.mark.parametrize("power", [-1, -19, -2147483648, 2147483647])
def test_signed_power_all_internal_layers(power):
    assert ImportCard(id="fictional", number="1", name="Fictional", power=power).power == power
    assert CardFields(power={"state": "VALUE", "value": power}).power.value == power
    validate_fragment("cards", {"power": power})
    ctx = execution_context.__wrapped__()
    for r in ctx["inputs"]:
        r["card"]["power"] = {"state": "VALUE", "value": power}
    result = prepare(ctx)
    assert result.technically_eligible, result.blocking_reasons
    materialized = PayloadContent.model_validate_json(result.candidate.payload.content_json)
    assert next(e for e in materialized.entities if e.kind == "cards").values["power"] == power
    assert not result.production_execution_authorized


@pytest.mark.parametrize("power", [-2147483649, 2147483648, True, 1.5, "-1"])
def test_invalid_power_rejected(power):
    with pytest.raises(ValidationError):
        ImportCard(id="fictional", number="1", name="Fictional", power=power)
    with pytest.raises(ValidationError):
        CardFields(power={"state": "VALUE", "value": power})
    with pytest.raises(ValueError):
        validate_fragment("cards", {"power": power})


def test_chakra_and_points_stay_nonnegative():
    with pytest.raises(ValidationError):
        ImportCard(id="fictional", number="1", name="Fictional", chakra=-1)
    with pytest.raises(ValidationError):
        CardFields(mission_points={"state": "VALUE", "value": -1})


def domain_record(**overrides):
    values = {
        "record_key": "fictional",
        "identity": {
            "expansion": "Ember",
            "edition": None,
            "printed_identifier": "01/99",
            "rarity": "Bright",
            "variant": None,
            "card_version": "V1",
            "stamp": None,
        },
        "language": "EN",
        "source": {
            "name": "Fictional",
            "retrieved_at": datetime(2026, 1, 1, tzinfo=UTC),
            "authority": "OFFICIAL_AUTHORITATIVE",
        },
        "review_status": "APPROVED",
        "title": {"state": "VALUE", "value": "Ember Scout"},
    }
    values.update(overrides)
    return PrintingRecord.model_validate(values)


def test_domain_identity_provenance_language_and_sparse_preview():
    one = domain_record()
    other = domain_record(language="FR", source_uid="changed", source_sku="changed")
    assert one.identity.key().analysis_public_id() == other.identity.key().analysis_public_id()
    assert one.identity.key().analysis_public_id().startswith("prn_")
    preview = project_printings(
        [
            domain_record(
                rules_text={"state": "CLEAR", "approval_reference": "fictional-review"}, points=None
            )
        ]
    )
    assert preview.patches["fictional"]["rules_text"].approval_reference == "fictional-review"
    assert preview.patches["fictional"]["points"].state == "UNKNOWN"
    assert not preview.production_execution_authorized


def test_future_grouping_conflicts_quarantine():
    first = domain_record()
    second = domain_record(
        record_key="other", title={"state": "VALUE", "value": "Different Concept"}
    )
    second.identity.stamp = "Event"
    result = validate_printings([first, second])
    assert not result.accepted
    assert all("CARD_GROUPING_CONFLICT" in r for r in result.quarantined.values())


def test_api_response_schema_is_still_signed():
    assert "minimum" not in str(CardDetail.model_json_schema()["properties"]["power"])
    assert set(PrintingFingerprint.model_fields) == {
        "expansion",
        "edition",
        "printed_identifier",
        "rarity",
        "variant",
        "card_version",
        "stamp",
    }


def test_signed_power_v2_preview_and_legacy_execution_gate():
    record = domain_record(power={"state": "VALUE", "value": -1})
    projection = project_printings([record])
    assert projection.patches[record.record_key]["power"].value == -1
    ctx = execution_context.__wrapped__()
    from importer.projection.planner import build_plan

    plan = build_plan(**ctx)
    ctx["inputs"] = [record.model_dump(mode="json")]
    result = prepare(ctx, plan=plan)
    assert result.blocking_reasons == ("DOMAIN_V2_EXECUTION_NOT_SUPPORTED",)
    assert not result.production_execution_authorized


@pytest.mark.parametrize("field", ["chakra", "points"])
def test_v2_other_numeric_fields_not_relaxed(field):
    with pytest.raises(ValidationError):
        domain_record(**{field: {"state": "VALUE", "value": -1}})


@pytest.mark.parametrize("value", [-2147483649, 2147483648, True])
def test_v2_power_range_and_strictness(value):
    with pytest.raises(ValidationError):
        domain_record(power={"state": "VALUE", "value": value})


def test_version_two_cannot_rebind_registered_public_identity():
    from importer.staging.identity import Registry, canonical

    record = domain_record(existing_public_id="legacy-visible-id")
    assert (
        "EXISTING_ID_NOT_REGISTERED" in validate_printings([record]).quarantined[record.record_key]
    )
    registry = Registry({canonical(record.identity.key().payload()): "legacy-visible-id"})
    assert validate_printings([record], registry).accepted[record.record_key] == "legacy-visible-id"


def test_readonly_compatibility_preserves_signed_raw_observation():
    from importer.catalogue_design.models import SourceCardRecord
    from scripts.check_domain_compatibility import check_records, schema_record

    raw = {
        "Uid": 1,
        "SKU": "FICTIONAL-ONLY",
        "Set": "Ember",
        "ID": "01/99",
        "Rarity": "Bright",
        "CardType": "Attachment",
        "Title": "Fictional Weight",
        "Power": -1,
        "Chakra": 1,
        "Points": "",
        "CardVersion": "V1",
        "Langs": ["en"],
    }
    record = SourceCardRecord.from_raw(raw)
    value = schema_record(record, "en")
    assert value.power == -1 and value.points is None
    assert value.observation == raw and value.observation["Points"] == ""
    assert check_records([record])["SCHEMA_COMPATIBLE"] == 1
