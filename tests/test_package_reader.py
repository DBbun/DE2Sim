from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from de2sim.ingest.package_reader import PackageValidationError, ingest_engineering_package


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


class PackageReaderTests(unittest.TestCase):
    def make_zip(self, path: Path, members: dict[str, bytes]) -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
            for name, data in members.items():
                zf.writestr(name, data)

    def read_manifest(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_valid_minimal_zip_and_manifest_hashes(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            output = root / "out"
            members = {
                "geometry/body.glb": b"glb-bytes",
                "requirements/reqs.csv": b"id,text\nR1,Fly\n",
                "misc/unknown.bin": b"\x00\x01",
            }
            self.make_zip(package, members)

            manifest_path = ingest_engineering_package(package, output)
            manifest = self.read_manifest(manifest_path)

            self.assertEqual(manifest_path, output / "package_manifest.json")
            self.assertEqual(manifest["schema_version"], "de2sim.package_manifest.v1")
            self.assertEqual(manifest["package_filename"], "package.zip")
            self.assertEqual(manifest["package_sha256"], hashlib.sha256(package.read_bytes()).hexdigest())
            self.assertEqual(manifest["extraction_root"], "work/package")
            self.assertEqual(manifest["file_count"], 3)
            self.assertEqual([item["relative_path"] for item in manifest["files"]], sorted(members))

            by_path = {item["relative_path"]: item for item in manifest["files"]}
            self.assertEqual(by_path["geometry/body.glb"]["role"], "geometry")
            self.assertEqual(by_path["geometry/body.glb"]["parser_status"], "referenced_not_parsed")
            self.assertEqual(by_path["requirements/reqs.csv"]["role"], "requirements")
            self.assertEqual(by_path["misc/unknown.bin"]["role"], "unsupported")
            self.assertEqual(by_path["misc/unknown.bin"]["parser_status"], "unsupported")
            for relative_path, data in members.items():
                self.assertEqual(by_path[relative_path]["sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(by_path[relative_path]["size_bytes"], len(data))

    def test_cli_success_prints_manifest_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            output = root / "out"
            self.make_zip(package, {"parameters/config.json": b'{"mass": 12}'})

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "de2sim.cli.challenge_pipeline",
                    "--engineering-package",
                    str(package),
                    "--output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(output / "package_manifest.json"))
            self.assertTrue((output / "package_manifest.json").is_file())

    def test_deterministic_manifest_ordering(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            self.make_zip(
                package,
                {
                    "zeta.txt": b"z",
                    "alpha.txt": b"a",
                    "geometry/part.stl": b"solid x",
                },
            )

            first = self.read_manifest(ingest_engineering_package(package, root / "out1"))
            second = self.read_manifest(ingest_engineering_package(package, root / "out2"))

            first_paths = [item["relative_path"] for item in first["files"]]
            second_paths = [item["relative_path"] for item in second["files"]]
            self.assertEqual(first_paths, ["alpha.txt", "geometry/part.stl", "zeta.txt"])
            self.assertEqual(first_paths, second_paths)

    def test_invalid_zip_is_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            package.write_bytes(b"definitely not a zip")
            with self.assertRaisesRegex(PackageValidationError, "valid ZIP"):
                ingest_engineering_package(package, root / "out")

    def test_nonexistent_zip_is_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(PackageValidationError, "does not exist"):
                ingest_engineering_package(root / "missing.zip", root / "out")

    def test_wrong_extension_is_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.txt"
            self.make_zip(package, {"file.txt": b"text"})
            with self.assertRaisesRegex(PackageValidationError, r"\.zip extension"):
                ingest_engineering_package(package, root / "out")

    def test_absolute_archive_path_rejection(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            self.make_zip(package, {"/absolute.txt": b"bad"})
            with self.assertRaisesRegex(PackageValidationError, "absolute"):
                ingest_engineering_package(package, root / "out")

    def test_path_traversal_rejection(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            self.make_zip(package, {"../evil.txt": b"bad"})
            with self.assertRaisesRegex(PackageValidationError, "path traversal"):
                ingest_engineering_package(package, root / "out")

    def test_extraction_outside_destination_rejection(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            self.make_zip(package, {"..\\evil.txt": b"bad"})
            with self.assertRaisesRegex(PackageValidationError, "path traversal|outside the extraction directory"):
                ingest_engineering_package(package, root / "out")

    def test_symbolic_link_like_entry_rejection(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            info = zipfile.ZipInfo("link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(package, "w") as zf:
                zf.writestr(info, "target")
            with self.assertRaisesRegex(PackageValidationError, "symbolic link"):
                ingest_engineering_package(package, root / "out")

    def test_nonempty_extraction_directory_rejection(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            output = root / "out"
            existing = output / "work" / "package"
            existing.mkdir(parents=True)
            (existing / "old.txt").write_text("old", encoding="utf-8")
            self.make_zip(package, {"file.txt": b"text"})

            with self.assertRaisesRegex(PackageValidationError, "already exists and is not empty"):
                ingest_engineering_package(package, output)


if __name__ == "__main__":
    unittest.main()
