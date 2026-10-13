"""Independent examples and adversarial checks for the publication contract."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jinja2 import Environment

from ilmari_ui import cards as module
from ilmari_ui.cards import (
    MAX_CARD_BYTES,
    PublicationError,
    TimeSeriesCard,
    load_cards,
    validate_card,
)

NOW = datetime(2026, 10, 13, 12, tzinfo=UTC)


def metric(app_id: str = "public-app", card_id: str = "summary") -> dict:
    return {
        "schema_version": "ilmari.card.v1",
        "app_id": app_id,
        "card_id": card_id,
        "kind": "metric",
        "title": "Julkaistu yhteenveto",
        "data_class": "public",
        "published_at": "2026-10-13T11:05:00Z",
        "observed_until": "2026-10-13T11:00:00Z",
        "fresh_until": "2026-10-14T11:05:00Z",
        "source": {"name": "Hyväksytty julkaisu", "url": None},
        "units": "kpl",
        "data": {"value": 12, "note": None},
    }


def validate(payload: dict, *, allowed_hosts: frozenset[str] = frozenset()):
    return validate_card(
        json.dumps(payload).encode(),
        expected_app_id="public-app",
        expected_card_id="summary",
        expected_data_class="public",
        allowed_source_hosts=allowed_hosts,
    )


def publish(root: Path, payload: dict) -> Path:
    folder = root / payload["app_id"]
    folder.mkdir(parents=True, exist_ok=True)
    filename = folder / f"{payload['card_id']}.json"
    filename.write_text(json.dumps(payload), encoding="utf-8")
    return filename


def load(root: Path | None, **kwargs):
    return load_cards(root, app_classes={"public-app": "public"}, now=NOW, **kwargs)["public-app"]


def series() -> dict:
    value = metric()
    value["kind"] = "time_series"
    value["units"] = "kcal"
    value["data"] = {
        "period_start": "2026-10-11",
        "period_end": "2026-10-13",
        "points": [
            {"date": "2026-10-11", "value": 2100},
            {"date": "2026-10-13", "value": None},
        ],
    }
    return value


def ideas() -> dict:
    value = metric()
    value["kind"] = "idea_list"
    value["units"] = None
    value["data"] = {
        "ideas": [
            {
                "idea_id": f"idea-{number}",
                "title": f"Hypoteesi {number}",
                "problem": "Selvitettävä ongelma",
                "solution": "Ehdotettu ratkaisu",
                "assumption": "Testaamaton oletus",
                "next_experiment": "Haastattele mahdollista käyttäjää",
                "stage": "hypothesis",
                "risks": ["Tarpeesta ei ole vielä näyttöä"],
            }
            for number in range(1, 4)
        ]
    }
    return value


def recommendations() -> dict:
    value = metric()
    value["kind"] = "recommendation_list"
    value["units"] = None
    value["data"] = {
        "for_date": "2026-10-13",
        "criteria": ["Käyttäjän valitsema kasvisruoka"],
        "items": [
            {
                "title": "Esimerkkiruoka",
                "description": "Esimerkkidataa",
                "dietary_tags": ["kasvis"],
                "reason": "Julkaisijan ilmoittama perustelu",
                "source_url": None,
            }
        ],
    }
    return value


def updates() -> dict:
    value = metric()
    value["kind"] = "update_feed"
    value["units"] = None
    value["data"] = {
        "updates": [
            {
                "update_id": "update-one",
                "published_at": "2026-10-13T10:00:00+00:00",
                "title": "Nimenomaisesti jaettu päivitys",
                "summary": "Rajattu yhteenveto",
                "detail": None,
                "source_url": None,
            }
        ]
    }
    return value


@pytest.mark.parametrize("factory", [metric, series, ideas, recommendations, updates])
def test_all_five_kinds_have_a_typed_happy_path(factory):
    payload = factory()
    card = validate(payload)
    assert card.kind == payload["kind"]
    assert card.app_id == "public-app"
    assert card.published_at == datetime(2026, 10, 13, 11, 5, tzinfo=UTC)


@pytest.mark.parametrize("field", ["extra", "kind", "schema_version", "title", "source", "units"])
def test_unknown_fields_types_and_versions_are_rejected(field):
    payload = metric()
    payload[field] = {"attacker": "value"}
    with pytest.raises(PublicationError):
        validate(payload)


@pytest.mark.parametrize("value", [True, False, "12", float("nan"), float("inf"), -float("inf"), 10**16])
def test_numeric_values_are_finite_real_numbers_not_coerced(value):
    payload = metric()
    payload["data"]["value"] = value
    with pytest.raises(PublicationError):
        validate(payload)


def test_null_is_preserved_and_missing_days_never_become_zero():
    card = validate(series())
    assert isinstance(card, TimeSeriesCard)
    assert card.data.observed_count == 1
    assert card.data.missing_count == 2
    assert [point.value for point in card.data.complete_points] == [2100, None, None]
    payload = metric()
    payload["data"]["value"] = None
    assert validate(payload).data.value is None


@pytest.mark.parametrize(
    "points",
    [
        [{"date": "2026-10-13", "value": True}],
        [{"date": "2026-10-13", "value": 1}, {"date": "2026-10-13", "value": 2}],
        [{"date": "2026-10-13", "value": 1}, {"date": "2026-10-11", "value": 2}],
        [{"date": "2026-10-10", "value": 1}],
        [{"date": "2026-10-14", "value": 1}],
        [{"date": "2026-10-13", "value": 1, "secret": "no"}],
    ],
)
def test_series_rejects_invalid_points(points):
    payload = series()
    payload["data"]["points"] = points
    with pytest.raises(PublicationError):
        validate(payload)


def test_series_limits_and_future_observation_dates():
    payload = series()
    payload["data"]["period_start"] = "2024-01-01"
    with pytest.raises(PublicationError):
        validate(payload)
    payload = series()
    payload["data"]["period_end"] = "2026-10-14"
    with pytest.raises(PublicationError):
        validate(payload)
    payload = series()
    payload["data"]["points"] *= 184
    with pytest.raises(PublicationError):
        validate(payload)


@pytest.mark.parametrize("count", [0, 1, 2, 4])
def test_idea_card_requires_exactly_three_ideas(count):
    payload = ideas()
    payload["data"]["ideas"] = (payload["data"]["ideas"] * 2)[:count]
    with pytest.raises(PublicationError):
        validate(payload)


def test_idea_ids_must_be_unique_and_unknown_nested_fields_rejected():
    payload = ideas()
    payload["data"]["ideas"][1]["idea_id"] = "idea-1"
    with pytest.raises(PublicationError):
        validate(payload)
    payload = metric()
    payload["data"]["sql_query"] = "select * from private"
    with pytest.raises(PublicationError):
        validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("published_at", "2026-10-13T11:05:00"),
        ("published_at", 1791889500),
        ("published_at", "2026-10-13"),
        ("published_at", "2026-10-13T10:00:00Z"),
        ("observed_until", "2026-10-13T12:00:00Z"),
        ("fresh_until", "2026-10-12T11:05:00Z"),
    ],
)
def test_timestamps_require_timezone_and_correct_order(field, value):
    payload = metric()
    payload[field] = value
    with pytest.raises(PublicationError):
        validate(payload)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "http://example.org/test",
        "https://user:password@example.org/test",
        "https://127.0.0.1/test",
        "https://localhost/test",
        "https://source.internal/test",
        "https://example.org:8443/test",
        "https://example.org/\nscript",
        "https://example.org\\@evil.org/test",
        "https://example.org.evil.org/test",
    ],
)
def test_unsafe_or_unapproved_urls_are_rejected(url):
    payload = metric()
    payload["source"]["url"] = url
    with pytest.raises(PublicationError):
        validate(payload, allowed_hosts=frozenset({"example.org"}))


def test_https_source_requires_exact_host_allowlist_including_nested_urls():
    payload = metric()
    payload["source"]["url"] = "https://example.org/reference"
    with pytest.raises(PublicationError):
        validate(payload)
    assert validate(payload, allowed_hosts=frozenset({"example.org"})).source.url.endswith("/reference")
    for factory, key in [(recommendations, "items"), (updates, "updates")]:
        payload = factory()
        payload["data"][key][0]["source_url"] = "https://evil.org/hidden"
        with pytest.raises(PublicationError):
            validate(payload, allowed_hosts=frozenset({"example.org"}))


def test_html_is_plain_untrusted_text_and_renderer_escapes_it():
    payload = metric()
    payload["title"] = '<img src=x onerror="alert(1)">'
    payload["data"]["note"] = "<script>fetch('https://evil.org')</script>"
    card = validate(payload)
    assert card.title == payload["title"]
    rendered = Environment(autoescape=True).from_string("{{ card.title }} {{ card.data.note }}").render(card=card)
    assert "<img" not in rendered and "<script" not in rendered
    assert "&lt;img" in rendered and "&lt;script" in rendered


@pytest.mark.parametrize("field,value", [("app_id", "other-app"), ("card_id", "other-card"), ("data_class", "private")])
def test_caller_owned_identity_and_class_cannot_be_forged(field, value):
    payload = metric()
    payload[field] = value
    with pytest.raises(PublicationError):
        validate(payload)


def test_restricted_publications_are_rejected_even_with_matching_class():
    payload = metric()
    payload["data_class"] = "restricted"
    with pytest.raises(PublicationError):
        validate_card(json.dumps(payload).encode(), expected_app_id="public-app", expected_card_id="summary", expected_data_class="restricted")


def test_duplicate_json_fields_invalid_json_and_oversize_are_rejected():
    for payload in [b'{"kind":"metric","kind":"idea_list"}', b"{not json", b"\xff", b" " * (MAX_CARD_BYTES + 1), b"[" * 1500]:
        with pytest.raises(PublicationError):
            validate_card(payload, expected_app_id="public-app", expected_card_id="summary", expected_data_class="public")


def test_bounded_text_and_required_null_fields():
    payload = metric()
    payload["title"] = "x" * 161
    with pytest.raises(PublicationError):
        validate(payload)
    payload = metric()
    del payload["data"]["note"]
    with pytest.raises(PublicationError):
        validate(payload)


def test_disconnected_missing_root_and_missing_app(tmp_path):
    assert load(None).status == "ei yhdistetty"
    assert load(tmp_path / "missing").status == "tietoa ei saatavilla"
    assert load(tmp_path).status == "tietoa ei saatavilla"
    (tmp_path / "public-app").mkdir()
    assert load(tmp_path).status == "tietoa ei saatavilla"


def test_fresh_stale_and_demo_states(tmp_path):
    payload = metric()
    publish(tmp_path, payload)
    assert load(tmp_path).status == "ajantasainen"
    payload["fresh_until"] = "2026-10-13T12:00:00Z"
    publish(tmp_path, payload)
    assert load(tmp_path).status == "vanhentunut"
    demo_state = load(tmp_path, demo=True)
    assert demo_state.status == "esimerkkidata"
    assert "DEMO – ESIMERKKIDATA" in demo_state.message


def test_null_observations_are_unavailable_with_metadata_preserved(tmp_path):
    payload = metric()
    payload["data"]["value"] = None
    publish(tmp_path, payload)
    state = load(tmp_path)
    assert state.status == "tietoa ei saatavilla"
    assert state.cards[0].data.value is None


def test_yesterdays_menu_never_becomes_todays_fact_and_uses_helsinki_date(tmp_path):
    payload = recommendations()
    payload["data"]["for_date"] = "2026-10-12"
    publish(tmp_path, payload)
    assert load(tmp_path).status == "vanhentunut"
    payload["data"]["for_date"] = "2026-10-14"
    publish(tmp_path, payload)
    state = load(tmp_path)
    assert state.status == "tietoa ei saatavilla" and state.cards == ()
    late_utc = datetime(2026, 10, 13, 22, tzinfo=UTC)
    state = load_cards(tmp_path, app_classes={"public-app": "public"}, now=late_utc)["public-app"]
    assert state.status == "ajantasainen"  # Helsinki is already on October 14.


def test_future_publication_and_naive_runtime_clock_rejected(tmp_path):
    payload = metric()
    payload["published_at"] = "2026-10-13T13:00:00Z"
    publish(tmp_path, payload)
    assert load(tmp_path).status == "virhe"
    with pytest.raises(ValueError):
        load_cards(tmp_path, app_classes={"public-app": "public"}, now=datetime(2026, 10, 13))


def test_one_bad_app_or_card_does_not_crash_other_apps(tmp_path):
    publish(tmp_path, metric())
    bad_folder = tmp_path / "bad-app"
    bad_folder.mkdir()
    (bad_folder / "summary.json").write_text("invalid")
    states = load_cards(tmp_path, app_classes={"public-app": "public", "bad-app": "public"}, now=NOW)
    assert states["public-app"].status == "ajantasainen"
    assert states["bad-app"].status == "virhe"
    (tmp_path / "public-app" / "broken.json").write_text("<script>alert('secret')</script>")
    state = load(tmp_path)
    assert state.status == "virhe" and len(state.cards) == 1 and state.rejected_count == 1
    assert "secret" not in state.message and str(tmp_path) not in state.message


def test_private_read_requires_explicit_app_consent_and_trusted_class(tmp_path, monkeypatch):
    payload = metric("private-app")
    payload["data_class"] = "private"
    publish(tmp_path, payload)
    original = module._read_card
    monkeypatch.setattr(module, "_read_card", lambda *_args: pytest.fail("denied app was read"))
    states = load_cards(tmp_path, app_classes={"private-app": "private", "restricted-app": "restricted"}, now=NOW)
    assert states["private-app"].status == "ei yhdistetty"
    assert states["restricted-app"].status == "ei yhdistetty"
    monkeypatch.setattr(module, "_read_card", original)
    states = load_cards(tmp_path, app_classes={"private-app": "private"}, allowed_private_apps=frozenset({"private-app"}), now=NOW)
    assert states["private-app"].status == "ajantasainen"
    payload["data_class"] = "public"
    publish(tmp_path, payload)
    states = load_cards(tmp_path, app_classes={"private-app": "private"}, allowed_private_apps=frozenset({"private-app"}), now=NOW)
    assert states["private-app"].status == "virhe"


@pytest.mark.parametrize("app_id", ["../outside", "/etc", "..", "invalid/name", "UPPERCASE", ""])
def test_configured_app_ids_cannot_traverse_paths(tmp_path, app_id):
    with pytest.raises(ValueError):
        load_cards(tmp_path, app_classes={app_id: "public"}, now=NOW)


def test_relative_root_is_not_implicitly_authorized():
    assert load(Path("relative")).status == "virhe"


def test_file_app_and_ancestor_symlinks_are_rejected(tmp_path):
    root = tmp_path / "published"
    payload = metric()
    filename = publish(root, payload)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    assert load(alias).status == "virhe"
    assert load(alias / "descendant").status == "virhe"
    filename.rename(root / "outside.json")
    filename.symlink_to(root / "outside.json")
    assert load(root).status == "virhe"
    filename.unlink()
    filename.write_text(json.dumps(payload))
    (root / "public-app").rename(root / "real-app")
    (root / "public-app").symlink_to(root / "real-app", target_is_directory=True)
    assert load(root).status == "virhe"


def test_special_files_and_hardlinks_are_rejected_without_blocking(tmp_path):
    folder = tmp_path / "public-app"
    folder.mkdir()
    os.mkfifo(folder / "summary.json")
    assert load(tmp_path).status == "virhe"
    (folder / "summary.json").unlink()
    filename = publish(tmp_path, metric())
    os.link(filename, tmp_path / "outside.json")
    assert load(tmp_path).status == "virhe"


def test_bad_filenames_and_app_count_limits(tmp_path):
    publish(tmp_path, metric())
    folder = tmp_path / "public-app"
    (folder / "BAD.json").write_text("{}")
    assert load(tmp_path).status == "virhe"
    (folder / "BAD.json").unlink()
    for number in range(8):
        publish(tmp_path, metric(card_id=f"card-{number}"))
    assert load(tmp_path).status == "virhe"


def test_oversize_file_is_rejected_without_full_read(tmp_path):
    filename = publish(tmp_path, metric())
    filename.write_bytes(b" " * (MAX_CARD_BYTES + 1))
    assert load(tmp_path).status == "virhe"


def test_directory_replacement_after_open_cannot_redirect_reader(tmp_path, monkeypatch):
    payload = metric()
    publish(tmp_path, payload)
    real_open = module.os.open
    swapped = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal swapped
        descriptor = real_open(path, flags, *args, **kwargs)
        if path == "public-app" and not swapped:
            swapped = True
            (tmp_path / "public-app").rename(tmp_path / "pinned-app")
            attacker = deepcopy(payload)
            attacker["data"]["value"] = 999
            publish(tmp_path, attacker)
        return descriptor

    monkeypatch.setattr(module.os, "open", racing_open)
    state = load(tmp_path)
    assert state.status == "ajantasainen"
    assert state.cards[0].data.value == 12


def test_file_replacement_after_open_cannot_redirect_reader(tmp_path, monkeypatch):
    filename = publish(tmp_path, metric())
    evil = tmp_path / "outside.json"
    attacker = metric()
    attacker["data"]["value"] = 999
    evil.write_text(json.dumps(attacker))
    real_open = module.os.open
    swapped = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal swapped
        descriptor = real_open(path, flags, *args, **kwargs)
        if path == "summary.json" and not swapped:
            swapped = True
            filename.rename(filename.with_suffix(".old"))
            filename.symlink_to(evil)
        return descriptor

    monkeypatch.setattr(module.os, "open", racing_open)
    state = load(tmp_path)
    assert state.status == "ajantasainen"
    assert state.cards[0].data.value == 12


@pytest.mark.parametrize("offset", ["+00:60", "+01:99", "-00:60", "+24:00"])
def test_invalid_timezone_offsets_are_not_normalized_into_valid_times(offset):
    payload = metric()
    payload["observed_until"] = "2026-10-13T12:00:00" + offset
    with pytest.raises(PublicationError):
        validate_card(
            json.dumps(payload).encode(), expected_app_id="public-app",
            expected_card_id="summary", expected_data_class="public",
        )
