"""KV store access: splunk.rest inside Splunk; vendored splunklib elsewhere."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from models import APP_NAME

OWNER = "nobody"

_USE_SPLUNK_REST = False
try:
    import splunk.rest  # type: ignore

    _USE_SPLUNK_REST = True
except ImportError:
    pass


class KvError(Exception):
    def __init__(self, message: str, status: int = 500, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


# --- splunk.rest backend (Splunk app runtime / Python 3.9 persist handler) ---


def _parse_content(content: Any) -> Any:
    if content is None:
        return None
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    if isinstance(content, str):
        content = content.strip()
        if not content:
            return None
        return json.loads(content)
    return content


def _collection_data_path(collection: str, key: Optional[str] = None) -> str:
    path = f"/servicesNS/{OWNER}/{APP_NAME}/storage/collections/data/{collection}"
    if key:
        path = f"{path}/{key}"
    return path


def _simple_request(
    session_key: str,
    method: str,
    path: str,
    *,
    query: Optional[Dict[str, Any]] = None,
    body: Optional[Any] = None,
) -> Any:
    import splunk.rest

    getargs = dict(query or {})
    getargs.setdefault("output_mode", "json")
    jsonargs = None
    if body is not None:
        jsonargs = json.dumps(body) if not isinstance(body, str) else body
    response, content = splunk.rest.simpleRequest(
        path,
        sessionKey=session_key,
        getargs=getargs,
        method=method,
        jsonargs=jsonargs,
        raiseAllErrors=False,
    )
    status = int(response.get("status", 200))
    if status >= 400:
        raise KvError(f"KV request failed ({status})", status=status, body=str(content)[:500])
    return _parse_content(content)


class _RestKvCollectionData:
    def __init__(self, session_key: str, collection: str):
        self._session_key = session_key
        self._collection = collection

    def query(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if query:
            params["query"] = json.dumps(query)
        data = _simple_request(
            self._session_key,
            "GET",
            _collection_data_path(self._collection),
            query=params,
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            rows = []
            for entry in data.get("entry") or []:
                content = entry.get("content")
                if isinstance(content, dict):
                    if "_key" not in content and entry.get("name"):
                        content = dict(content)
                        content["_key"] = entry["name"]
                    rows.append(content)
            return rows
        return []

    def query_by_id(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            data = _simple_request(
                self._session_key,
                "GET",
                _collection_data_path(self._collection, key),
            )
        except KvError as err:
            if err.status == 404:
                return None
            raise
        if isinstance(data, dict):
            if "entry" in data and data["entry"]:
                content = dict(data["entry"][0].get("content") or {})
                content.setdefault("_key", data["entry"][0].get("name") or key)
                return content
            if "_key" not in data:
                data = dict(data)
                data["_key"] = key
            return data
        return None

    def insert(self, record: Dict[str, Any], key: Optional[str] = None) -> str:
        payload = dict(record)
        payload.pop("_key", None)
        data = _simple_request(
            self._session_key,
            "POST",
            _collection_data_path(self._collection),
            body=payload,
        )
        if isinstance(data, dict):
            if data.get("_key"):
                return data["_key"]
            entries = data.get("entry") or []
            if entries:
                return entries[0].get("name") or entries[0].get("content", {}).get("_key", "")
        return str(data)

    def update(self, key: str, record: Dict[str, Any]) -> None:
        payload = dict(record)
        payload.pop("_key", None)
        _simple_request(
            self._session_key,
            "POST",
            _collection_data_path(self._collection, key),
            body=payload,
        )

    def delete(self, key: str) -> None:
        _simple_request(
            self._session_key,
            "DELETE",
            _collection_data_path(self._collection, key),
        )

    def batch_save(self, *records: Dict[str, Any]) -> None:
        for record in records:
            self.insert(record)


class _RestKvCollection:
    def __init__(self, session_key: str, name: str):
        self.data = _RestKvCollectionData(session_key, name)


class RestKvService:
    def __init__(self, session_key: str):
        self._session_key = session_key
        self.kvstore = self

    def __getitem__(self, name: str) -> _RestKvCollection:
        return _RestKvCollection(self._session_key, name)


# --- splunklib backend (external scripts / system Python + vendored lib/) ---


def _sdk_connect(session_key: str, app: str):
    import _sdk_path  # noqa: F401

    import splunklib.client as client

    return client.connect(token=session_key, app=app, owner=OWNER)


ServiceType = Union[RestKvService, Any]


def connect(session_key: str, app: str = APP_NAME) -> ServiceType:
    if _USE_SPLUNK_REST:
        return RestKvService(session_key)
    return _sdk_connect(session_key, app)


def get_collection(service: ServiceType, name: str):
    return service.kvstore[name]


def query_all(collection, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    q = query or {}
    return list(collection.data.query(query=q))


def get_by_key(collection, key: str) -> Optional[Dict[str, Any]]:
    try:
        return collection.data.query_by_id(key)
    except KvError:
        raise
    except Exception as err:
        status = getattr(err, "status", None)
        if status == 404:
            return None
        raise


def insert_record(collection, record: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(record)
    data.pop("_key", None)
    new_key = collection.data.insert(data)
    stored = collection.data.query_by_id(new_key)
    if not stored:
        raise KvError("insert succeeded but record could not be read back")
    return stored


def update_record(collection, key: str, record: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(record)
    data.pop("_key", None)
    collection.data.update(key, data)
    stored = collection.data.query_by_id(key)
    if not stored:
        raise KvError(f"update succeeded but {key} could not be read back")
    return stored


def delete_record(collection, key: str) -> None:
    collection.data.delete(key)


def batch_insert(collection, records: List[Dict[str, Any]], chunk_size: int = 500) -> None:
    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        if hasattr(collection.data, "batch_save"):
            collection.data.batch_save(*chunk)
        else:
            for rec in chunk:
                insert_record(collection, rec)
