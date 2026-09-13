import os
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from exporters import ckl  # noqa: E402
from exporters.ckl import (  # noqa: E402
    ASSET_TAGS,
    STIG_INFO_NAMES,
    VULN_ATTR_ORDER,
    VULN_TRAILING,
)
from importers import xccdf  # noqa: E402

SV_CKL = Path("/home/squinlan/SourceOfFormat.ckl")


def _si_names(root):
    return [si.findtext("SID_NAME") for si in root.find(".//STIG_INFO")]


def _asset_tags(root):
    return [child.tag for child in list(root.find("ASSET"))]


def _vuln_attr_names(vuln):
    names = []
    for block in vuln.findall("STIG_DATA"):
        names.append(block.findtext("VULN_ATTRIBUTE") or "")
    return names


def _vuln_child_tags(vuln):
    return [child.tag for child in list(vuln)]


def _sample_export(**overrides):
    checklist = {
        "_key": "ck1",
        "title": "web-01 RHEL 8",
        "target_data": "{}",
    }
    baseline = {
        "_key": "b1",
        "title": "Red Hat Enterprise Linux 8 Security Technical Implementation Guide",
        "stig_name": "Red Hat Enterprise Linux 8 Security Technical Implementation Guide",
        "stig_id": "RHEL_8_STIG",
        "xccdf_benchmark_id": "RHEL_8_STIG",
        "version": "2",
        "release_info": "Release: 1 Benchmark Date: 24 Oct 2024",
        "source_uri": "U_RHEL_8_STIG_V2R1_Manual-xccdf.xml",
        "target_key": "2921",
        "description": (
            "This Security Technical Implementation Guide is published as a tool to "
            "improve the security of Department of Defense (DOD) information systems."
        ),
    }
    rules = [
        {
            "group_id": "V-230221",
            "rule_id": "SV-230221r1017040_rule",
            "rule_id_src": "SV-230221r1017040_rule",
            "rule_version": "RHEL-08-010000",
            "rule_title": "RHEL 8 must be a vendor-supported release.",
            "severity": "high",
            "group_title": "SRG-OS-000480-GPOS-00227",
            "srg_id": "SRG-OS-000480-GPOS-00227",
            "discussion": (
                "<VulnDiscussion>An operating system release is considered "
                '"supported".</VulnDiscussion><FalsePositives></FalsePositives>'
                "<Documentable>false</Documentable>"
            ),
            "check_content": "Verify the version of the operating system is vendor supported.",
            "fix_text": "Upgrade to a supported version of RHEL 8.",
            "ccis": ["CCI-000366"],
            "weight": "10.0",
        }
    ]
    reviews = {
        "V-230221": {
            "status": "not_a_finding",
            "finding_details": "Finding Details here",
            "comments": "write-probe",
        }
    }
    host = {"hostname": "web-01", "ip_address": "10.0.0.10", "fqdn": "web-01.example.com"}
    checklist.update(overrides.get("checklist", {}))
    baseline.update(overrides.get("baseline", {}))
    return ckl.export_ckl(checklist, baseline, rules, reviews, host)


class TestCklViewerAlign(unittest.TestCase):
    def test_export_matches_viewer_skeleton(self):
        xml = _sample_export()
        self.assertTrue(xml.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertIn("<!--DISA STIG Viewer :: 2.18-->", xml)
        self.assertNotIn("<HOST_MAC/>", xml)
        self.assertNotIn("Package_ID", xml)
        self.assertNotIn("<VULN_ATTRIBUTE>CCI</VULN_ATTRIBUTE>", xml)
        self.assertNotIn("<VulnDiscussion>", xml)

        root = ET.fromstring(xml)
        self.assertEqual(_asset_tags(root), list(ASSET_TAGS))
        self.assertEqual(_si_names(root), list(STIG_INFO_NAMES))
        custom = [si for si in root.find(".//STIG_INFO") if si.findtext("SID_NAME") == "customname"][0]
        self.assertIsNone(custom.find("SID_DATA"))

        vuln = root.find(".//VULN")
        children = _vuln_child_tags(vuln)
        self.assertEqual(children[: len(VULN_ATTR_ORDER)], ["STIG_DATA"] * len(VULN_ATTR_ORDER))
        self.assertEqual(children[-len(VULN_TRAILING) :], list(VULN_TRAILING))
        attrs = _vuln_attr_names(vuln)
        self.assertEqual(attrs[: len(VULN_ATTR_ORDER)], list(VULN_ATTR_ORDER))
        self.assertEqual(attrs.count("LEGACY_ID"), 2)
        self.assertIn("CCI_REF", attrs)
        self.assertEqual(vuln.findtext("STATUS"), "NotAFinding")
        discuss = None
        for block in vuln.findall("STIG_DATA"):
            if block.findtext("VULN_ATTRIBUTE") == "Vuln_Discuss":
                discuss = block.findtext("ATTRIBUTE_DATA")
        self.assertEqual(discuss, 'An operating system release is considered "supported".')
        self.assertEqual(root.findtext("ASSET/HOST_NAME"), "web-01")

    def test_stigid_and_stigref(self):
        root = ET.fromstring(_sample_export())
        info = {si.findtext("SID_NAME"): (si.findtext("SID_DATA") or "") for si in root.find(".//STIG_INFO")}
        self.assertEqual(info["stigid"], "RHEL_8_STIG")
        self.assertEqual(info["filename"], "U_RHEL_8_STIG_V2R1_Manual-xccdf.xml")
        self.assertEqual(info["notice"], "terms-of-use")
        self.assertEqual(info["source"], "STIG.DOD.MIL")
        stigref = None
        for block in root.find(".//VULN").findall("STIG_DATA"):
            if block.findtext("VULN_ATTRIBUTE") == "STIGRef":
                stigref = block.findtext("ATTRIBUTE_DATA")
        self.assertEqual(
            stigref,
            "Red Hat Enterprise Linux 8 Security Technical Implementation Guide :: "
            "Version 2, Release: 1 Benchmark Date: 24 Oct 2024",
        )

    @unittest.skipUnless(SV_CKL.is_file(), "SourceOfFormat.ckl is not in the home directory")
    def test_source_of_format_schema(self):
        viewer = ET.parse(SV_CKL).getroot()
        ours = ET.fromstring(_sample_export())
        self.assertEqual(_asset_tags(ours), _asset_tags(viewer))
        self.assertEqual(_si_names(ours), _si_names(viewer))
        v_attrs = [name for name in _vuln_attr_names(viewer.find(".//VULN")) if name not in ("LEGACY_ID", "CCI_REF")]
        o_attrs = [name for name in _vuln_attr_names(ours.find(".//VULN")) if name not in ("LEGACY_ID", "CCI_REF")]
        self.assertEqual(o_attrs, v_attrs)
        self.assertEqual(_vuln_child_tags(ours.find(".//VULN"))[-5:], _vuln_child_tags(viewer.find(".//VULN"))[-5:])


class TestXccdfCklMetadata(unittest.TestCase):
    def test_minimal_fixture_carries_ckl_metadata(self):
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml")
        with open(fixture, "rb") as handle:
            meta, rules = xccdf.parse_xccdf(handle.read(), source_uri="minimal_benchmark.xml")
        self.assertEqual(meta["source_filename"], "minimal_benchmark.xml")
        self.assertEqual(meta["notice"], "terms-of-use")
        self.assertEqual(meta["classification"], "UNCLASSIFIED")
        xml = ckl.export_ckl(
            {"_key": "c", "target_data": "{}"},
            {**meta, "_key": "b"},
            rules,
            [],
            {"hostname": "h1"},
        )
        root = ET.fromstring(xml)
        self.assertEqual(_si_names(root), list(STIG_INFO_NAMES))
        self.assertEqual(root.findtext("ASSET/HOST_NAME"), "h1")


if __name__ == "__main__":
    unittest.main()
