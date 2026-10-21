# Architecture Review Toolkit for .NET Systems

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

The process and tools I use to review .NET / Azure systems: an **automated scanner** for a fast first
picture, a **checklist** for the manual review, and a **report template** that turns findings into a
prioritised roadmap.

## What's inside

| Path | What it is |
|---|---|
| [`analyzer/dotnet_review.py`](analyzer/dotnet_review.py) | Scans a .NET repo and writes a Markdown report |
| [`docs/checklist.md`](docs/checklist.md) | ~50-point checklist across 9 areas |
| [`docs/report-template.md`](docs/report-template.md) | Client-ready report structure with roadmap |

## The automated scan

No installation needed: Python 3.9+ standard library only.

```bash
python analyzer/dotnet_review.py /path/to/your/repo -o report.md
```

It checks:

- **Platform** – out-of-support target frameworks (`netcoreapp3.1`, `net6.0`, old .NET Framework…)
- **Security** – possible hard-coded passwords, API keys and private keys
- **Architecture** – circular project references, project dependency map
- **Dependencies** – the same NuGet package referenced with different versions
- **Quality** – missing test projects
- **Maintainability** – very large files, TODO/FIXME/HACK counts
- **DevOps** – CI pipeline, Dockerfile, README

Example output:

```markdown
## Findings
| Severity | Area | Finding |
|---|---|---|
| High | Platform | Out-of-support target frameworks: netcoreapp3.1. Plan an upgrade to .NET 8+. |
| High | Security | 2 possible hard-coded secret(s). Move to Key Vault / user secrets / environment variables. |
| Medium | Dependencies | 3 package(s) referenced with different versions across projects (consider Central Package Management). |
```

## Review process

1. **Kick-off** – goals, pain points, constraints, access
2. **Automated scan** – run the analyzer to find hot spots quickly
3. **Manual review** – walk through the checklist with code, diagrams and the team
4. **Report** – fill in the template; rank findings by impact and effort
5. **Walkthrough** – present quick wins and the roadmap

The scan is a starting point. The value of a review comes from understanding the business context
and talking to the team.

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT
