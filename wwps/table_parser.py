from __future__ import annotations

import threading
from typing import Callable


class TableParser:

    def __init__(self, src: str | None, prefix: str = "", delimiter: str = "|"):
        self._delimiter = delimiter
        self._prefix = None
        if prefix != "":
            src = src[len(prefix) + 1:]
            self._prefix = prefix
        self.table: list[list[str]] = self._load(src or "")
        self._identifiers: dict[str, list[int]] = {}
        self._load_identifier_table()

    def _load(self, src: str) -> list[list[str]]:
        if not src:
            return []
        return [row.split(self._delimiter) for row in src.split('*')]

    def add_row(self, row: list[str]):
        self.table.append(row)
        self._load_row_into_identifiers(row, len(self.table) - 1)

    def _load_row_into_identifiers(self, row: list[str], i: int):
        for item in row:
            self._identifiers.setdefault(item, []).append(i)

    def _load_identifier_table(self):
        self._identifiers.clear()
        for i, row in enumerate(self.table):
            self._load_row_into_identifiers(row, i)

    def find_index(self, identifiers: list[str]) -> int:
        return _find_index(self._identifiers, identifiers)

    def __str__(self) -> str:
        s = '*'.join(self._delimiter.join(row) for row in self.table)
        s = s.strip('*')
        if self._prefix is not None:
            return f"{self._prefix}:{s}"
        return s


def _find_index(identifier_dict: dict[str, list[int]], identifiers: list[str]) -> int:
    candidates: set[int] = set()
    for identifier in identifiers:
        if identifier not in identifier_dict:
            return -1
        indexes = set(identifier_dict[identifier])
        if not candidates:
            candidates = indexes
        else:
            matching = set()
            for candidate in candidates:
                if candidate in indexes:
                    matching.add(candidate)
                    break
            if not matching:
                return -1
            candidates = matching
        if len(candidates) == 1:
            return next(iter(candidates))
    return -1


class TypedTableParser:

    def __init__(self, row_factory: Callable, fields: list[tuple[str, Callable]],
                 src: str | None = "", prefix: str = "", delimiter: str = "|"):
        if src is None:
            src = ""
        self._row_factory = row_factory
        self._fields = fields
        self._delimiter = delimiter
        self._prefix = None
        if prefix != "":
            src = src[len(prefix) + 1:]
            self._prefix = prefix
        self._raw_table = self._load(src)
        self._identifiers: dict[str, list[int]] = {}
        self._load_identifier_table()
        self.items: list = []
        self._convert_to_objects()
        self._to_string_lock = threading.Lock()

    def _load(self, src: str) -> list[list[str]]:
        if not src:
            return []
        return [row.split(self._delimiter) for row in src.split('*')]

    def _convert_to_objects(self):
        for row in self._raw_table:
            obj = self._row_factory()
            for i in range(min(len(row), len(self._fields))):
                name, conv = self._fields[i]
                try:
                    setattr(obj, name, conv(row[i]))
                except (ValueError, TypeError):
                    pass
            self.items.append(obj)

    def add_item(self, item):
        self.items.append(item)
        row = self._convert_object_to_row(item)
        self._raw_table.append(row)
        self._load_row_into_identifiers(row, len(self._raw_table) - 1)

    def _convert_object_to_row(self, item) -> list[str]:
        out = []
        for name, _ in self._fields:
            val = getattr(item, name, None)
            if val is None:
                out.append("")
            elif isinstance(val, bool):
                out.append(str(int(val)))
            else:
                out.append(str(val))
        return out

    def _load_row_into_identifiers(self, row: list[str], i: int):
        for item in row:
            self._identifiers.setdefault(item, []).append(i)

    def _load_identifier_table(self):
        self._identifiers.clear()
        for i, row in enumerate(self._raw_table):
            self._load_row_into_identifiers(row, i)

    def find_index(self, identifiers: list[str]) -> int:
        return _find_index(self._identifiers, identifiers)

    def __str__(self) -> str:
        with self._to_string_lock:
            self._raw_table = [self._convert_object_to_row(it) for it in self.items]
            s = '*'.join(self._delimiter.join(row) for row in self._raw_table)
            s = s.strip('*')
            if self._prefix is not None:
                return f"{self._prefix}:{s}"
            return s


def int0(v: str) -> int:
    return int(v)
