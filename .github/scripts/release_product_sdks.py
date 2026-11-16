#!/usr/bin/env python3
"""Export and release the MOI Product Python and Go SDKs.

The source checkout is never modified. Target files are exported into temporary
locations, validated, and only then published through pull requests.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.parse


SOURCE_GO_MODULE = "github.com/matrixorigin/matrixflow/sdk/go-sdk"
SOURCE_MODEL_MODULE = "github.com/matrixorigin/matrixflow/sdk/product-model"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
METADATA_SOURCE = re.compile(r"^Moi-Source-Sha: ([0-9a-f]{40})$", re.MULTILINE)
METADATA_VERSION = re.compile(r"^Moi-Sdk-Version: ([0-9]+\.[0-9]+\.[0-9]+)$", re.MULTILINE)
METADATA_PRODUCT = re.compile(r"^Moi-Product-Version: (.+)$", re.MULTILINE)


class ReleaseError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Metadata:
    source_sha: str | None
    version: str | None
    product_version: str | None


@dataclasses.dataclass(frozen=True)
class Baseline:
    tag: str
    version: str
    source_sha: str


@dataclasses.dataclass
class Plan:
    kind: str
    repository: str
    version: str
    export_dir: Path
    module_path: str | None
    manual_notes: str
    baseline: Baseline | None = None
    notes: str = ""
    result: dict[str, object] = dataclasses.field(default_factory=dict)

    @property
    def tag(self) -> str:
        return f"v{self.version}"


def run(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        arguments,
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
    )
    if process.returncode:
        command = " ".join(arguments)
        detail = process.stderr.strip() or process.stdout.strip()
        raise ReleaseError(f"command failed ({command}): {detail}")
    return process


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise ReleaseError(f"required export directory is missing: {source}")
    shutil.copytree(source, destination, dirs_exist_ok=True)


def replace_in_file(path: Path, replacements: dict[str, str]) -> None:
    content = path.read_text(encoding="utf-8")
    for old, new in replacements.items():
        content = content.replace(old, new)
    path.write_text(content, encoding="utf-8")


def copy_common_sources(source_root: Path, output: Path) -> None:
    copy_tree(source_root / "sdk/testdata", output / "testdata")
    copy_tree(source_root / "sdk/proto/product", output / "proto/product")
    (output / "docs").mkdir(parents=True, exist_ok=True)
    capability_doc = source_root / "sdk/docs/product-sdk-capabilities.md"
    if not capability_doc.is_file():
        raise ReleaseError(f"required SDK document is missing: {capability_doc}")
    shutil.copy2(capability_doc, output / "docs/product-sdk-capabilities.md")
    iam_doc = source_root / "docs/iam/07-public-api-frontend-sdk-contracts.md"
    if not iam_doc.is_file():
        raise ReleaseError(f"required SDK document is missing: {iam_doc}")
    (output / "docs/iam").mkdir(parents=True, exist_ok=True)
    shutil.copy2(iam_doc, output / "docs/iam/07-public-api-frontend-sdk-contracts.md")


def rewrite_public_documentation(output: Path) -> None:
    for path in output.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".go"} and "legacy" not in path.parts:
            replace_in_file(
                path,
                {
                    "../../docs/": "docs/",
                    "../docs/": "docs/",
                    "../proto/": "proto/",
                },
            )


def export_python(source_root: Path, output: Path) -> str:
    copy_tree(source_root / "sdk/python-sdk", output)
    copy_common_sources(source_root, output)
    for test in (output / "tests").glob("*.py"):
        replace_in_file(
            test,
            {
                "parents[2]": "parents[1]",
                'Path("../testdata/': 'Path("testdata/',
                "Path('../testdata/": "Path('testdata/",
            },
        )
    rewrite_public_documentation(output)
    copy_tree(source_root / "sdk/public-release/python-sdk", output)
    return read_python_version(output)


def export_go(source_root: Path, output: Path, module_path: str) -> None:
    if not module_path.startswith("github.com/") or module_path.endswith("/"):
        raise ReleaseError(f"invalid public Go module path: {module_path}")
    copy_tree(source_root / "sdk/go-sdk", output)
    copy_tree(source_root / "sdk/product-model/product", output / "product")
    copy_common_sources(source_root, output)
    run(
        [
            "go",
            "mod",
            "edit",
            f"-module={module_path}",
            f"-droprequire={SOURCE_MODEL_MODULE}",
            f"-dropreplace={SOURCE_MODEL_MODULE}",
        ],
        cwd=output,
    )
    for path in output.iterdir():
        if path.is_file() and path.suffix in {".go", ".md"}:
            replace_in_file(
                path,
                {
                    SOURCE_MODEL_MODULE + "/product": module_path + "/product",
                    SOURCE_GO_MODULE: module_path,
                },
            )
    for test in output.glob("*_test.go"):
        replace_in_file(test, {'"../testdata/': '"testdata/'})
    for proto in (output / "proto/product").glob("*.proto"):
        replace_in_file(proto, {SOURCE_MODEL_MODULE + "/product": module_path + "/product"})
    rewrite_public_documentation(output)
    copy_tree(source_root / "sdk/public-release/go-sdk", output)


def read_python_version(export_dir: Path) -> str:
    with (export_dir / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    return normalize_version(project["version"], "Python project version")


def normalize_version(value: str, field: str) -> str:
    normalized = value.strip()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    if not SEMVER.fullmatch(normalized):
        raise ReleaseError(f"{field} must be stable x.y.z SemVer, got: {value!r}")
    return normalized


def version_key(value: str) -> tuple[int, int, int]:
    major, minor, patch = SEMVER.fullmatch(value).groups()
    return int(major), int(minor), int(patch)


def parse_metadata(message: str) -> Metadata:
    source = METADATA_SOURCE.search(message)
    version = METADATA_VERSION.search(message)
    product = METADATA_PRODUCT.search(message)
    return Metadata(
        source_sha=source.group(1) if source else None,
        version=version.group(1) if version else None,
        product_version=product.group(1).strip() if product else None,
    )


def release_commit_message(plan: Plan, source_sha: str, product_version: str) -> str:
    return (
        f"release: {plan.kind} SDK {plan.tag}\n\n"
        f"Moi-Source-Sha: {source_sha}\n"
        f"Moi-Sdk-Version: {plan.version}\n"
        f"Moi-Product-Version: {product_version}\n"
    )


def release_footer(source_repository: str, source_sha: str, product_version: str) -> str:
    return (
        "\n\n---\n"
        f"MOI source: [`{source_sha[:12]}`](https://github.com/{source_repository}/commit/{source_sha})  \n"
        f"MOI product version: `{product_version}`"
    )


def clean_change_subject(subject: str) -> tuple[str, str, int | None]:
    match = re.search(r"\s+\(#(\d+)\)\s*$", subject)
    number = int(match.group(1)) if match else None
    if match:
        subject = subject[: match.start()]
    kind_match = re.match(r"^([A-Za-z]+)(?:\([^)]*\))?!?:\s+", subject)
    kind = kind_match.group(1).lower() if kind_match else ""
    if kind_match:
        subject = subject[kind_match.end() :]
    subject = subject.strip()
    if not subject:
        raise ReleaseError("cannot generate Release Notes from an empty commit subject")
    return kind, subject, number


def collect_release_notes(
    source_root: Path,
    source_repository: str,
    source_sha: str,
    product_version: str,
    plan: Plan,
) -> str:
    if plan.manual_notes.strip():
        return plan.manual_notes.strip() + release_footer(source_repository, source_sha, product_version)
    if plan.baseline is None:
        body = f"## Initial release\n\nFirst public release of the MOI Product {plan.kind} SDK."
        return body + release_footer(source_repository, source_sha, product_version)
    previous = plan.baseline.source_sha
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", previous, source_sha],
        cwd=source_root,
    )
    if ancestry.returncode:
        raise ReleaseError(
            f"{plan.repository} baseline {previous} is not an ancestor of {source_sha}"
        )
    paths = ["sdk/python-sdk", "sdk/testdata", "sdk/proto/product", "sdk/docs"]
    if plan.kind == "Go":
        paths = ["sdk/go-sdk", "sdk/product-model", *paths]
    log = run(
        ["git", "log", "--reverse", "--format=%s", f"{previous}..{source_sha}", "--", *paths],
        cwd=source_root,
    ).stdout
    sections: dict[str, list[str]] = {
        "Added": [],
        "Fixed": [],
        "Changed": [],
        "Documentation": [],
        "Other changes": [],
    }
    kinds = {
        "feat": "Added",
        "fix": "Fixed",
        "perf": "Changed",
        "refactor": "Changed",
        "revert": "Changed",
        "docs": "Documentation",
    }
    for line in log.splitlines():
        kind, subject, number = clean_change_subject(line)
        if kind in {"chore", "ci", "test", "build"}:
            continue
        if number is not None:
            subject += f" ([#{number}](https://github.com/{source_repository}/pull/{number}))"
        sections[kinds.get(kind, "Other changes")].append(subject)
    parts = [f"## Changes from {plan.baseline.tag}"]
    for heading, entries in sections.items():
        if entries:
            parts.append(heading)
            parts.extend(f"- {entry}" for entry in entries)
    if len(parts) == 1:
        parts.append("No user-facing changes were recorded.")
    parts.append(
        f"[Full source comparison](https://github.com/{source_repository}/compare/{previous}...{source_sha})"
    )
    return "\n\n".join(parts) + release_footer(source_repository, source_sha, product_version)


class GitHub:
    def __init__(self) -> None:
        if not os.environ.get("GH_TOKEN") and not os.environ.get("GITHUB_TOKEN"):
            raise ReleaseError("GH_TOKEN is required for target repository access")

    def api(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, object] | None = None,
        allow_not_found: bool = False,
    ) -> dict | list | None:
        arguments = ["gh", "api", path, "--method", method]
        input_text = None
        if payload is not None:
            arguments += ["--input", "-"]
            input_text = json.dumps(payload)
        process = subprocess.run(arguments, input=input_text, text=True, capture_output=True)
        if process.returncode:
            detail = process.stderr.strip() or process.stdout.strip()
            if allow_not_found and "404" in detail:
                return None
            raise ReleaseError(f"GitHub API {method} {path} failed: {detail}")
        if not process.stdout.strip():
            return None
        return json.loads(process.stdout)

    def default_branch(self, repository: str) -> str:
        result = self.api(f"repos/{repository}")
        return result["default_branch"]

    def commit(self, repository: str, reference: str) -> dict:
        return self.api(f"repos/{repository}/commits/{urllib.parse.quote(reference, safe='/')}")

    def metadata(self, repository: str, reference: str) -> tuple[str, Metadata]:
        commit = self.commit(repository, reference)
        return commit["sha"], parse_metadata(commit["commit"]["message"])

    def tag_commit(self, repository: str, tag: str) -> dict | None:
        reference = self.api(f"repos/{repository}/git/ref/tags/{tag}", allow_not_found=True)
        if reference is None:
            return None
        return self.commit(repository, tag)

    def release(self, repository: str, tag: str) -> dict | None:
        return self.api(f"repos/{repository}/releases/tags/{tag}", allow_not_found=True)

    def baseline(self, repository: str, exclude_tag: str) -> Baseline | None:
        releases = self.api(f"repos/{repository}/releases?per_page=100")
        for release in releases:
            tag = release.get("tag_name", "")
            if tag == exclude_tag or release.get("draft") or release.get("prerelease"):
                continue
            try:
                version = normalize_version(tag, "existing release tag")
            except ReleaseError:
                continue
            try:
                _, metadata = self.metadata(repository, tag)
            except ReleaseError:
                continue
            if metadata.source_sha:
                return Baseline(tag=tag, version=version, source_sha=metadata.source_sha)
        return None


def prepare_plan(
    github: GitHub,
    source_root: Path,
    source_repository: str,
    source_sha: str,
    product_version: str,
    plan: Plan,
) -> None:
    plan.baseline = github.baseline(plan.repository, plan.tag)
    if plan.baseline and version_key(plan.version) <= version_key(plan.baseline.version):
        existing = github.tag_commit(plan.repository, plan.tag)
        if existing is None:
            raise ReleaseError(
                f"{plan.repository} {plan.tag} must be newer than {plan.baseline.tag}"
            )
    existing = github.tag_commit(plan.repository, plan.tag)
    if existing is not None:
        metadata = parse_metadata(existing["commit"]["message"])
        if metadata.source_sha != source_sha or metadata.version != plan.version:
            raise ReleaseError(
                f"{plan.repository} {plan.tag} already exists for different source or metadata"
            )
    plan.notes = collect_release_notes(
        source_root, source_repository, source_sha, product_version, plan
    )


def validate_export(plan: Plan, work_dir: Path) -> None:
    if plan.kind == "Go":
        run(["go", "mod", "tidy"], cwd=plan.export_dir)
        run(["go", "test", "-p=2", "./..."], cwd=plan.export_dir)
        run(["go", "build", "./..."], cwd=plan.export_dir)
        return
    venv = work_dir / "python-venv"
    run([sys.executable, "-m", "venv", str(venv)])
    python = venv / "bin/python"
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python), "-m", "pip", "install", "build", "twine", str(plan.export_dir)])
    run([str(python), "-m", "unittest", "discover", "-s", "tests"], cwd=plan.export_dir)
    run([str(python), "-m", "build"], cwd=plan.export_dir)
    distributions = sorted((plan.export_dir / "dist").glob("*"))
    run([str(python), "-m", "twine", "check", *map(str, distributions)])


def replace_target_tree(target: Path, export: Path, archive_legacy: bool) -> None:
    if archive_legacy:
        entries = [entry for entry in target.iterdir() if entry.name != ".git"]
        if any(entry.name == "legacy" for entry in entries):
            raise ReleaseError("cannot archive target: legacy already exists without export metadata")
        legacy = target / "legacy"
        legacy.mkdir()
        for entry in entries:
            shutil.move(str(entry), str(legacy / entry.name))
    else:
        for entry in target.iterdir():
            if entry.name in {".git", "legacy"}:
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
    copy_tree(export, target)


def publish_plan(
    github: GitHub,
    plan: Plan,
    source_sha: str,
    product_version: str,
    work_dir: Path,
) -> None:
    repository = plan.repository
    default_branch = github.default_branch(repository)
    main_sha, main_metadata = github.metadata(repository, f"heads/{default_branch}")
    existing_tag = github.tag_commit(repository, plan.tag)
    if existing_tag is not None:
        target_sha = existing_tag["sha"]
    elif main_metadata.source_sha == source_sha and main_metadata.version == plan.version:
        target_sha = main_sha
    else:
        target = work_dir / f"target-{plan.kind.lower()}"
        run(["git", "clone", f"https://github.com/{repository}.git", str(target)])
        branch = f"release/{plan.tag}-{source_sha[:12]}"
        run(["git", "checkout", "-B", branch, f"origin/{default_branch}"], cwd=target)
        replace_target_tree(target, plan.export_dir, archive_legacy=main_metadata.source_sha is None)
        run(["git", "add", "--all"], cwd=target)
        if not run(["git", "status", "--porcelain"], cwd=target).stdout.strip():
            raise ReleaseError(f"{repository} has no exported changes for {plan.tag}")
        run(["git", "config", "user.name", "moi-sdk-release[bot]"], cwd=target)
        run(["git", "config", "user.email", "moi-sdk-release@users.noreply.github.com"], cwd=target)
        message = release_commit_message(plan, source_sha, product_version)
        run(["git", "commit", "-m", message], cwd=target)
        run(["git", "push", "--force-with-lease", "origin", f"HEAD:refs/heads/{branch}"], cwd=target)
        owner = repository.split("/", 1)[0]
        pulls = github.api(
            f"repos/{repository}/pulls?state=open&head={owner}:{urllib.parse.quote(branch)}"
        )
        if pulls:
            pull = pulls[0]
        else:
            pull = github.api(
                f"repos/{repository}/pulls",
                method="POST",
                payload={
                    "title": f"release: {plan.kind} SDK {plan.tag}",
                    "head": branch,
                    "base": default_branch,
                    "body": (
                        f"Automated export from MOI commit `{source_sha}`.\n\n"
                        f"Target version: `{plan.tag}`\n\n"
                        "CI must pass before this PR is merged."
                    ),
                    "maintainer_can_modify": False,
                },
            )
        head_sha = run(["git", "rev-parse", "HEAD"], cwd=target).stdout.strip()
        wait_for_ci(github, repository, head_sha)
        merged = github.api(
            f"repos/{repository}/pulls/{pull['number']}/merge",
            method="PUT",
            payload={
                "commit_title": f"release: {plan.kind} SDK {plan.tag} (#{pull['number']})",
                "commit_message": message,
                "merge_method": "squash",
            },
        )
        if not merged.get("merged"):
            raise ReleaseError(f"{repository} PR #{pull['number']} was not merged")
        target_sha = merged["sha"]
        plan.result["pull_request"] = pull["html_url"]
    create_tag_and_release(github, plan, target_sha, source_sha, product_version)


def wait_for_ci(github: GitHub, repository: str, head_sha: str) -> None:
    deadline = time.monotonic() + 20 * 60
    while time.monotonic() < deadline:
        response = github.api(
            f"repos/{repository}/commits/{head_sha}/check-runs?per_page=100"
        )
        checks = [check for check in response["check_runs"] if check["name"] == "sdk-ci"]
        if checks:
            check = checks[0]
            if check["status"] == "completed":
                if check["conclusion"] == "success":
                    return
                raise ReleaseError(
                    f"{repository} sdk-ci failed for {head_sha}: {check.get('html_url')}"
                )
        time.sleep(5)
    raise ReleaseError(f"{repository} sdk-ci did not complete within 20 minutes")


def create_tag_and_release(
    github: GitHub,
    plan: Plan,
    target_sha: str,
    source_sha: str,
    product_version: str,
) -> None:
    repository = plan.repository
    existing_tag = github.tag_commit(repository, plan.tag)
    if existing_tag is None:
        github.api(
            f"repos/{repository}/git/refs",
            method="POST",
            payload={"ref": f"refs/tags/{plan.tag}", "sha": target_sha},
        )
    elif existing_tag["sha"] != target_sha:
        raise ReleaseError(f"{repository} {plan.tag} points to an unexpected commit")
    release = github.release(repository, plan.tag)
    expected_name = f"MOI Product {plan.kind} SDK {plan.tag}"
    if release is None:
        release = github.api(
            f"repos/{repository}/releases",
            method="POST",
            payload={
                "tag_name": plan.tag,
                "target_commitish": target_sha,
                "name": expected_name,
                "body": plan.notes,
                "draft": False,
                "prerelease": False,
                "generate_release_notes": False,
            },
        )
    elif release.get("body", "") != plan.notes:
        raise ReleaseError(f"{repository} {plan.tag} Release already has different notes")
    plan.result.update(
        {
            "repository": repository,
            "version": plan.version,
            "tag": plan.tag,
            "target_commit": target_sha,
            "release": release["html_url"],
            "source_sha": source_sha,
            "product_version": product_version,
        }
    )


def validate_arguments(arguments: argparse.Namespace) -> None:
    if not COMMIT_SHA.fullmatch(arguments.source_sha):
        raise ReleaseError("source_sha must be a full 40-character commit SHA")
    normalize_version(arguments.product_version, "product_version")
    for repository in (arguments.python_repository, arguments.go_repository):
        if not REPOSITORY.fullmatch(repository):
            raise ReleaseError(f"invalid target repository: {repository}")
    if arguments.python_repository == arguments.go_repository:
        raise ReleaseError("Python and Go targets must be different repositories")
    if arguments.source_repository in {arguments.python_repository, arguments.go_repository}:
        raise ReleaseError("source and target repositories must be different")


def publish(arguments: argparse.Namespace) -> list[dict[str, object]]:
    validate_arguments(arguments)
    source_root = Path(arguments.source_root).resolve()
    source_repository = arguments.source_repository
    go_module = f"github.com/{arguments.go_repository}"
    work_dir = Path(arguments.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    python_export = work_dir / "python-export"
    go_export = work_dir / "go-export"
    python_export.mkdir()
    go_export.mkdir()
    python_version = export_python(source_root, python_export)
    export_go(source_root, go_export, go_module)
    plans = [
        Plan(
            kind="Python",
            repository=arguments.python_repository,
            version=python_version,
            export_dir=python_export,
            module_path=None,
            manual_notes=os.environ.get("PYTHON_RELEASE_NOTES", ""),
        ),
        Plan(
            kind="Go",
            repository=arguments.go_repository,
            version=normalize_version(arguments.go_version, "go_version"),
            export_dir=go_export,
            module_path=go_module,
            manual_notes=os.environ.get("GO_RELEASE_NOTES", ""),
        ),
    ]
    github = GitHub()
    for plan in plans:
        prepare_plan(
            github,
            source_root,
            source_repository,
            arguments.source_sha,
            arguments.product_version,
            plan,
        )
    for plan in plans:
        validate_export(plan, work_dir)
    if arguments.dry_run:
        for plan in plans:
            plan.result.update(
                {
                    "repository": plan.repository,
                    "version": plan.version,
                    "tag": plan.tag,
                    "dry_run": True,
                    "baseline": plan.baseline.tag if plan.baseline else None,
                }
            )
        return [plan.result for plan in plans]
    for plan in plans:
        publish_plan(
            github,
            plan,
            arguments.source_sha,
            arguments.product_version,
            work_dir,
        )
    return [plan.result for plan in plans]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="export one SDK without contacting GitHub")
    export_parser.add_argument("--source-root", required=True)
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--kind", choices=["Python", "Go"], required=True)
    export_parser.add_argument("--module-path", help="required for Go")
    publish_parser = subparsers.add_parser("publish", help="validate and publish both SDKs")
    publish_parser.add_argument("--source-root", required=True)
    publish_parser.add_argument("--source-repository", required=True)
    publish_parser.add_argument("--source-sha", required=True)
    publish_parser.add_argument("--product-version", required=True)
    publish_parser.add_argument("--python-repository", required=True)
    publish_parser.add_argument("--go-repository", required=True)
    publish_parser.add_argument("--go-version", required=True)
    publish_parser.add_argument("--work-dir", required=True)
    publish_parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.command == "export":
            output = Path(arguments.output).resolve()
            if output.exists():
                raise ReleaseError(f"export output already exists: {output}")
            output.mkdir(parents=True)
            if arguments.kind == "Python":
                version = export_python(Path(arguments.source_root).resolve(), output)
                result = {"kind": "Python", "version": version, "output": str(output)}
            else:
                if not arguments.module_path:
                    raise ReleaseError("--module-path is required for Go export")
                export_go(Path(arguments.source_root).resolve(), output, arguments.module_path)
                result = {"kind": "Go", "module_path": arguments.module_path, "output": str(output)}
        else:
            result = publish(arguments)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(summary).open("a", encoding="utf-8") as stream:
                stream.write("## Product SDK release\n\n```json\n")
                stream.write(json.dumps(result, indent=2, ensure_ascii=False))
                stream.write("\n```\n")
        return 0
    except ReleaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
