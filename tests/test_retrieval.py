from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from pypdf import PdfWriter

from senpilot.catalog import parse_row
from senpilot.files import safe_filename, unique_path, validate_file
from senpilot.models import Document, DownloadError, identify_occurrences, selection_order
from senpilot.retrieval import collect_files


def entry(number, *, date="04/07/2025", security="Public", category="Other Documents", title="Filing"):
    return Document(category, number, str(number), title, date, security, ".pdf", {})


class SelectionTests(unittest.TestCase):
    def test_identity_ignores_recycled_row_position(self):
        document = entry(1)
        self.assertEqual(document.key, replace(document, position=99).key)
        self.assertNotEqual(document.key, replace(document, title="Different filing").key)

    def test_order_is_independent_of_viewport_and_missing_dates_come_last(self):
        older, newer, missing = entry(1), entry(2, date="05/01/2025"), entry(3, date=None)
        self.assertEqual(selection_order([missing, older, newer]), [newer, older, missing])
        self.assertEqual(selection_order([newer, missing, older]), [newer, older, missing])

    def test_security_uses_the_label_instead_of_title_words(self):
        self.assertTrue(entry(1, title="Confidentiality Undertaking").available)
        self.assertFalse(entry(2, security="Confidential", title="Public exhibit").available)
        self.assertFalse(entry(3, security=None).available)
        self.assertTrue(entry(4, security=None, category="Recordings").available)

    def test_limit_applies_to_successes_and_never_exceeds_ten(self):
        documents = [entry(number) for number in range(20)]
        documents[0] = replace(documents[0], security="Confidential")
        report = {"downloads": [], "failures": [], "downloaded_count": 0}
        calls = []
        def download(document):
            calls.append(document.source_id)
            if len(calls) == 1:
                raise DownloadError("The first available file failed")
            return {"document_key": document.key}
        collect_files(documents, 10, download, report, lambda: None)
        self.assertEqual(len(calls), 11)
        self.assertEqual(report["downloaded_count"], 10)
        self.assertEqual(len(report["failures"]), 1)
        self.assertEqual(len(report["unavailable"]), 1)
        self.assertNotIn("0", calls)
        self.assertTrue(report["goal_met"])

    def test_short_empty_and_unavailable_categories_are_distinct(self):
        for documents, count, status in [([entry(1), entry(2)], 2, "complete"),
                                         ([], 0, "empty"),
                                         ([entry(1, security="Confidential")], 0, "unavailable")]:
            with self.subTest(status=status):
                report = {"downloads": [], "failures": [], "downloaded_count": 0}
                collect_files(documents, 10, lambda document: {"key": document.key}, report, lambda: None)
                self.assertEqual(report["downloaded_count"], count)
                self.assertEqual(report["status"], status)

    def test_metadata_only_never_calls_the_downloader(self):
        report = {"downloads": [], "failures": [], "downloaded_count": 0}
        collect_files([entry(1)], 0, lambda _: self.fail("Unexpected download"), report, lambda: None)
        self.assertEqual(report["status"], "metadata_only")

    def test_invalid_limit_is_rejected_before_downloading(self):
        for limit in [-1, 11]:
            with self.assertRaises(ValueError):
                collect_files([entry(1)], limit, lambda _: self.fail("Unexpected download"), {}, lambda: None)

    def test_source_format_warning_does_not_hide_a_completed_download(self):
        report = {"downloads": [], "failures": [], "downloaded_count": 0}
        collect_files([entry(1)], 1, lambda _: {"validation": {"warning": "Source header mismatch"}},
                      report, lambda: None)
        self.assertEqual(report["downloaded_count"], 1)
        self.assertEqual(report["validation_warning_count"], 1)
        self.assertEqual(report["status"], "complete")

    def test_transcript_repeating_fields_keep_evening_session_in_identity(self):
        raw = {"position": 1, "fields": {"201.1": "09/12/2022", "202.1": "September 12, 2022",
                                          "202.2": "Evening Session", "202.3": "Pdf", "204.1": "Public"}}
        document = parse_row("Transcripts", raw)
        self.assertEqual(document.title, "September 12, 2022 Evening Session")
        self.assertEqual(document.extension, ".pdf")
        self.assertIsNone(document.source_id)

    def test_identical_recording_labels_remain_separate_source_entries(self):
        first = entry(1, category="Recordings", security=None)
        second = replace(first, position=17)
        documents = identify_occurrences([first, second])
        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[0].fingerprint, documents[1].fingerprint)
        self.assertNotEqual(documents[0].key, documents[1].key)
        self.assertEqual([doc.occurrence for doc in documents], [1, 2])


class FileTests(unittest.TestCase):
    def test_wav_format_is_detected_and_source_header_mismatch_is_reported(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recording.part"
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b"\0\0" * 1600)
            result = validate_file(path, "recording.mp3", "M10431")
            self.assertEqual(result["kind"], "wav")
            self.assertTrue(result["extension_mismatch"])
            path.write_bytes(path.read_bytes()[:-100])
            inconsistent = validate_file(path, "recording.mp3", "M10431")
            self.assertFalse(inconsistent["header_length_consistent"])
            self.assertIsNone(inconsistent["duration_seconds"])
            self.assertIn("warning", inconsistent)

    def test_source_names_cannot_escape_the_output_directory(self):
        for source in ["../../letter.pdf", r"C:\private\letter.pdf", "../.."]:
            name = safe_filename(source)
            self.assertNotIn("/", name)
            self.assertNotIn("\\", name)
            self.assertNotIn(name, {".", "..", ""})
        self.assertTrue(safe_filename("a" * 300 + ".pdf").endswith(".pdf"))

    def test_normalized_name_collisions_preserve_both_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = unique_path(root, "filing,a.pdf")
            first.write_bytes(b"original")
            second = unique_path(root, "filing?a.pdf")
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), b"original")

    def test_empty_or_html_disguised_as_pdf_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "download.part"
            for payload in [b"", b"<html>Server error</html>", b"not a PDF"]:
                path.write_bytes(payload)
                with self.assertRaises(DownloadError):
                    validate_file(path, "filing.pdf", "M12205")

    def test_valid_pdf_without_extractable_matter_text_is_not_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "download.part"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.write(path)
            validation = validate_file(path, "filing.pdf", "M12205")
            self.assertEqual(validation["pages"], 1)
            self.assertFalse(validation["matter_marker_on_first_page"])


if __name__ == "__main__":
    unittest.main()
