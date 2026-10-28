from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from senpilot.__main__ import main as retrieve_main
from senpilot.package import main as package_main
from senpilot.packaging import PackagingError, package_report


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "files").mkdir()
        self.report_path = self.root / "report.json"
        self.report = {
            "status": "complete", "request": {"matter": "M12205", "category": "Other Documents", "limit": 10},
            "matter": {"matter_number": "M12205", "title": "Test matter", "category_counts": {"Other Documents": 2}},
            "downloads": [], "catalog": [], "downloaded_count": 0, "goal_met": True,
            "failures": [], "unavailable": [],
        }
        for index in range(2):
            payload = bytes([index]) * (1024 * 1024 + 17)
            relative = f"files/{index}_same_name.pdf"
            (self.root / relative).write_bytes(payload)
            self.report["downloads"].append({
                "document_key": str(index), "original_filename": "same name.pdf", "local_path": relative,
                "validation": {"bytes": len(payload), "sha256": sha256(payload).hexdigest()},
            })
            self.report["catalog"].append({"document_key": str(index), "title": f"Filing {index}", "date": None})
        self.report["downloaded_count"] = 2
        self.save()

    def save(self):
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")

    def test_archive_preserves_bytes_metadata_and_original_name_collisions(self):
        original_report = self.report_path.read_bytes()
        (self.root / "files" / "unlisted.pdf").write_bytes(b"must not be included")
        (self.root / "incomplete").mkdir()
        (self.root / "incomplete" / "partial.part").write_bytes(b"unfinished")
        result = package_report(self.report_path)
        self.assertEqual(result["status"], "ready")
        path = self.root / "package" / "documents.zip"
        self.assertEqual(result["archive"]["bytes"], path.stat().st_size)
        self.assertEqual(result["archive"]["sha256"], sha256(path.read_bytes()).hexdigest())
        self.assertEqual(result["archive"]["document_count"], 2)
        self.assertEqual(result["archive"]["entry_count"], 3)
        self.assertTrue(result["archive"]["verified"])
        with ZipFile(path) as archive:
            self.assertEqual(archive.namelist(), ["manifest.json", "files/0_same_name.pdf", "files/1_same_name.pdf"])
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["matter"], self.report["matter"])
            for item in manifest["files"]:
                self.assertEqual(item["original_filename"], "same name.pdf")
                self.assertEqual(archive.read(item["archive_path"]), (self.root / item["local_path"]).read_bytes())
                self.assertIn("title", item["source"])
        self.assertEqual(self.report_path.read_bytes(), original_report)

    def test_partial_and_interrupted_results_keep_failures_and_warnings(self):
        for status in ("partial", "error", "interrupted"):
            with self.subTest(status=status):
                self.report["status"] = status
                self.report["goal_met"] = False
                self.report["failures"] = [{"document_key": "failed", "error": "Transfer timed out"}]
                self.report["unavailable"] = [{"security": "Confidential"}]
                self.report["downloads"][0]["validation"]["warning"] = "Source WAV header mismatch"
                self.save()
                result = package_report(self.report_path, self.root / status)
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["source_status"], status)
                manifest = result["manifest"]
                self.assertFalse(manifest["goal_met"])
                self.assertEqual(manifest["failures"], self.report["failures"])
                self.assertEqual(manifest["unavailable"], self.report["unavailable"])
                self.assertIn("warning", manifest["files"][0]["validation"])

    def test_no_files_gets_summary_without_an_empty_zip(self):
        for status in ("empty", "unavailable", "metadata_only", "not_found", "partial", "error"):
            with self.subTest(status=status):
                self.report.update(status=status, downloads=[], downloaded_count=0)
                self.save()
                output = self.root / status
                result = package_report(self.report_path, output)
                self.assertEqual(result["status"], "no_files")
                self.assertEqual(result["source_status"], status)
                self.assertIsNone(result["archive"])
                self.assertEqual(list(output.iterdir()), [output / "package.json"])

    def test_changed_or_missing_files_never_publish_an_archive(self):
        path = self.root / self.report["downloads"][0]["local_path"]
        for kind in ("changed", "missing"):
            with self.subTest(kind=kind):
                if kind == "changed":
                    payload = path.read_bytes()
                    path.write_bytes(b"x" + payload[1:])  # Same size, different hash.
                else:
                    path.unlink()
                output = self.root / kind
                with self.assertRaises(PackagingError):
                    package_report(self.report_path, output)
                self.assertEqual(json.loads((output / "package.json").read_text())["status"], "error")
                self.assertFalse((output / "documents.zip").exists())
                self.assertFalse((output / "documents.zip.part").exists())

    def test_unsafe_report_paths_are_rejected(self):
        for relative in ("../outside.pdf", "files/../outside.pdf", "files/sub/file.pdf",
                         "C:/outside.pdf", "files\\file.pdf", "/files/file.pdf", "files/./file.pdf",
                         "files/null\0.pdf", "files/trailing.pdf.", "files/stream:alternate"):
            with self.subTest(relative=relative):
                self.report["downloads"][0]["local_path"] = relative
                self.save()
                with self.assertRaises(PackagingError):
                    package_report(self.report_path)
                self.assertFalse((self.root / "package").exists())

    def test_file_symlink_cannot_escape_the_retrieval(self):
        path = self.root / self.report["downloads"][0]["local_path"]
        outside = self.root / "outside.pdf"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        try:
            path.symlink_to(outside)
        except OSError:
            self.skipTest("Creating symbolic links requires Windows developer mode or privilege")
        with self.assertRaises(PackagingError):
            package_report(self.report_path)

    def test_duplicate_paths_identities_and_invalid_counts_are_rejected(self):
        original = deepcopy(self.report)
        for kind in ("path", "identity", "catalog_identity", "count", "cap", "running"):
            with self.subTest(kind=kind):
                self.report = deepcopy(original)
                if kind == "path":
                    self.report["downloads"][1]["local_path"] = "files/0_SAME_NAME.PDF"
                elif kind == "identity":
                    self.report["downloads"][1]["document_key"] = "0"
                elif kind == "catalog_identity":
                    self.report["catalog"].append(self.report["catalog"][0])
                elif kind == "count":
                    self.report["downloaded_count"] = 1
                elif kind == "cap":
                    self.report["downloads"] *= 6
                    self.report["downloaded_count"] = 12
                else:
                    self.report["status"] = "running"
                self.save()
                with self.assertRaises(PackagingError):
                    package_report(self.report_path)

    def test_existing_package_is_not_overwritten(self):
        package_report(self.report_path)
        path = self.root / "package" / "documents.zip"
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            package_report(self.report_path)
        self.assertEqual(path.read_bytes(), original)

    def test_readback_detects_a_valid_zip_with_wrong_file_contents(self):
        def corrupt(path, root, manifest, contents):
            with ZipFile(path, "w") as archive:
                archive.writestr("manifest.json", contents)
                for item in manifest["files"]:
                    archive.writestr(item["archive_path"], b"wrong bytes with a valid CRC")
        with patch("senpilot.packaging.write_archive", side_effect=corrupt):
            with self.assertRaisesRegex(PackagingError, "verification failed"):
                package_report(self.report_path)
        self.assertFalse((self.root / "package" / "documents.zip").exists())

    def test_package_cli_preserves_partial_exit_status(self):
        self.report["status"] = "partial"
        self.save()
        with patch("sys.argv", ["senpilot.package", str(self.report_path)]), redirect_stdout(StringIO()):
            self.assertEqual(package_main(), 2)
        with patch("sys.argv", ["senpilot.package", str(self.report_path)]), redirect_stderr(StringIO()):
            self.assertEqual(package_main(), 2)  # Existing output is refused.

    def test_retrieval_cli_packages_its_saved_report(self):
        target = self.root / "retrieved"
        def retrieve(matter, category, output, limit, progress):
            self.assertEqual(output, target)
            self.assertEqual((matter, category, limit), ("M12205", "Other Documents", 10))
            shutil.copytree(self.root / "files", output / "files")
            (output / "report.json").write_text(json.dumps(self.report), encoding="utf-8")
            return self.report
        with patch("senpilot.__main__.retrieve", side_effect=retrieve), \
                patch("sys.argv", ["senpilot", "M12205", "Other Documents", "--output", str(target)]), \
                redirect_stdout(StringIO()):
            self.assertEqual(retrieve_main(), 0)
        self.assertTrue((target / "package" / "documents.zip").is_file())


if __name__ == "__main__":
    unittest.main()
