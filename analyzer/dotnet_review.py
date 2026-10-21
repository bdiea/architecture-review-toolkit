#!/usr/bin/env python3
"""
dotnet_review.py - quick automated health scan of a .NET codebase.

Produces a Markdown report that gives a reviewer a fast first picture before
the manual architecture review: frameworks, packages, project dependencies,
code hot-spots, possible secrets and engineering hygiene.

Usage:
    python analyzer/dotnet_review.py <path-to-repo> [-o report.md]

Only the Python standard library is used, so it runs anywhere.
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

SKIP_DIRS = {"bin", "obj", ".git", ".vs", "node_modules", "packages", "TestResults"}

# Frameworks that are out of Microsoft support (as of late 2025).
UNSUPPORTED_FRAMEWORK = re.compile(
    r"^(netcoreapp\d|net5\.0|net6\.0|net7\.0|netstandard1|net4[0-5]\d?$|net4[0-5]\b|v[1-4]\.[0-5])", re.I
)

SECRET_PATTERNS = {
    "Password in connection string": re.compile(r"(?i)\b(password|pwd)\s*=\s*[^;\"'\s{}$]{3,}"),
    "API key / token literal": re.compile(r"(?i)\b(api[_-]?key|secret|token)\b\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']"),
    "Private key block": re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
}

LARGE_FILE_LINES = 500


@dataclass
class ProjectInfo:
    path: Path
    name: str
    frameworks: list[str]
    packages: dict[str, str]
    project_refs: list[str]
    is_test: bool


@dataclass
class Finding:
    severity: str  # High / Medium / Low
    area: str
    message: str


@dataclass
class ReviewResult:
    root: Path
    projects: list[ProjectInfo] = field(default_factory=list)
    cs_files: int = 0
    cs_lines: int = 0
    large_files: list[tuple[Path, int]] = field(default_factory=list)
    todo_count: int = 0
    secrets: list[tuple[Path, int, str]] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    has_ci: bool = False
    has_docker: bool = False
    has_readme: bool = False


def iter_files(root: Path, suffixes: tuple[str, ...]):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in suffixes and not (set(path.relative_to(root).parts) & SKIP_DIRS):
            yield path


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def parse_project(path: Path) -> ProjectInfo:
    frameworks: list[str] = []
    packages: dict[str, str] = {}
    refs: list[str] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return ProjectInfo(path, path.stem, [], {}, [], False)

    for el in tree.iter():
        tag = _strip_ns(el.tag)
        text = (el.text or "").strip()
        if tag in ("TargetFramework", "TargetFrameworks") and text:
            frameworks += [f.strip() for f in text.split(";") if f.strip()]
        elif tag == "TargetFrameworkVersion" and text:  # legacy .NET Framework projects
            frameworks.append(text)
        elif tag == "PackageReference":
            name = el.get("Include") or el.get("Update")
            version = el.get("Version") or next((_c.text for _c in el if _strip_ns(_c.tag) == "Version"), None)
            if name:
                packages[name] = (version or "?").strip()
        elif tag == "ProjectReference" and el.get("Include"):
            refs.append(Path(el.get("Include").replace("\\", "/")).stem)

    is_test = bool(re.search(r"tests?$", path.stem, re.I)) or any(
        p.lower() in ("xunit", "nunit", "mstest.testframework", "microsoft.net.test.sdk") for p in packages
    )
    return ProjectInfo(path, path.stem, frameworks, packages, refs, is_test)


def inherited_frameworks(project: Path, root: Path) -> list[str]:
    """Frameworks set in the nearest Directory.Build.props above the project."""
    for folder in [project.parent, *project.parent.parents]:
        props = folder / "Directory.Build.props"
        if props.is_file():
            return parse_project(props).frameworks
        if folder == root:
            break
    return []


def find_cycles(projects: list[ProjectInfo]) -> list[list[str]]:
    graph = {p.name: p.project_refs for p in projects}
    cycles, state, stack = [], {}, []

    def visit(node: str):
        state[node] = "visiting"
        stack.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt) == "visiting":
                cycles.append(stack[stack.index(nxt):] + [nxt])
            elif nxt in graph and nxt not in state:
                visit(nxt)
        stack.pop()
        state[node] = "done"

    for name in graph:
        if name not in state:
            visit(name)
    return cycles


def scan(root: Path) -> ReviewResult:
    root = root.resolve()
    result = ReviewResult(root=root)

    for proj in iter_files(root, (".csproj", ".vbproj", ".fsproj")):
        info = parse_project(proj)
        if not info.frameworks:
            info.frameworks = inherited_frameworks(proj, root)
        result.projects.append(info)

    for cs in iter_files(root, (".cs",)):
        try:
            lines = cs.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        result.cs_files += 1
        result.cs_lines += len(lines)
        if len(lines) >= LARGE_FILE_LINES:
            result.large_files.append((cs.relative_to(root), len(lines)))
        result.todo_count += sum(1 for line in lines if re.search(r"\b(TODO|FIXME|HACK)\b", line))

    for cfg in iter_files(root, (".cs", ".json", ".config", ".xml", ".yml", ".yaml", ".env")):
        try:
            for no, line in enumerate(cfg.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                for label, pattern in SECRET_PATTERNS.items():
                    if pattern.search(line):
                        result.secrets.append((cfg.relative_to(root), no, label))
        except OSError:
            continue

    result.large_files.sort(key=lambda x: -x[1])
    result.cycles = find_cycles(result.projects)
    result.has_ci = (root / ".github" / "workflows").is_dir() or any(root.glob("azure-pipelines*.yml"))
    result.has_docker = any(
        not (set(p.relative_to(root).parts) & SKIP_DIRS) for p in root.rglob("Dockerfile")
    )
    result.has_readme = any(root.glob("README*"))
    result.findings = build_findings(result)
    return result


def build_findings(r: ReviewResult) -> list[Finding]:
    f: list[Finding] = []

    old = sorted({fw for p in r.projects for fw in p.frameworks if UNSUPPORTED_FRAMEWORK.match(fw)})
    if old:
        f.append(Finding("High", "Platform", f"Out-of-support target frameworks: {', '.join(old)}. Plan an upgrade to .NET 8+."))

    if r.secrets:
        f.append(Finding("High", "Security", f"{len(r.secrets)} possible hard-coded secret(s). Move to Key Vault / user secrets / environment variables."))

    if r.cycles:
        f.append(Finding("High", "Architecture", f"{len(r.cycles)} circular project reference(s) detected."))

    versions: dict[str, set[str]] = defaultdict(set)
    for p in r.projects:
        for name, ver in p.packages.items():
            versions[name].add(ver)
    drift = {n: v for n, v in versions.items() if len(v) > 1}
    if drift:
        f.append(Finding("Medium", "Dependencies", f"{len(drift)} package(s) referenced with different versions across projects "
                                                   "(consider Central Package Management)."))

    if r.projects and not any(p.is_test for p in r.projects):
        f.append(Finding("High", "Quality", "No test projects found."))

    if r.large_files:
        f.append(Finding("Medium", "Maintainability", f"{len(r.large_files)} file(s) with {LARGE_FILE_LINES}+ lines - candidates for refactoring."))

    if r.todo_count > 20:
        f.append(Finding("Low", "Maintainability", f"{r.todo_count} TODO/FIXME/HACK markers - review technical debt backlog."))

    if not r.has_ci:
        f.append(Finding("Medium", "DevOps", "No CI pipeline found (GitHub Actions or Azure Pipelines)."))
    if not r.has_readme:
        f.append(Finding("Low", "Documentation", "No README at repository root."))
    if not r.has_docker:
        f.append(Finding("Low", "DevOps", "No Dockerfile - consider containerising for consistent deployments."))

    order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(f, key=lambda x: order[x.severity])


def to_markdown(r: ReviewResult) -> str:
    out: list[str] = []
    w = out.append
    w(f"# Automated .NET Review - {r.root.name}")
    w(f"_Generated {date.today().isoformat()} by architecture-review-toolkit. "
      "This scan is a starting point for a manual review, not a replacement for it._\n")

    sev = Counter(x.severity for x in r.findings)
    w("## Summary\n")
    w("| Metric | Value |\n|---|---|")
    w(f"| Projects | {len(r.projects)} ({sum(p.is_test for p in r.projects)} test) |")
    w(f"| C# files / lines | {r.cs_files} / {r.cs_lines:,} |")
    w(f"| Findings | {sev.get('High', 0)} high, {sev.get('Medium', 0)} medium, {sev.get('Low', 0)} low |")
    w(f"| CI pipeline | {'yes' if r.has_ci else 'no'} |")
    w(f"| Dockerfile | {'yes' if r.has_docker else 'no'} |\n")

    w("## Findings\n")
    if r.findings:
        w("| Severity | Area | Finding |\n|---|---|---|")
        for x in r.findings:
            w(f"| {x.severity} | {x.area} | {x.message} |")
    else:
        w("No automated findings.")
    w("")

    w("## Projects\n")
    w("| Project | Frameworks | Packages | References |\n|---|---|---|---|")
    for p in sorted(r.projects, key=lambda p: p.name):
        w(f"| {p.name}{' (test)' if p.is_test else ''} | {', '.join(p.frameworks) or '?'} | {len(p.packages)} | {', '.join(p.project_refs) or '-'} |")
    w("")

    if r.cycles:
        w("## Circular references\n")
        for c in r.cycles:
            w(f"- {' -> '.join(c)}")
        w("")

    if r.large_files:
        w(f"## Largest files (>= {LARGE_FILE_LINES} lines)\n")
        for path, lines in r.large_files[:15]:
            w(f"- `{path.as_posix()}` - {lines:,} lines")
        w("")

    if r.secrets:
        w("## Possible secrets (verify manually)\n")
        for path, line, label in r.secrets[:30]:
            w(f"- `{path.as_posix()}:{line}` - {label}")
        w("")

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Automated health scan of a .NET repository.")
    parser.add_argument("path", type=Path, help="Path to the repository root")
    parser.add_argument("-o", "--output", type=Path, help="Write Markdown report to this file")
    args = parser.parse_args(argv)

    if not args.path.is_dir():
        parser.error(f"{args.path} is not a directory")

    report = to_markdown(scan(args.path))
    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
