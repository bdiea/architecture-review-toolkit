import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analyzer"))
import dotnet_review as dr  # noqa: E402


def write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>{fw}</TargetFramework></PropertyGroup>
  <ItemGroup>{packages}</ItemGroup>
  <ItemGroup>{refs}</ItemGroup>
</Project>"""


def csproj(fw="net8.0", packages=None, refs=None) -> str:
    pk = "".join(f'<PackageReference Include="{n}" Version="{v}" />' for n, v in (packages or {}).items())
    rf = "".join(f'<ProjectReference Include="..\\{r}\\{r}.csproj" />' for r in (refs or []))
    return CSPROJ.format(fw=fw, packages=pk, refs=rf)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_healthy_repo_has_no_high_findings(self):
        write(self.root, "src/Api/Api.csproj", csproj(packages={"Serilog": "4.0.0"}, refs=["Core"]))
        write(self.root, "src/Core/Core.csproj", csproj())
        write(self.root, "tests/Api.Tests/Api.Tests.csproj", csproj(packages={"xunit": "2.9.2"}, refs=["Api"]))
        write(self.root, "src/Api/Program.cs", "var x = 1;\n")
        write(self.root, ".github/workflows/ci.yml", "name: CI\n")
        write(self.root, "Dockerfile", "FROM scratch\n")
        write(self.root, "README.md", "# Demo\n")

        result = dr.scan(self.root)

        self.assertEqual(3, len(result.projects))
        self.assertEqual([], [f for f in result.findings if f.severity == "High"])
        self.assertTrue(result.has_ci and result.has_docker and result.has_readme)

    def test_detects_old_framework_secrets_cycles_and_missing_tests(self):
        write(self.root, "A/A.csproj", csproj(fw="netcoreapp3.1", refs=["B"]))
        write(self.root, "B/B.csproj", csproj(fw="net6.0", refs=["A"]))
        write(self.root, "A/appsettings.json",
              '{ "ConnectionStrings": { "Db": "Server=x;User Id=sa;Password=SuperSecret1;" } }')

        result = dr.scan(self.root)
        areas = {f.area for f in result.findings if f.severity == "High"}

        self.assertEqual({"Platform", "Security", "Architecture", "Quality"}, areas)
        self.assertEqual(1, len(result.secrets))
        self.assertTrue(result.cycles)

    def test_package_version_drift_and_large_files(self):
        write(self.root, "A/A.csproj", csproj(packages={"Newtonsoft.Json": "12.0.3"}))
        write(self.root, "B/B.csproj", csproj(packages={"Newtonsoft.Json": "13.0.3"}))
        write(self.root, "A/Big.cs", "// line\n" * 600)

        result = dr.scan(self.root)
        areas = {f.area for f in result.findings}

        self.assertIn("Dependencies", areas)
        self.assertIn("Maintainability", areas)
        self.assertEqual(600, result.large_files[0][1])

    def test_ignores_bin_and_obj_folders(self):
        write(self.root, "A/A.csproj", csproj())
        write(self.root, "A/obj/Generated.cs", "// TODO\n" * 600)

        result = dr.scan(self.root)

        self.assertEqual(0, result.cs_files)
        self.assertEqual(0, result.todo_count)

    def test_markdown_report_contains_sections(self):
        write(self.root, "A/A.csproj", csproj(fw="net48"))
        report = dr.to_markdown(dr.scan(self.root))

        self.assertIn("# Automated .NET Review", report)
        self.assertIn("## Findings", report)
        self.assertIn("| A |", report)


if __name__ == "__main__":
    unittest.main()
