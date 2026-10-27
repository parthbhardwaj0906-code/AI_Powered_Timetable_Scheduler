"""Pydantic schemas: strict validation of every dataset before a solver sees it."""
from typing import List, Literal

from pydantic import BaseModel, Field, model_validator


class Slot(BaseModel):
    day: int = Field(ge=0)
    period: int = Field(ge=0)


class Subject(BaseModel):
    code: str
    name: str
    weekly_hours: int = Field(gt=0, description="Required weekly sessions")
    type: Literal["theory", "lab"]


class Teacher(BaseModel):
    name: str
    subjects: List[str] = Field(description="Subject codes this teacher may teach")
    unavailable_slots: List[Slot] = Field(default_factory=list, description="HARD: cannot teach")
    avoid_slots: List[Slot] = Field(default_factory=list, description="OPTIONAL extension (not in the assignment spec): extra S4 preferences")
    max_weekly_load: int = Field(gt=0)


class ClassBatch(BaseModel):
    name: str
    strength: int = Field(gt=0)
    subjects: List[str]
    lunch_break_slot: int = Field(ge=0)


class Room(BaseModel):
    name: str
    capacity: int = Field(gt=0)
    type: Literal["classroom", "lab"]


class TimeStructure(BaseModel):
    working_days: int = Field(ge=1, le=6)
    periods_per_day: int = Field(ge=2, le=12)
    break_periods: List[int] = Field(default_factory=list)


class TimetableDataset(BaseModel):
    time_structure: TimeStructure
    subjects: List[Subject]
    teachers: List[Teacher]
    classes: List[ClassBatch]
    rooms: List[Room]

    @model_validator(mode="after")
    def _cross_checks(self):
        def dupes(names):
            return sorted({n for n in names if names.count(n) > 1})

        for label, names in (
            ("subject codes", [s.code for s in self.subjects]),
            ("teacher names", [t.name for t in self.teachers]),
            ("class names", [c.name for c in self.classes]),
            ("room names", [r.name for r in self.rooms]),
        ):
            if dupes(names):
                raise ValueError(f"Duplicate {label}: {dupes(names)}")

        codes = {s.code for s in self.subjects}
        ts = self.time_structure
        if any(b >= ts.periods_per_day for b in ts.break_periods):
            raise ValueError("break_periods contains a period outside the day")
        for t in self.teachers:
            bad = set(t.subjects) - codes
            if bad:
                raise ValueError(f"Teacher '{t.name}' teaches unknown subjects {sorted(bad)}")
            for sl in t.unavailable_slots + t.avoid_slots:
                if sl.day >= ts.working_days or sl.period >= ts.periods_per_day:
                    raise ValueError(f"Teacher '{t.name}' has a slot outside the timetable grid: {sl}")
        for c in self.classes:
            bad = set(c.subjects) - codes
            if bad:
                raise ValueError(f"Class '{c.name}' uses unknown subjects {sorted(bad)}")
            if c.lunch_break_slot >= ts.periods_per_day:
                raise ValueError(f"Class '{c.name}' lunch slot is outside the day")
        return self
