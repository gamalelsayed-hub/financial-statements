"""Report building blocks shared by every report module."""
from dataclasses import dataclass, field


@dataclass
class Row:
    label: str
    values: list = field(default_factory=list)
    kind: str = "item"   # item | sub | tot | hdr | note
    fmt: str = "n"       # n | % | x | d | t
    styles: list = None  # optional css class per value (good / warn / bad)


@dataclass
class Table:
    columns: list
    rows: list
    col_fmts: list = None   # per value column, overrides the row format
    title: str = None


@dataclass
class Para:
    text: str
    cls: str = "sub"


@dataclass
class Report:
    key: str
    title: str
    subtitle: str
    blocks: list
