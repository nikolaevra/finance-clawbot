from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any


@dataclass
class FakeResult:
    data: Any


class FakeStorageBucket:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def upload(self, path: str, content: bytes | str, _options: dict | None = None):
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        if path in self.files:
            raise FileExistsError(path)
        self.files[path] = data
        return {"path": path}

    def update(self, path: str, content: bytes | str, _options: dict | None = None):
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        self.files[path] = data
        return {"path": path}

    def download(self, path: str):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def remove(self, paths: list[str]):
        for path in paths:
            self.files.pop(path, None)
        return {"removed": paths}

    def list(self, prefix: str):
        names = []
        for path in sorted(self.files):
            if path.startswith(prefix):
                names.append({"name": path.split("/")[-1]})
        return names


class FakeStorageService:
    def __init__(self) -> None:
        self.buckets: dict[str, FakeStorageBucket] = {}

    def get_bucket(self, name: str):
        if name not in self.buckets:
            raise KeyError(name)
        return self.buckets[name]

    def create_bucket(self, name: str, options: dict | None = None):
        self.buckets[name] = self.buckets.get(name, FakeStorageBucket())
        return {"name": name, "options": options or {}}

    def from_(self, name: str) -> FakeStorageBucket:
        self.buckets.setdefault(name, FakeStorageBucket())
        return self.buckets[name]


class FakeTable:
    def __init__(self, store: dict[str, list[dict]], name: str) -> None:
        self._store = store
        self._name = name
        self._filters: list[tuple[str, str, Any]] = []
        self._mode = "select"
        self._payload: Any = None
        self._single = False
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def _matches(self, row: dict) -> bool:
        for op, key, value in self._filters:
            if op == "eq" and row.get(key) != value:
                return False
            if op == "in" and row.get(key) not in value:
                return False
            if op == "gte" and row.get(key) < value:
                return False
            if op == "or_user_or_null" and row.get("user_id") not in {value, None}:
                return False
        return True

    def _rows(self) -> list[dict]:
        rows = [deepcopy(row) for row in self._store.setdefault(self._name, []) if self._matches(row)]
        if self._order:
            key, desc = self._order
            rows.sort(key=lambda row: row.get(key) or "", reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def select(self, _fields: str = "*"):
        self._mode = "select"
        return self

    def insert(self, payload: dict | list[dict]):
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict):
        self._mode = "update"
        self._payload = payload
        return self

    def upsert(self, payload: dict, on_conflict: str | None = None):
        self._mode = "upsert"
        self._payload = {"row": payload, "on_conflict": on_conflict}
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def eq(self, key: str, value: Any):
        self._filters.append(("eq", key, value))
        return self

    def in_(self, key: str, value: list[Any]):
        self._filters.append(("in", key, value))
        return self

    def gte(self, key: str, value: Any):
        self._filters.append(("gte", key, value))
        return self

    def order(self, key: str, desc: bool = False):
        self._order = (key, desc)
        return self

    def limit(self, value: int):
        self._limit = value
        return self

    def single(self):
        self._single = True
        return self

    def or_(self, expression: str):
        if expression.startswith("user_id.eq.") and expression.endswith(",user_id.is.null"):
            self._filters.append(("or_user_or_null", "user_id", expression.split(".")[2].split(",")[0]))
        return self

    def execute(self):
        table_rows = self._store.setdefault(self._name, [])

        if self._mode == "select":
            rows = self._rows()
            if self._single:
                return FakeResult(rows[0] if rows else None)
            return FakeResult(rows)

        if self._mode == "insert":
            payload_rows = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted: list[dict] = []
            for row in payload_rows:
                new_row = deepcopy(row)
                if "id" not in new_row:
                    new_row["id"] = f"{self._name}-{len(table_rows) + len(inserted) + 1}"
                if "created_at" not in new_row:
                    new_row["created_at"] = datetime.utcnow().isoformat()
                inserted.append(new_row)
            table_rows.extend(inserted)
            return FakeResult(inserted)

        if self._mode == "update":
            updated: list[dict] = []
            for row in table_rows:
                if self._matches(row):
                    row.update(deepcopy(self._payload))
                    updated.append(deepcopy(row))
            return FakeResult(updated)

        if self._mode == "upsert":
            row = deepcopy(self._payload["row"])
            conflict_cols = (self._payload.get("on_conflict") or "").split(",") if self._payload.get("on_conflict") else []
            if conflict_cols:
                existing = None
                for current in table_rows:
                    if all(current.get(col) == row.get(col) for col in conflict_cols):
                        existing = current
                        break
                if existing is not None:
                    existing.update(row)
                    return FakeResult([deepcopy(existing)])
            if "id" not in row:
                row["id"] = f"{self._name}-{len(table_rows) + 1}"
            table_rows.append(row)
            return FakeResult([deepcopy(row)])

        if self._mode == "delete":
            deleted = [deepcopy(row) for row in table_rows if self._matches(row)]
            self._store[self._name] = [row for row in table_rows if not self._matches(row)]
            return FakeResult(deleted)

        raise AssertionError(f"Unsupported mode {self._mode}")


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict]] | None = None) -> None:
        self.tables = deepcopy(tables or {})
        self.storage = FakeStorageService()
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_result: list[dict] = []

    def table(self, name: str) -> FakeTable:
        return FakeTable(self.tables, name)

    def rpc(self, name: str, params: dict[str, Any]):
        self.rpc_calls.append((name, params))
        return SimpleNamespace(execute=lambda: FakeResult(deepcopy(self.rpc_result)))
