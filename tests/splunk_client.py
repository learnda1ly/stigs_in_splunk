"""Splunk integration test client using the Splunk Python SDK (splunklib)."""

from __future__ import annotations

import json
import os
import sys
import unittest
from typing import Any, Dict, Optional, Union

# Repo lib/ (vendored splunk-sdk) before bin/
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
for _sub in ("lib", os.path.join("package", "bin")):
    _path = os.path.join(_ROOT, _sub)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

import splunklib.client as client
from splunklib.binding import HTTPError


class SplunkRestError(Exception):
    def __init__(self, status: int, body: str, url: str = ""):
        super().__init__(f"HTTP {status} for {url}: {body[:500]}")
        self.status = status
        self.body = body
        self.url = url


class SplunkRestClient:
    """SDK-backed client for management REST and KV store in integration tests."""

    def __init__(
        self,
        service: client.Service,
        host: str,
        port: int,
        username: str,
        app: str = "stigs_in_splunk",
        owner: str = "nobody",
    ):
        self.service = service
        self.host = host
        self.port = port
        self.username = username
        self.app = app
        self.owner = owner

    @classmethod
    def from_env(cls) -> "SplunkRestClient":
        host = os.environ.get("SPLUNK_HOST", "127.0.0.1")
        port = int(os.environ.get("SPLUNK_PORT", "8089"))
        username = os.environ.get("SPLUNK_USERNAME", "admin")
        password = os.environ.get("SPLUNK_PASSWORD", "")
        if not password:
            raise ValueError("SPLUNK_PASSWORD is required for Splunk integration tests")
        app = os.environ.get("SPLUNK_APP", "stigs_in_splunk")
        verify = os.environ.get("SPLUNK_VERIFY_SSL", "0").lower() in ("1", "true", "yes")
        service = client.connect(
            host=host,
            port=port,
            username=username,
            password=password,
            app=app,
            owner="nobody",
            autologin=True,
            verify=verify,
        )
        return cls(service, host, port, username, app=app)

    def app_path(self, resource: str) -> str:
        resource = resource.lstrip("/")
        return f"/servicesNS/{self.owner}/{self.app}/{resource}"

    def _http(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, str]] = None,
        body: Optional[Union[bytes, str, Dict[str, Any]]] = None,
        content_type: Optional[str] = None,
    ) -> Any:
        full_path = path if path.startswith("/") else f"/{path}"
        q = dict(query or {})
        headers = []
        if content_type:
            headers.append(("Content-Type", content_type))

        payload: Optional[bytes] = None
        if isinstance(body, dict):
            payload = json.dumps(body).encode("utf-8")
            if not content_type:
                headers.append(("Content-Type", "application/json"))
        elif isinstance(body, str):
            payload = body.encode("utf-8")
        elif isinstance(body, bytes):
            payload = body

        try:
            if method.upper() == "GET":
                response = self.service.get(full_path, headers=headers, **q)
            elif method.upper() == "POST":
                response = self.service.post(
                    full_path, headers=headers, body=payload, **q
                )
            elif method.upper() == "PATCH":
                message = {"method": "PATCH", "headers": headers, "body": payload or b""}
                response = self.service.request(full_path, message)
            elif method.upper() == "DELETE":
                # splunklib passes auth via _auth_headers; do not pass headers= twice.
                response = self.service.delete(full_path, **q)
            else:
                message = {
                    "method": method.upper(),
                    "headers": headers,
                    "body": payload or b"",
                }
                response = self.service.request(full_path, message)
            return self._read_response(response)
        except HTTPError as err:
            raise SplunkRestError(
                err.status,
                str(getattr(err, "body", err)),
                full_path,
            ) from err

    @staticmethod
    def _read_response(response) -> Any:
        body = response.body.read()
        if not body:
            return None
        text = body.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        if text[0] in "{[":
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return text

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, str]] = None,
        body: Optional[Union[bytes, str, Dict[str, Any]]] = None,
        content_type: Optional[str] = None,
    ):
        result = self._http(method, path, query=query, body=body, content_type=content_type)
        return 200, result

    def get_json(self, path: str, query: Optional[Dict[str, str]] = None) -> Any:
        q = dict(query or {})
        q.setdefault("output_mode", "json")
        return self._unwrap_payload(self._http("GET", path, query=q))

    def get_app_json(self, resource: str, query: Optional[Dict[str, str]] = None) -> Any:
        return self._unwrap_payload(self._http("GET", self.app_path(resource), query=query))

    def post_app_json(self, resource: str, payload: Dict[str, Any]) -> Any:
        return self._unwrap_payload(
            self._http("POST", self.app_path(resource), body=payload)
        )

    def patch_app_json(self, resource: str, payload: Dict[str, Any]) -> Any:
        return self._unwrap_payload(
            self._http("PATCH", self.app_path(resource), body=payload)
        )

    def delete_json(self, path: str) -> Any:
        return self._unwrap_payload(self._http("DELETE", path))

    def delete_app_json(self, resource: str) -> Any:
        return self._unwrap_payload(self._http("DELETE", self.app_path(resource)))

    def post_app_raw(
        self,
        resource: str,
        data: bytes,
        content_type: str,
        query: Optional[Dict[str, str]] = None,
    ) -> Any:
        return self._unwrap_payload(
            self._http(
                "POST",
                self.app_path(resource),
                query=query,
                body=data,
                content_type=content_type,
            )
        )

    def get_app_raw(self, resource: str, query: Optional[Dict[str, str]] = None) -> str:
        body = self._http("GET", self.app_path(resource), query=query)
        if isinstance(body, str):
            return body
        if isinstance(body, dict):
            return json.dumps(body)
        return str(body)

    def kv_collection(self, name: str):
        return self.service.kvstore[name]

    @staticmethod
    def _unwrap_payload(body: Any) -> Any:
        if isinstance(body, dict) and "entry" in body and "messages" in body:
            entries = body.get("entry") or []
            if len(entries) == 1 and "content" in entries[0]:
                content = entries[0]["content"]
                if isinstance(content, dict) and "payload" in content:
                    inner = content["payload"]
                    if isinstance(inner, str):
                        try:
                            return json.loads(inner)
                        except json.JSONDecodeError:
                            return inner
                return content
        if isinstance(body, dict) and "payload" in body and len(body) == 1:
            inner = body["payload"]
            if isinstance(inner, str):
                try:
                    return json.loads(inner)
                except json.JSONDecodeError:
                    return inner
        return body


def splunk_tests_enabled() -> bool:
    if os.environ.get("SPLUNK_INTEGRATION", "").lower() in ("0", "false", "no"):
        return False
    return bool(os.environ.get("SPLUNK_PASSWORD"))


def require_splunk_client() -> SplunkRestClient:
    if not splunk_tests_enabled():
        raise unittest.SkipTest(
            "Set SPLUNK_PASSWORD (and install the app) to run Splunk integration tests"
        )
    try:
        return SplunkRestClient.from_env()
    except ValueError as exc:
        raise unittest.SkipTest(str(exc)) from exc
