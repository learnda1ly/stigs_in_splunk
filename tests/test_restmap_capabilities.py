"""restmap.conf capability lines must match OpenAPI x-splunk-capability hints."""

from __future__ import annotations

import re
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parents[1]
RESTMAP_PATH = ROOT / "package" / "default" / "restmap.conf"
OPENAPI_PATH = ROOT / "docs" / "openapi.yaml"


def _restmap_stanza(match_path: str) -> dict[str, str]:
    text = RESTMAP_PATH.read_text(encoding="utf-8")
    stanzas = re.split(r"\n(?=\[)", text)
    for stanza in stanzas:
        if f"match = {match_path}" not in stanza:
            continue
        out: dict[str, str] = {}
        for line in stanza.splitlines():
            m = re.match(r"^capability\.(\w+)\s*=\s*(.+)$", line.strip())
            if m:
                out[m.group(1)] = m.group(2).strip()
        return out
    raise AssertionError(f"no restmap stanza for {match_path}")


def _methods_for_capability(stanza: dict[str, str], capability: str) -> set[str]:
    raw = stanza.get(capability, "")
    methods: set[str] = set()
    for part in raw.split("|"):
        part = part.strip()
        if part:
            methods.add(part.upper())
    return methods


class RestmapReviewImageCapabilitiesTests(unittest.TestCase):
    def test_review_image_delete_admits_stig_write_at_restmap(self):
        """Splunk must allow DELETE before persist handler (image remove in editor)."""
        stanza = _restmap_stanza("/stig_reviews")
        write_methods = _methods_for_capability(stanza, "stig_write")
        self.assertIn(
            "DELETE",
            write_methods,
            "stig_reviews DELETE must be on stig_write; handler only implements "
            "DELETE for /stig_reviews/{id}/images/{imageId}",
        )

    def test_openapi_delete_review_image_documents_stig_write(self):
        text = OPENAPI_PATH.read_text(encoding="utf-8")
        block = re.search(
            r"/stig_reviews/\{reviewId\}/images/\{imageId\}:.*?"
            r"operationId: deleteReviewImage.*?"
            r"x-splunk-capability:\s*(\S+)",
            text,
            flags=re.DOTALL,
        )
        self.assertTrue(block, "deleteReviewImage operation not found in openapi.yaml")
        self.assertEqual(block.group(1), "stig_write")

    def test_stig_reviews_handler_delete_only_for_images(self):
        handler = (ROOT / "package" / "bin" / "stig_rest_handler.py").read_text(
            encoding="utf-8"
        )
        reviews_block = re.search(
            r"def _reviews\((?:.|\n)*?\n    def _imports\(",
            handler,
        )
        self.assertTrue(reviews_block, "_reviews method not found")
        block = reviews_block.group(0)
        delete_sites = [
            m.start() for m in re.finditer(r'if method == "DELETE"', block)
        ]
        self.assertEqual(
            len(delete_sites),
            1,
            "expected exactly one DELETE branch in _reviews (review images only)",
        )
        self.assertIn('parts[1] == "images"', block)


if __name__ == "__main__":
    unittest.main()
