#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from release_product_sdks import (
    Baseline,
    Plan,
    ReleaseError,
    collect_release_notes,
    export_go,
    export_python,
    normalize_version,
    parse_metadata,
    release_commit_message,
    replace_target_tree,
)


class ExportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "source"
        self.root.mkdir()
        for directory in (
            "sdk/testdata",
            "sdk/proto/product",
            "sdk/docs",
            "docs/iam",
            "sdk/public-release/python-sdk/.github/workflows",
            "sdk/public-release/go-sdk/.github/workflows",
        ):
            (self.root / directory).mkdir(parents=True)
        (self.root / "sdk/testdata/example.json").write_text("{}")
        (self.root / "sdk/proto/product/example.proto").write_text(
            'option go_package = "github.com/matrixorigin/matrixflow/sdk/product-model/product";'
        )
        (self.root / "sdk/docs/product-sdk-capabilities.md").write_text("capabilities")
        (self.root / "docs/iam/07-public-api-frontend-sdk-contracts.md").write_text("IAM")
        for kind in ("python-sdk", "go-sdk"):
            (self.root / f"sdk/public-release/{kind}/.github/workflows/sdk-ci.yml").write_text("name: CI")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_python_export_contains_runtime_and_fixture_dependencies(self) -> None:
        package = self.root / "sdk/python-sdk"
        (package / "moi_product_sdk").mkdir(parents=True)
        (package / "tests").mkdir()
        (package / "pyproject.toml").write_text(
            '[project]\nname = "moi-product-sdk"\nversion = "0.1.0"\n'
        )
        (package / "README.md").write_text("../docs/product-sdk-capabilities.md")
        original = (package / "moi_product_sdk/client.py")
        original.write_text("CLIENT = True\n")
        (package / "tests/test_fixture.py").write_text(
            'from pathlib import Path\n'
            'one = Path(__file__).resolve().parents[2] / "testdata/example.json"\n'
            'two = Path("../testdata/example.json")\n'
        )
        output = Path(self.temporary.name) / "python-output"
        output.mkdir()

        self.assertEqual("0.1.0", export_python(self.root, output))

        self.assertEqual("CLIENT = True\n", original.read_text())
        self.assertEqual("CLIENT = True\n", (output / "moi_product_sdk/client.py").read_text())
        self.assertEqual("{}", (output / "testdata/example.json").read_text())
        rewritten = (output / "tests/test_fixture.py").read_text()
        self.assertIn("parents[1]", rewritten)
        self.assertNotIn("parents[2]", rewritten)
        self.assertIn('Path("testdata/example.json")', rewritten)
        self.assertEqual("docs/product-sdk-capabilities.md", (output / "README.md").read_text())
        self.assertTrue((output / ".github/workflows/sdk-ci.yml").is_file())

    def test_go_export_is_one_public_module_without_local_replace(self) -> None:
        package = self.root / "sdk/go-sdk"
        package.mkdir(parents=True)
        (package / "go.mod").write_text(
            "module github.com/matrixorigin/matrixflow/sdk/go-sdk\n\n"
            "go 1.25.7\n\n"
            "require github.com/matrixorigin/matrixflow/sdk/product-model v0.0.0\n\n"
            "replace github.com/matrixorigin/matrixflow/sdk/product-model => ../product-model\n"
        )
        (package / "go.sum").write_text("")
        (package / "client.go").write_text(
            'package sdk\nimport product "github.com/matrixorigin/matrixflow/sdk/product-model/product"\n'
        )
        (package / "client_test.go").write_text(
            'package sdk\nimport "os"\nvar _ = os.ReadFile("../testdata/example.json")\n'
        )
        (package / "README.md").write_text("github.com/matrixorigin/matrixflow/sdk/go-sdk")
        model = self.root / "sdk/product-model/product"
        model.mkdir(parents=True)
        (model / "model.pb.go").write_text("package product\n")
        output = Path(self.temporary.name) / "go-output"
        output.mkdir()

        export_go(self.root, output, "github.com/example/moi-go-sdk")

        module = (output / "go.mod").read_text()
        self.assertIn("module github.com/example/moi-go-sdk", module)
        self.assertNotIn("replace", module)
        self.assertNotIn("matrixflow/sdk/product-model v", module)
        self.assertIn(
            'product "github.com/example/moi-go-sdk/product"',
            (output / "client.go").read_text(),
        )
        self.assertIn('os.ReadFile("testdata/example.json")', (output / "client_test.go").read_text())
        self.assertIn(
            'option go_package = "github.com/example/moi-go-sdk/product"',
            (output / "proto/product/example.proto").read_text(),
        )
        self.assertTrue((output / "product/model.pb.go").is_file())
        self.assertTrue((output / "testdata/example.json").is_file())

    def test_legacy_archive_is_preserved_during_later_exports(self) -> None:
        target = Path(self.temporary.name) / "target"
        target.mkdir()
        (target / ".git").mkdir()
        (target / "old.txt").write_text("old")
        first = Path(self.temporary.name) / "first"
        first.mkdir()
        (first / "sdk.txt").write_text("one")
        replace_target_tree(target, first, archive_legacy=True)
        self.assertEqual("old", (target / "legacy/old.txt").read_text())
        self.assertEqual("one", (target / "sdk.txt").read_text())
        second = Path(self.temporary.name) / "second"
        second.mkdir()
        (second / "sdk.txt").write_text("two")
        replace_target_tree(target, second, archive_legacy=False)
        self.assertEqual("old", (target / "legacy/old.txt").read_text())
        self.assertEqual("two", (target / "sdk.txt").read_text())


class ReleaseNotesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        sdk = self.root / "sdk/python-sdk"
        sdk.mkdir(parents=True)
        self.file = sdk / "client.py"
        self.file.write_text("one")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "chore: baseline"], cwd=self.root, check=True)
        self.baseline_sha = self.head()
        self.file.write_text("two")
        subprocess.run(["git", "commit", "-qam", "feat: add knowledge search (#12)"], cwd=self.root, check=True)
        self.file.write_text("three")
        subprocess.run(["git", "commit", "-qam", "fix: preserve pagination cursor (#13)"], cwd=self.root, check=True)
        (self.root / "sdk/python-sdk/internal.txt").write_text("internal")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qam", "chore: update build metadata (#14)"], cwd=self.root, check=True)
        self.source_sha = self.head()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def head(self) -> str:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout.strip()

    def plan(self) -> Plan:
        return Plan(
            kind="Python",
            repository="example/moi-python-sdk",
            version="0.2.0",
            export_dir=self.root,
            module_path=None,
            manual_notes="",
            baseline=Baseline("v0.1.0", "0.1.0", self.baseline_sha),
        )

    def test_notes_cover_only_changes_since_previous_export(self) -> None:
        notes = collect_release_notes(
            self.root, "example/matrixflow", self.source_sha, "5.2.3", self.plan()
        )
        self.assertIn("Added", notes)
        self.assertIn("add knowledge search", notes)
        self.assertIn("preserve pagination cursor", notes)
        self.assertIn("https://github.com/example/matrixflow/pull/12", notes)
        self.assertNotIn("update build metadata", notes)
        self.assertNotIn("chore: baseline", notes)
        self.assertIn(f"compare/{self.baseline_sha}...{self.source_sha}", notes)

    def test_manual_notes_replace_generated_body_but_keep_provenance(self) -> None:
        plan = self.plan()
        plan.manual_notes = "## Upgrade\n\nRead the migration guide."
        notes = collect_release_notes(
            self.root, "example/matrixflow", self.source_sha, "5.2.3", plan
        )
        self.assertTrue(notes.startswith("## Upgrade"))
        self.assertNotIn("add knowledge search", notes)
        self.assertIn(self.source_sha[:12], notes)
        self.assertIn("5.2.3", notes)

    def test_export_metadata_round_trip(self) -> None:
        message = release_commit_message(self.plan(), self.source_sha, "5.2.3")
        metadata = parse_metadata(message)
        self.assertEqual(self.source_sha, metadata.source_sha)
        self.assertEqual("0.2.0", metadata.version)
        self.assertEqual("5.2.3", metadata.product_version)


class VersionTest(unittest.TestCase):
    def test_stable_semver_is_required(self) -> None:
        self.assertEqual("0.1.0", normalize_version("v0.1.0", "version"))
        for value in ("1.0", "1.0.0-dev", "latest", "1.0.0;echo no"):
            with self.subTest(value=value), self.assertRaises(ReleaseError):
                normalize_version(value, "version")


if __name__ == "__main__":
    unittest.main()
