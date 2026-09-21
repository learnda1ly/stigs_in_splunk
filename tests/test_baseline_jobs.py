import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers.stig_zip import explore_baseline_zip, extract_baseline_xccdf  # noqa: E402
from services import baseline_jobs as jobs  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml")


def _xccdf_bytes():
    with open(FIXTURE, "rb") as handle:
        return handle.read()


def _zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buf.getvalue()


def _nested_library_zip():
    inner = _zip_bytes(
        [
            ("U_Example_STIG_V1R1_Manual-xccdf.xml", _xccdf_bytes()),
            ("U_Example_SRG_V1R1_Manual-xccdf.xml", b"<Benchmark/>"),
            ("readme.pdf", b"%PDF"),
        ]
    )
    return _zip_bytes(
        [
            ("U_STIG_Library.zip", inner),
            ("notes.txt", b"ignore"),
        ]
    )


class TestBaselineJobs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stig_jobs_")
        self.patcher = patch.object(jobs, "_jobs_root", return_value=self.tmp)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_chunk_finalize_lists_manual_xccdf(self):
        payload = _nested_library_zip()
        rec = jobs.create_job("U_Library.zip", len(payload), "admin")
        job_id = rec["job_id"]
        mid = len(payload) // 2
        jobs.append_chunk(job_id, "admin", 0, payload[:mid])
        jobs.append_chunk(job_id, "admin", mid, payload[mid:])
        listed = jobs.finalize_job(job_id, "admin")
        self.assertEqual(listed["status"], "ready")
        self.assertEqual(len(listed["found"]), 1)
        self.assertIn("Manual-xccdf.xml", listed["found"][0]["path"])
        self.assertGreater(listed["skipped"]["srg"], 0)

        xml = extract_baseline_xccdf(jobs._zip_path(job_id), listed["found"][0]["path"])
        self.assertEqual(xml, _xccdf_bytes())

    def test_rejects_offset_gap_and_oversize_zip(self):
        payload = _nested_library_zip()
        rec = jobs.create_job("lib.zip", len(payload), "admin")
        with self.assertRaises(ValueError):
            jobs.append_chunk(rec["job_id"], "admin", 1, payload[:10])
        with self.assertRaises(ValueError):
            jobs.create_job("huge.zip", jobs.MAX_ZIP_BYTES + 1, "admin")

    def test_other_user_cannot_read_job(self):
        rec = jobs.create_job("lib.zip", 8, "admin")
        jobs.append_chunk(rec["job_id"], "admin", 0, b"PK\x03\x04xxxx")
        with self.assertRaises(PermissionError):
            jobs.get_job(rec["job_id"], "other")


class TestExploreZip(unittest.TestCase):
    def test_explore_and_extract_from_path(self):
        payload = _nested_library_zip()
        fd, path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        try:
            with open(path, "wb") as handle:
                handle.write(payload)
            listed = explore_baseline_zip(path)
            self.assertEqual(len(listed["found"]), 1)
            xml = extract_baseline_xccdf(path, listed["found"][0]["path"])
            self.assertEqual(xml, _xccdf_bytes())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
