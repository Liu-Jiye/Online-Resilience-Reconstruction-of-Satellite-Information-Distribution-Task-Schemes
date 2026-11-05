"""Immutable, integer-second, single-hop ISL interchange model."""
from dataclasses import asdict, dataclass, replace
from fractions import Fraction
from math import ceil, floor, isfinite
import json


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def identifier(value):
    if not isinstance(value, str) or not value:
        raise ValueError("IDs must be nonempty strings")


def inward_window(start, end):
    """Empty after inward rounding means no usable contact, never expand."""
    if not isfinite(start) or not isfinite(end) or start > end:
        raise ValueError("invalid physical window")
    a, b = ceil(start), floor(end)
    return (a, b) if a < b else None


@dataclass(frozen=True)
class Task:
    id: str
    sender: str
    receiver: str
    release: int
    deadline: int
    data_bits: int
    rate_bps: int
    utility: int

    def __post_init__(self):
        for value in (self.id, self.sender, self.receiver):
            identifier(value)
        if self.sender == self.receiver:
            raise ValueError("endpoints must differ")
        for field in ("release", "deadline", "utility"):
            integer(getattr(self, field), field)
        for field in ("data_bits", "rate_bps"):
            integer(getattr(self, field), field, 1)
        if self.release >= self.deadline:
            raise ValueError("empty task window")

    @property
    def duration(self):
        # Exact ceil(1+D/R), without float overflow or rounding drift.
        return 1 + (self.data_bits + self.rate_bps - 1) // self.rate_bps

    @property
    def density_key(self):
        return (-Fraction(self.utility, self.duration), self.deadline, self.id)


@dataclass(frozen=True)
class Contact:
    id: str
    sender: str
    receiver: str
    start: int
    end: int

    def __post_init__(self):
        for value in (self.id, self.sender, self.receiver):
            identifier(value)
        integer(self.start, "contact.start")
        integer(self.end, "contact.end", 1)
        if self.start >= self.end or self.sender == self.receiver:
            raise ValueError("invalid contact")


@dataclass(frozen=True)
class Busy:
    resource: str
    start: int
    end: int

    def __post_init__(self):
        identifier(self.resource)
        integer(self.start, "busy.start")
        integer(self.end, "busy.end", 1)
        if self.start >= self.end:
            raise ValueError("empty busy interval")


@dataclass(frozen=True)
class Item:
    task_id: str
    sender: str
    receiver: str
    start: int
    end: int


def ordered(plan):
    return tuple(sorted(plan, key=lambda p: (p.start, p.task_id)))


@dataclass(frozen=True)
class Instance:
    id: str
    satellites: tuple[str, ...]
    tasks: tuple[Task, ...]
    contacts: tuple[Contact, ...]
    calendar: tuple[Busy, ...] = ()
    horizon: int = 5400

    def __post_init__(self):
        identifier(self.id)
        integer(self.horizon, "horizon", 1)
        if not self.satellites or len(set(self.satellites)) != len(self.satellites):
            raise ValueError("duplicate/empty satellites")
        for s in self.satellites:
            identifier(s)
        if len({t.id for t in self.tasks}) != len(self.tasks):
            raise ValueError("duplicate task IDs")
        if len({c.id for c in self.contacts}) != len(self.contacts):
            raise ValueError("duplicate contact IDs")
        for t in self.tasks:
            if not {t.sender, t.receiver} <= set(self.satellites) or t.deadline > self.horizon:
                raise ValueError("task outside instance")
        for c in self.contacts:
            if not {c.sender, c.receiver} <= set(self.satellites) or c.end > self.horizon:
                raise ValueError("contact outside instance")
        for b in self.calendar:
            if b.resource not in self.satellites or b.end > self.horizon:
                raise ValueError("calendar outside instance")

    @property
    def task_map(self):
        return {t.id: t for t in self.tasks}


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    seed: int
    intensity: float
    cancelled: tuple[str, ...] = ()
    rewards: tuple[tuple[str, int], ...] = ()
    urgent: Task | None = None
    applicable: bool = True

    def __post_init__(self):
        identifier(self.id)
        integer(self.seed, "event seed")
        if self.kind not in {"cancellation", "reward_update", "urgent_insertion"}:
            raise ValueError("unknown event")
        if not isfinite(self.intensity) or not 0 <= self.intensity <= 1:
            raise ValueError("invalid intensity")
        if len(set(self.cancelled)) != len(self.cancelled):
            raise ValueError("duplicate cancellation")
        if len({k for k, _ in self.rewards}) != len(self.rewards):
            raise ValueError("duplicate reward update")
        for _, reward in self.rewards:
            integer(reward, "reward")
        if ((self.kind != "cancellation" and self.cancelled)
                or (self.kind != "reward_update" and self.rewards)
                or (self.kind == "urgent_insertion") != (self.urgent is not None)):
            raise ValueError("event payload does not match kind")


def apply_event(instance, event):
    ids = set(instance.task_map)
    if not set(event.cancelled) <= ids or not {k for k, _ in event.rewards} <= ids:
        raise ValueError("event references unknown task")
    changes = dict(event.rewards)
    tasks = tuple(replace(t, utility=changes.get(t.id, t.utility)) for t in instance.tasks)
    if event.urgent:
        if event.urgent.id in ids:
            raise ValueError("urgent ID collision")
        tasks += (event.urgent,)
    return replace(instance, tasks=tasks)


@dataclass(frozen=True)
class Case:
    base: Instance
    reference: tuple[Item, ...]
    event: Event
    frozen_count: int = 0
    post_event_contacts: tuple[Contact, ...] | None = None

    def __post_init__(self):
        integer(self.frozen_count, "frozen_count")
        if self.frozen_count > len(self.reference) or self.reference != ordered(self.reference):
            raise ValueError("reference must be ordered and frozen count in range")

    @property
    def frozen(self):
        return self.reference[:self.frozen_count]

    def effective_instance(self):
        instance = apply_event(self.base, self.event)
        return replace(instance, contacts=self.post_event_contacts) if self.post_event_contacts is not None else instance


def frozen_count(reference, ratio):
    if not isfinite(ratio) or not 0 <= ratio <= 1:
        raise ValueError("invalid frozen ratio")
    return floor(Fraction(str(ratio)) * len(reference))


def case_to_dict(case):
    return asdict(case)


def case_from_dict(data):
    raw = data['base']
    base = Instance(raw['id'], tuple(raw['satellites']), tuple(Task(**t) for t in raw['tasks']),
                    tuple(Contact(**c) for c in raw['contacts']),
                    tuple(Busy(**b) for b in raw['calendar']), raw['horizon'])
    e = data['event']
    event = Event(e['id'], e['kind'], e['seed'], e['intensity'], tuple(e['cancelled']),
                  tuple((k, v) for k, v in e['rewards']), Task(**e['urgent']) if e['urgent'] else None,
                  e['applicable'])
    post = data.get('post_event_contacts')
    return Case(base, tuple(Item(**p) for p in data['reference']), event, data['frozen_count'],
                tuple(Contact(**c) for c in post) if post is not None else None)


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
