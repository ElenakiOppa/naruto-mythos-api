"""Offline Phase 12B tests. Every record and relationship is fictional."""

import ast
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from importer.staging import identity as identity_module
from importer.staging.identity import Registry, derived_public_id, printing_identity
from importer.staging.models import CardFields, Policy, Record, RightsState, State
from importer.staging.validator import validate_records

FIXTURE = Path(__file__).parent / "fixtures" / "staging-fictional.json"


@pytest.fixture
def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def policy(fixture):
    return Policy.model_validate(fixture["policy"])


@pytest.fixture
def record(fixture):
    return fixture["records"][0]


def codes(result):
    return {item.code for item in result.unresolved}


def public_id(record):
    return derived_public_id(printing_identity(Record.model_validate(record).identity))


def test_valid_fictional_fixture(fixture, policy):
    result = validate_records(fixture["records"], policy)
    assert result.accepted_record_count == 5
    assert result.unresolved_record_count == 0
    assert len({p.public_id for p in result.accepted}) == 5
    assert all(len(p.public_id) <= 64 for p in result.accepted)
    assert {w.code for w in result.warnings} == {"SOURCE_REVIEW_REQUIRED", "RIGHTS_NOT_CLEARED"}


def test_unknowns_are_not_defaults(record):
    record["identity"]["scope"].pop("language")
    r = Record.model_validate(record)
    assert r.identity.scope.language is None
    assert r.card.subtitle.state == State.UNKNOWN
    assert r.card.artist.state == State.ABSENT
    assert r.rarity.official_label.state == State.ABSENT
    assert r.rights.metadata == RightsState.UNKNOWN
    assert r.rights.text == RightsState.UNKNOWN
    assert r.rights.images == RightsState.UNKNOWN


@pytest.mark.parametrize(
    "field,value",
    [
        ("expansion", "glass-harbor"),
        ("edition", "second"),
        ("language", "FR"),
        ("territory", "island"),
    ],
)
def test_scope_dimensions_change_identity(record, field, value):
    original = public_id(record)
    record["identity"]["scope"][field] = value
    assert public_id(record) != original


@pytest.mark.parametrize("namespace", ["MISSION", "PROMO", "SPECIAL"])
def test_namespace_separation(record, namespace):
    original = public_id(record)
    record["identity"]["numbering_namespace"] = namespace
    assert public_id(record) != original


@pytest.mark.parametrize("number", ["1/100", "001/100 A", "M-001", "P-004", "075/100 A"])
def test_complete_number_preserved(record, number):
    original = public_id(record)
    record["identity"]["printed_identifier"] = number
    r = Record.model_validate(record)
    assert r.identity.printed_identifier == number
    assert public_id(record) != original


@pytest.mark.parametrize("mutation", ["name", "rarity", "source", "labels", "retrieved"])
def test_mutable_descriptions_never_change_id(record, mutation):
    original = public_id(record)
    if mutation == "name":
        record["card"]["name"]["value"] = "Moonlit Guardian"
    elif mutation == "rarity":
        record["rarity"] = {"official_label": {"state": "VALUE", "value": "Radiant"}}
    elif mutation == "source":
        record["source"]["url"] = "https://example.invalid/revised"
    elif mutation == "labels":
        record["expansion_label"] = "Renamed display label"
    else:
        record["source"]["retrieved_at"] = "2026-02-02T00:00:00Z"
    assert public_id(record) == original


def test_unicode_nfc_is_identity_normalization_only(record, policy):
    record["identity"]["printed_identifier"] = "P-é"
    other = copy.deepcopy(record)
    other["record_key"] = "decomposed"
    other["identity"]["printed_identifier"] = "P-e\u0301"
    assert public_id(record) == public_id(other)
    assert Record.model_validate(other).identity.printed_identifier == "P-e\u0301"
    result = validate_records([record, other], policy)
    assert result.accepted_record_count == 0
    assert result.unresolved_record_count == 2
    assert "DUPLICATE_IDENTITY" in codes(result)


def test_identity_does_not_casefold_numbers(record):
    record["identity"]["printed_identifier"] = "P-a"
    original = public_id(record)
    record["identity"]["printed_identifier"] = "P-A"
    assert public_id(record) != original


@pytest.mark.parametrize("number", [1, "", " 001/100", "001/100 "])
def test_lossy_or_empty_number_rejected(record, number):
    record["identity"]["printed_identifier"] = number
    with pytest.raises(ValidationError):
        Record.model_validate(record)


def test_duplicate_identity_quarantines_both(record, policy):
    other = copy.deepcopy(record)
    other["record_key"] = "duplicate"
    result = validate_records([record, other], policy)
    assert result.accepted_record_count == 0
    assert result.unresolved_record_count == 2
    assert len(result.duplicate_records) == 2


def test_public_id_collision_quarantines_both(fixture, policy, monkeypatch):
    monkeypatch.setattr(identity_module, "derived_public_id", lambda _: "cpr_forced_collision")
    result = validate_records(fixture["records"][:2], policy)
    assert result.accepted_record_count == 0
    assert len(result.identity_collisions) == 2


def test_collision_with_reserved_identity(record, policy):
    assigned = public_id(record)
    result = validate_records([record], policy, Registry({"unrelated-reserved-identity": assigned}))
    assert "PUBLIC_ID_COLLISION" in codes(result)
    assert result.accepted_record_count == 0


def test_existing_id_requires_explicit_registry(record, policy):
    record["existing_public_id"] = "legacy_card_17"
    assert "EXISTING_ID_NOT_REGISTERED" in codes(validate_records([record], policy))
    canonical = printing_identity(Record.model_validate(record).identity)
    result = validate_records([record], policy, Registry({canonical: "legacy_card_17"}))
    assert result.accepted[0].public_id == "legacy_card_17"


@pytest.mark.parametrize("invalid_id", ["bad id", ""])
def test_invalid_registry_id(record, policy, invalid_id):
    canonical = printing_identity(Record.model_validate(record).identity)
    result = validate_records([record], policy, Registry({canonical: invalid_id}))
    assert "INVALID_PUBLIC_ID" in codes(result)


@pytest.mark.parametrize("field", ["expansion", "edition", "language"])
def test_incomplete_scope_is_unresolved(record, policy, field):
    record["identity"]["scope"][field] = None
    result = validate_records([record], policy)
    assert "MISSING_IDENTITY" in codes(result)
    assert result.proposed_public_ids == []


def test_unnumbered_does_not_receive_fabricated_id(record, policy):
    record["identity"]["printed_identifier"] = None
    assert "MISSING_IDENTITY" in codes(validate_records([record], policy))
    with pytest.raises(ValueError):
        printing_identity(Record.model_validate(record).identity)


def test_namespace_extension_requires_policy(record, policy):
    record["identity"]["numbering_namespace"] = "EVENT"
    assert "UNKNOWN_NAMESPACE" in codes(validate_records([record], policy))
    extended = Policy.model_validate({**policy.model_dump(), "namespaces": ["EVENT"]})
    assert validate_records([record], extended).accepted_record_count == 1


def test_scope_cross_product_not_inferred(record, policy):
    record["identity"]["scope"].update(edition="second", language="FR")
    assert "UNAPPROVED_SCOPE" in codes(validate_records([record], policy))


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("missing", "UNRESOLVED_PARENT"),
        ("unverified", "UNVERIFIED_PARENT"),
        ("no_evidence", "UNVERIFIED_PARENT"),
        ("scope", "PARENT_IDENTITY_MISMATCH"),
        ("unsupported", "UNSUPPORTED_TREATMENT"),
        ("finish", "UNSUPPORTED_TREATMENT"),
    ],
)
def test_parent_relationship_gates(fixture, policy, mutation, expected):
    parent, variant = fixture["records"][0], fixture["records"][-1]
    t = variant["treatment"]
    if mutation == "missing":
        t["parent_record_key"] = "missing-parent"
    elif mutation == "unverified":
        t["equivalence"] = "UNKNOWN"
    elif mutation == "no_evidence":
        variant["field_evidence"] = {}
    elif mutation == "scope":
        variant["identity"]["scope"]["language"] = "FR"
    elif mutation == "unsupported":
        t["treatment_key"] = "unapproved"
    else:
        t["finish_key"] = "unapproved"
    result = validate_records([parent, variant], policy)
    assert expected in codes(result)
    assert result.accepted_record_count == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "Crystal Keeper"),
        ("subtitle", "Different role"),
        ("type", "Quest"),
        ("chakra", 9),
        ("power", 9),
        ("ability_text", "Fictional alternate effect."),
        ("faction", "Glass Circle"),
        ("mission_points", 2),
        ("mission_rank", "silver"),
    ],
)
def test_gameplay_changes_block_variant(fixture, policy, field, value):
    parent, variant = fixture["records"][0], fixture["records"][-1]
    variant["card"][field] = {"state": "VALUE", "value": value}
    result = validate_records([parent, variant], policy)
    assert codes(result) & {"GAMEPLAY_CONFLICT", "GAMEPLAY_UNVERIFIED"}
    assert result.accepted_record_count == 1


def test_variant_keyword_override_rejected(fixture, policy):
    fixture["records"][-1]["keywords"] = {"state": "VALUE", "value": []}
    assert "GAMEPLAY_CONFLICT" in codes(validate_records(fixture["records"], policy))


def test_variant_gameplay_clear_rejected(fixture, policy):
    fixture["records"][-1]["card"]["power"] = {
        "state": "CLEAR",
        "approval_reference": "fixture-review",
    }
    assert "GAMEPLAY_CONFLICT" in codes(validate_records(fixture["records"], policy))


def test_ambiguous_parent_and_duplicate_reference(fixture, policy):
    records = [fixture["records"][0], copy.deepcopy(fixture["records"][0]), fixture["records"][-1]]
    result = validate_records(records, policy)
    assert result.accepted_record_count == 0
    assert "DUPLICATE_RECORD_KEY" in codes(result)
    assert "UNRESOLVED_PARENT" in codes(result)


def test_parent_appearing_later_is_supported(fixture, policy):
    result = validate_records(list(reversed(fixture["records"])), policy)
    assert result.accepted_record_count == 5


def test_treatment_cannot_parent_treatment(fixture, policy):
    variant = fixture["records"][-1]
    variant["treatment"]["parent_record_key"] = variant["record_key"]
    assert "UNRESOLVED_PARENT" in codes(validate_records(fixture["records"], policy))


def test_duplicate_treatment_quarantined(fixture, policy):
    clone = copy.deepcopy(fixture["records"][-1])
    clone["record_key"] = "second-treatment-claim"
    result = validate_records([*fixture["records"], clone], policy)
    assert result.accepted_record_count == 4
    assert result.unresolved_record_count == 2


def test_final_collision_invalidates_parent_and_treatment(fixture, policy, monkeypatch):
    parent_id = public_id(fixture["records"][0])
    original = identity_module.derived_public_id
    monkeypatch.setattr(
        identity_module,
        "derived_public_id",
        lambda key: parent_id if '"kind":"TREATMENT"' in key else original(key),
    )
    result = validate_records([fixture["records"][0], fixture["records"][-1]], policy)
    assert result.accepted_record_count == 0
    assert "UNRESOLVED_PARENT" in codes(result)


def test_omission_null_clear_are_distinct_and_roundtrip():
    fields = CardFields.model_validate(
        {"subtitle": None, "power": {"state": "CLEAR", "approval_reference": "fictional-review-1"}}
    )
    assert fields.artist.state == State.ABSENT
    assert fields.subtitle.state == State.UNKNOWN
    assert fields.power.state == State.CLEAR
    assert fields.present_fields == ["subtitle", "power"]
    assert fields.explicit_clear_fields == ["power"]
    assert CardFields.model_validate_json(fields.model_dump_json()) == fields


@pytest.mark.parametrize(
    "field_state",
    [
        {"state": "ABSENT", "value": 2},
        {"state": "UNKNOWN", "value": 2},
        {"state": "CLEAR", "value": 2, "approval_reference": "review"},
        {"state": "CLEAR"},
        {"state": "CLEAR", "approval_reference": " "},
        {"state": "VALUE", "value": None},
        {"state": "VALUE", "value": True},
        {"state": "VALUE", "value": -1},
        {"state": "ABSENT", "approval_reference": "review"},
    ],
)
def test_contradictory_field_states_rejected(field_state):
    with pytest.raises(ValidationError):
        CardFields.model_validate({"power": field_state})


def test_required_name_cannot_clear():
    with pytest.raises(ValidationError):
        CardFields.model_validate({"name": {"state": "CLEAR", "approval_reference": "review"}})


def test_null_collections_are_unknown(record):
    record.update(keywords=None, images=None, availability=None, rarity={"official_label": None})
    r = Record.model_validate(record)
    assert all(getattr(r, k).state == State.UNKNOWN for k in ("keywords", "images", "availability"))
    assert r.rarity.official_label.state == State.UNKNOWN


@pytest.mark.parametrize(
    "field,value",
    [
        ("retrieved_at", "2026-01-01T00:00:00"),
        ("retrieved_at", "invalid"),
        ("name", ""),
        ("name", " "),
        ("authority", "TRUST_ME"),
        ("url", "file:///example"),
        ("url", "https://user:fictional@example.invalid/"),
        ("content_hash", "not-a-sha256"),
    ],
)
def test_malformed_source_is_quarantined_without_input_echo(record, policy, field, value):
    record["source"][field] = value
    result = validate_records([record], policy)
    assert codes(result) == {"MALFORMED_RECORD"}
    assert result.unresolved_record_count == 1
    assert "user:fictional" not in result.model_dump_json()


@pytest.mark.parametrize("target", ["evidence", "image", "image-source"])
def test_nested_credential_urls_rejected(record, policy, target):
    url = "https://user:fictional@example.invalid/"
    if target == "evidence":
        record["field_evidence"] = {"proof": {"source_url": url, "locator": "fixture"}}
    else:
        image = {"url": "https://example.invalid/image.png", "owner": "PRINTING", "type": "front"}
        image["url" if target == "image" else "source_url"] = url
        record["images"] = {"state": "VALUE", "value": [image]}
    assert "MALFORMED_RECORD" in codes(validate_records([record], policy))


@pytest.mark.parametrize("serial,total", [(False, 100), (None, 100), (True, 0), (True, -1)])
def test_serialization_inconsistent_rejected(fixture, policy, serial, total):
    variant = fixture["records"][-1]
    variant["treatment"].update(serial_numbered=serial, serial_total=total)
    assert "MALFORMED_RECORD" in codes(validate_records([variant], policy))


def test_serialization_unknown_preserved(fixture):
    variant = fixture["records"][-1]
    variant["treatment"].pop("serial_numbered")
    variant["treatment"].pop("serial_total")
    assert Record.model_validate(variant).treatment.serial_numbered is None


@pytest.mark.parametrize("status", ["UNREVIEWED", "REJECTED"])
def test_unapproved_record_quarantined(record, policy, status):
    record["review_status"] = status
    assert "UNRESOLVED_REVIEW" in codes(validate_records([record], policy))


def test_open_questions_quarantined(record, policy):
    record["unresolved_questions"] = ["Which fictional edition?"]
    assert "UNRESOLVED_REVIEW" in codes(validate_records([record], policy))


def test_validation_deterministic_nonmutating_and_roundtrip(fixture, policy):
    snapshot = copy.deepcopy(fixture)
    first = validate_records(fixture["records"], policy)
    second = validate_records(fixture["records"], policy)
    assert first.model_dump_json() == second.model_dump_json()
    serialized = [Record.model_validate(r).model_dump(mode="json") for r in fixture["records"]]
    assert validate_records(serialized, policy) == first
    assert fixture == snapshot


def test_invalid_model_copy_revalidated(record, policy):
    model = Record.model_validate(record).model_copy(update={"schema_version": "unsupported"})
    assert "MALFORMED_RECORD" in codes(validate_records([model], policy))


def test_empty_batch(policy):
    result = validate_records([], policy)
    assert result.accepted_record_count == result.unresolved_record_count == 0


def test_version_one_golden_id(record):
    assert public_id(record) == "cpr_0163f4296e1f8c26d917591445641d40cc7545114c11840d6029df8d"


def test_source_summary_preserves_revision_and_origin(fixture, policy):
    result = validate_records(fixture["records"], policy)
    assert result.source_summary[0].record_count == 5
    assert result.source_summary[0].source.revision == "fictional-1"
    assert str(result.source_summary[0].source.url) == "https://example.invalid/staging"


def test_wrong_image_owner_is_quarantined(record, policy):
    record["images"] = {
        "state": "VALUE",
        "value": [
            {"url": "https://example.invalid/fictional.png", "owner": "TREATMENT", "type": "front"}
        ],
    }
    assert "IMAGE_OWNER_MISMATCH" in codes(validate_records([record], policy))


@pytest.mark.parametrize(
    "dimension,value",
    [("treatment_key", "normal"), ("finish_key", "matte"), ("collector_number", "P-004")],
)
def test_treatment_dimensions_change_identity(fixture, policy, dimension, value):
    before = validate_records(fixture["records"], policy).accepted[-1].public_id
    fixture["records"][-1]["treatment"][dimension] = value
    after = validate_records(fixture["records"], policy).accepted[-1].public_id
    assert before != after


def test_serial_run_change_does_not_change_identity(fixture, policy):
    before = validate_records(fixture["records"], policy).accepted[-1].public_id
    fixture["records"][-1]["treatment"]["serial_total"] = 200
    after = validate_records(fixture["records"], policy).accepted[-1].public_id
    assert before == after


def test_staging_has_no_application_write_or_network_imports():
    root = Path(__file__).parents[1] / "importer" / "staging"
    forbidden = {"app", "sqlalchemy", "requests", "httpx", "urllib", "socket", "subprocess"}
    for file in root.glob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not {alias.name.split(".")[0] for alias in node.names} & forbidden
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden
                assert node.module not in {"importer.runner", "importer.planner"}
