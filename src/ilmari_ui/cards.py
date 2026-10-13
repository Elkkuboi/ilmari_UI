"""Proposed, read-only ``ilmari.card.v1`` publication contract.

These files are summaries explicitly published for the Hub. This module never
fetches a source URL, loads a plugin, or reads an application's database.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, TypeAlias
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    TypeAdapter,
    ValidationError,
    model_validator,
)

MAX_CARD_BYTES = 65_536
MAX_CARDS_PER_APP = 8
MAX_DIRECTORY_ENTRIES = 32
MAX_POINTS = 366
HELSINKI = ZoneInfo("Europe/Helsinki")
IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"
_IDENTIFIER = re.compile(IDENTIFIER_PATTERN)
_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)

DataClass: TypeAlias = Literal["public", "private", "restricted"]
CardStatus: TypeAlias = Literal[
    "ajantasainen",
    "vanhentunut",
    "ei yhdistetty",
    "tietoa ei saatavilla",
    "virhe",
    "esimerkkidata",
]
Identifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN)]
ShortText = Annotated[str, Field(min_length=1, max_length=160)]
Text = Annotated[str, Field(min_length=1, max_length=1000)]
LongText = Annotated[str, Field(min_length=1, max_length=4000)]


def _finite_number(value: int | float) -> int | float:
    if not math.isfinite(value) or abs(value) > 1e15:
        raise ValueError("number must be finite and at most 1e15 in magnitude")
    return value


Number = Annotated[StrictInt | StrictFloat, AfterValidator(_finite_number)]


def _aware_datetime(value: Any) -> datetime:
    if isinstance(value, str):
        if not _TIMESTAMP.fullmatch(value):
            raise ValueError("timestamp must be ISO 8601 with a timezone")
        if not value.endswith("Z") and (int(value[-5:-3]) >= 24 or int(value[-2:]) >= 60):
            raise ValueError("timestamp timezone offset is invalid")
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timestamp must have a timezone")
    return value


def _calendar_date(value: Any) -> date:
    if isinstance(value, str):
        if not _DATE.fullmatch(value):
            raise ValueError("date must be YYYY-MM-DD")
        value = date.fromisoformat(value)
    if type(value) is not date:
        raise ValueError("date must be a calendar date")
    return value


AwareTimestamp = Annotated[datetime, BeforeValidator(_aware_datetime)]
CalendarDate = Annotated[date, BeforeValidator(_calendar_date)]


def _https_url(value: str) -> str:
    if any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise ValueError("URL contains whitespace or control characters")
    if "\\" in value:
        raise ValueError("URL contains a backslash")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid URL") from exc
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not _HOSTNAME.fullmatch(host)
        or ".." in host
        or "." not in host
        or host.endswith((".localhost", ".local", ".internal"))
    ):
        raise ValueError("source URL must be a public HTTPS hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP address source URLs are not accepted")
    return value


SafeURL = Annotated[str, Field(max_length=2048), AfterValidator(_https_url)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Source(StrictModel):
    name: ShortText
    url: SafeURL | None


class MetricData(StrictModel):
    value: Number | None
    note: Text | None


class SeriesPoint(StrictModel):
    date: CalendarDate
    value: Number | None


class TimeSeriesData(StrictModel):
    period_start: CalendarDate
    period_end: CalendarDate
    points: Annotated[list[SeriesPoint], Field(max_length=MAX_POINTS)]

    @model_validator(mode="after")
    def validate_period(self) -> TimeSeriesData:
        if self.period_end < self.period_start:
            raise ValueError("series period is reversed")
        if (self.period_end - self.period_start).days >= MAX_POINTS:
            raise ValueError("series period exceeds 366 days")
        previous: date | None = None
        for point in self.points:
            if not self.period_start <= point.date <= self.period_end:
                raise ValueError("point is outside the observation period")
            if previous is not None and point.date <= previous:
                raise ValueError("points must have unique, ascending dates")
            previous = point.date
        return self

    @property
    def observed_count(self) -> int:
        return sum(point.value is not None for point in self.points)

    @property
    def missing_count(self) -> int:
        return (self.period_end - self.period_start).days + 1 - self.observed_count

    @property
    def complete_points(self) -> tuple[SeriesPoint, ...]:
        """Fill omitted days with null; never interpolate or assume zero."""
        by_day = {point.date: point.value for point in self.points}
        return tuple(
            SeriesPoint(date=day, value=by_day.get(day))
            for offset in range((self.period_end - self.period_start).days + 1)
            for day in (self.period_start + timedelta(days=offset),)
        )


class Recommendation(StrictModel):
    title: ShortText
    description: Text
    dietary_tags: Annotated[list[ShortText], Field(max_length=12)]
    reason: Text
    source_url: SafeURL | None


class RecommendationData(StrictModel):
    for_date: CalendarDate
    criteria: Annotated[list[ShortText], Field(max_length=12)]
    items: Annotated[list[Recommendation], Field(max_length=30)]


class Idea(StrictModel):
    idea_id: Identifier
    title: ShortText
    problem: Text
    solution: Text
    assumption: Text
    next_experiment: Text
    stage: Literal["idea", "hypothesis", "tested"]
    risks: Annotated[list[Text], Field(max_length=8)]


class IdeaData(StrictModel):
    ideas: Annotated[list[Idea], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def unique_ideas(self) -> IdeaData:
        if len({idea.idea_id for idea in self.ideas}) != 3:
            raise ValueError("idea IDs must be unique")
        return self


class Update(StrictModel):
    update_id: Identifier
    published_at: AwareTimestamp
    title: ShortText
    summary: Text
    detail: LongText | None
    source_url: SafeURL | None


class UpdateData(StrictModel):
    updates: Annotated[list[Update], Field(max_length=30)]

    @model_validator(mode="after")
    def unique_updates(self) -> UpdateData:
        ids = [update.update_id for update in self.updates]
        if len(ids) != len(set(ids)):
            raise ValueError("update IDs must be unique")
        return self


class BaseCard(StrictModel):
    schema_version: Literal["ilmari.card.v1"]
    app_id: Identifier
    card_id: Identifier
    title: ShortText
    data_class: DataClass
    published_at: AwareTimestamp
    observed_until: AwareTimestamp
    fresh_until: AwareTimestamp
    source: Source
    units: Annotated[str, Field(min_length=1, max_length=32)] | None

    @model_validator(mode="after")
    def timestamp_order(self) -> BaseCard:
        if not self.observed_until <= self.published_at <= self.fresh_until:
            raise ValueError("timestamps must be observed <= published <= fresh")
        return self


class MetricCard(BaseCard):
    kind: Literal["metric"]
    data: MetricData


class TimeSeriesCard(BaseCard):
    kind: Literal["time_series"]
    data: TimeSeriesData

    @model_validator(mode="after")
    def observed_period(self) -> TimeSeriesCard:
        if self.data.period_end > self.observed_until.astimezone(HELSINKI).date():
            raise ValueError("series includes days after the last observation")
        return self


class RecommendationCard(BaseCard):
    kind: Literal["recommendation_list"]
    data: RecommendationData


class IdeaCard(BaseCard):
    kind: Literal["idea_list"]
    data: IdeaData


class UpdateCard(BaseCard):
    kind: Literal["update_feed"]
    data: UpdateData

    @model_validator(mode="after")
    def observed_updates(self) -> UpdateCard:
        if any(update.published_at > self.observed_until for update in self.data.updates):
            raise ValueError("update is newer than the last observation")
        return self


Card: TypeAlias = Annotated[
    MetricCard | TimeSeriesCard | RecommendationCard | IdeaCard | UpdateCard,
    Field(discriminator="kind"),
]
CARD_ADAPTER = TypeAdapter(Card)


class PublicationError(ValueError):
    """A rejected publication; its detailed cause is never shown to end users."""


@dataclass(frozen=True, slots=True)
class CardState:
    app_id: str
    status: CardStatus
    cards: tuple[Card, ...] = ()
    message: str = ""
    rejected_count: int = 0


def _reject_constant(_value: str) -> Any:
    raise PublicationError("non-finite JSON constant")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PublicationError("duplicate JSON field")
        result[key] = value
    return result


def _source_urls(card: Card) -> tuple[str, ...]:
    urls = [card.source.url] if card.source.url else []
    if isinstance(card, RecommendationCard):
        urls.extend(item.source_url for item in card.data.items if item.source_url)
    elif isinstance(card, UpdateCard):
        urls.extend(item.source_url for item in card.data.updates if item.source_url)
    return tuple(urls)


def validate_card(
    payload: bytes,
    *,
    expected_app_id: str,
    expected_card_id: str,
    expected_data_class: DataClass,
    allowed_source_hosts: frozenset[str] = frozenset(),
) -> Card:
    """Validate a bounded JSON file using caller-owned identity and policy.

    HTML remains plain text. Render it with template autoescaping; never mark a
    source field as safe HTML. URL acceptance does not authorize fetching it.
    """
    if len(payload) > MAX_CARD_BYTES:
        raise PublicationError("card is too large")
    if expected_data_class == "restricted":
        raise PublicationError("restricted summaries are not supported")
    try:
        raw = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        card = CARD_ADAPTER.validate_python(raw)
    except (UnicodeError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise PublicationError("invalid card publication") from exc
    if card.app_id != expected_app_id or card.card_id != expected_card_id:
        raise PublicationError("publication identity does not match its path")
    if card.data_class != expected_data_class:
        raise PublicationError("publication class does not match trusted policy")
    for url in _source_urls(card):
        if urlsplit(url).hostname not in allowed_source_hosts:
            raise PublicationError("source hostname is not approved")
    return card


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


def _open_publication_root(path: Path) -> int:
    """Pin every ancestor, rejecting symlinks rather than resolving them."""
    if not path.is_absolute() or str(path) == "/" or ".." in path.parts:
        raise PublicationError("publication root must be an explicit absolute directory")
    descriptor = os.open("/", _DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_card(directory_fd: int, filename: str) -> bytes:
    descriptor = os.open(filename, _FILE_FLAGS, dir_fd=directory_fd)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise PublicationError("publication is not an isolated regular file")
        if metadata.st_size > MAX_CARD_BYTES:
            raise PublicationError("card is too large")
        chunks: list[bytes] = []
        size = 0
        while size <= MAX_CARD_BYTES:
            chunk = os.read(descriptor, min(8192, MAX_CARD_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if size > MAX_CARD_BYTES:
            raise PublicationError("card grew beyond its limit")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _card_filenames(directory_fd: int) -> list[str]:
    filenames: list[str] = []
    with os.scandir(directory_fd) as entries:
        for count, entry in enumerate(entries, start=1):
            if count > MAX_DIRECTORY_ENTRIES:
                raise PublicationError("too many publication directory entries")
            if not entry.name.endswith(".json"):
                continue
            card_id = entry.name[:-5]
            if not _IDENTIFIER.fullmatch(card_id):
                raise PublicationError("invalid publication filename")
            filenames.append(entry.name)
            if len(filenames) > MAX_CARDS_PER_APP:
                raise PublicationError("too many cards")
    return sorted(filenames)


def _state_for_cards(
    app_id: str, cards: tuple[Card, ...], rejected: int, now: datetime, demo: bool
) -> CardState:
    if not cards:
        if rejected:
            return CardState(app_id, "virhe", message="Julkaisu ei läpäissyt tarkistusta.", rejected_count=rejected)
        return CardState(app_id, "tietoa ei saatavilla", message="Julkaistua yhteenvetoa ei ole.")
    if rejected:
        return CardState(app_id, "virhe", cards, "Osa julkaisuista ei läpäissyt tarkistusta.", rejected)
    # A date-specific menu can never silently become today's list.
    today = now.astimezone(HELSINKI).date()
    if any(isinstance(card, RecommendationCard) and card.data.for_date > today for card in cards):
        return CardState(app_id, "tietoa ei saatavilla", message="Tälle päivälle ei ole julkaistua ruokalistaa.")
    if not any(
        (isinstance(card, MetricCard) and card.data.value is not None)
        or (isinstance(card, TimeSeriesCard) and card.data.observed_count > 0)
        or (isinstance(card, RecommendationCard) and bool(card.data.items))
        or isinstance(card, IdeaCard)
        or (isinstance(card, UpdateCard) and bool(card.data.updates))
        for card in cards
    ):
        return CardState(app_id, "tietoa ei saatavilla", cards, "Havaintoja ei ole julkaistu.")
    stale = any(
        card.fresh_until <= now
        or (isinstance(card, RecommendationCard) and card.data.for_date < today)
        for card in cards
    )
    if demo:
        return CardState(app_id, "esimerkkidata", cards, "DEMO – ESIMERKKIDATA. Ei todellinen tietolähde.")
    if stale:
        return CardState(app_id, "vanhentunut", cards, "Tieto on vanhentunut. Tarkista havaintoaika.")
    return CardState(app_id, "ajantasainen", cards, "Julkaistu yhteenveto on ajantasainen.")


def load_cards(
    publication_dir: Path | None,
    *,
    app_classes: Mapping[str, DataClass],
    allowed_private_apps: frozenset[str] = frozenset(),
    allowed_source_hosts: frozenset[str] = frozenset(),
    now: datetime | None = None,
    demo: bool = False,
) -> dict[str, CardState]:
    """Read only configured app summaries from an isolated publication tree.

    The app→class mapping and private-app consent come from trusted server
    configuration, never from a publication. Invalid cards are isolated per app.
    ``demo`` must likewise come from an explicit development-only server setting.
    """
    for app_id, data_class in app_classes.items():
        if not isinstance(app_id, str) or not _IDENTIFIER.fullmatch(app_id):
            raise ValueError("invalid configured app ID")
        if data_class not in ("public", "private", "restricted"):
            raise ValueError("invalid configured data class")
    current_time = _aware_datetime(now) if now is not None else datetime.now(UTC)
    states: dict[str, CardState] = {}
    eligible: list[str] = []
    for app_id, data_class in app_classes.items():
        if data_class == "restricted":
            states[app_id] = CardState(app_id, "ei yhdistetty", message="Rajoitettujen tietojen yhteenvetoa ei lueta.")
        elif data_class == "private" and app_id not in allowed_private_apps:
            states[app_id] = CardState(app_id, "ei yhdistetty", message="Yksityisen yhteenvedon julkaisu vaatii erillisen luvan.")
        elif publication_dir is None:
            states[app_id] = CardState(app_id, "ei yhdistetty", message="Julkaisulähdettä ei ole yhdistetty.")
        else:
            eligible.append(app_id)
    if not eligible:
        return states
    try:
        root_fd = _open_publication_root(publication_dir)
    except FileNotFoundError:
        for app_id in eligible:
            states[app_id] = CardState(app_id, "tietoa ei saatavilla", message="Julkaisuhakemistoa ei ole saatavilla.")
        return states
    except (OSError, PublicationError):
        for app_id in eligible:
            states[app_id] = CardState(app_id, "virhe", message="Julkaisuhakemisto ei läpäissyt tarkistusta.")
        return states
    try:
        for app_id in eligible:
            try:
                app_fd = os.open(app_id, _DIRECTORY_FLAGS, dir_fd=root_fd)
            except FileNotFoundError:
                states[app_id] = CardState(app_id, "tietoa ei saatavilla", message="Sovellus ei ole julkaissut yhteenvetoa.")
                continue
            except OSError:
                states[app_id] = CardState(app_id, "virhe", message="Sovelluksen julkaisu ei läpäissyt tarkistusta.")
                continue
            cards: list[Card] = []
            rejected = 0
            try:
                filenames = _card_filenames(app_fd)
                for filename in filenames:
                    try:
                        card = validate_card(
                            _read_card(app_fd, filename),
                            expected_app_id=app_id,
                            expected_card_id=filename[:-5],
                            expected_data_class=app_classes[app_id],
                            allowed_source_hosts=allowed_source_hosts,
                        )
                        if card.published_at > current_time + timedelta(minutes=2):
                            raise PublicationError("publication is from the future")
                        cards.append(card)
                    except (OSError, PublicationError, ValidationError):
                        rejected += 1
            except (OSError, PublicationError):
                rejected += 1
            finally:
                os.close(app_fd)
            states[app_id] = _state_for_cards(app_id, tuple(cards), rejected, current_time, demo)
    finally:
        os.close(root_fd)
    return states
