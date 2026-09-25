import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_collector_imports_from_a_zip_archive(tmp_path: Path) -> None:
    # The deployment artifact is a zip; the package must not assume it lives on a filesystem.
    archive = tmp_path / "collector.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in (ROOT / "collector").rglob("*.py"):
            bundle.write(path, path.relative_to(ROOT).as_posix())
    code = (
        f"import sys; sys.path.insert(0, {str(archive)!r}); "
        "import collector.handler, collector.publish as p; print(p.__file__, p.RENDER_VERSION)"
    )

    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path, check=False
    )

    assert result.returncode == 0, result.stderr
    assert "collector.zip" in result.stdout
