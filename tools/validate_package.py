"""Validate the packaged standalone RTL-Davis extension."""

import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from package import build


EXPECTED_MODULES = {
    "rtldavis.py",
    "rtldavis_receiver.py",
    "rtldavis_dsp.py",
    "rtldavis_gust_diagnostics.py",
    "rtldavis_frame_diagnostics.py",
    "rtldavis_phase_c_diagnostics.py",
    "rtldavis_diagnostic_storage.py",
    "rtldavis_wind_validation.py",
}


def validate():
    """Check archive contents, installer manifest and isolated imports."""
    package = build()
    root_name = package.stem

    with tempfile.TemporaryDirectory() as directory:
        destination = Path(directory)

        with zipfile.ZipFile(package) as archive:
            assert archive.testzip() is None, "Corrupt ZIP archive"

            names = set(archive.namelist())
            prefix = f"{root_name}/bin/user/"

            modules = {
                name.removeprefix(prefix)
                for name in names
                if name.startswith(prefix)
                and name.endswith(".py")
            }

            assert modules == EXPECTED_MODULES, (
                f"Missing: {EXPECTED_MODULES - modules}; "
                f"Unexpected: {modules - EXPECTED_MODULES}"
            )

            assert not any(
                "__pycache__" in name or name.endswith(".pyc")
                for name in names
            ), "Generated Python files included"

            assert not any(
                "rtldavis_ab_diagnostics.py" in name
                for name in names
            ), "Obsolete A/B module included"

            assert f"{root_name}/install.py" in names
            archive.extractall(destination)

        root = destination / root_name
        installer = ast.parse(
            (root / "install.py").read_text()
        )

        manifest = [
            ast.literal_eval(node.value)
            for node in ast.walk(installer)
            if isinstance(node, ast.keyword)
            and node.arg == "files"
        ]

        expected_manifest = [
            ("bin/user", sorted(
                f"bin/user/{name}" for name in EXPECTED_MODULES
            ))
        ]

        assert len(manifest) == 1
        actual_manifest = [
            (target, sorted(files))
            for target, files in manifest[0]
        ]
        assert actual_manifest == expected_manifest

        # Isolated Python process: imports must come from the archive,
        # not the repository checkout or an existing user installation.
        code = """
import importlib
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "bin"))

for name in sys.argv[2:]:
    module = importlib.import_module("user." + name)
    location = Path(module.__file__).resolve()
    assert location.parent == root / "bin/user", location
    print("Imported:", module.__name__)

sys.path.insert(0, str(root))
installer = importlib.import_module("install")
installer.loader()
print("Installer loaded successfully")
"""

        subprocess.run(
            [
                sys.executable, "-I", "-c", code, str(root),
                *sorted(Path(name).stem for name in EXPECTED_MODULES),
            ],
            cwd=destination,
            check=True,
        )

    print("Package validation passed:", package)


if __name__ == "__main__":
    validate()
