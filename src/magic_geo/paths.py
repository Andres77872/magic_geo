"""Runtime storage locations shared by the CLI, workbench and job worker.

Environment is read at application creation, never at import time. Relative
settings are anchored to the project, so launching from a subdirectory does not
create a second workspace. Explicit CLI file paths retain normal cwd semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


def project_directory(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        if (directory / "pyproject.toml").is_file() and (directory / "src/magic_geo").is_dir():
            return directory
        if (directory / "magic-geo.yaml").is_file():
            return directory
    return start


def contains(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path.is_relative_to(root) for root in roots)


@dataclass(frozen=True)
class RuntimePaths:
    project: Path
    workspace: Path
    config_dir: Path
    saved_config_dir: Path
    output_dir: Path
    debug_dir: Path
    reports_dir: Path
    exports_dir: Path
    state_dir: Path
    calibration_dir: Path
    config_path: Path | None = None

    @classmethod
    def resolve(cls, project: Path | None = None, workspace: Path | None = None,
                *, environ: Mapping[str, str] | None = None) -> RuntimePaths:
        env = os.environ if environ is None else environ
        root = Path(project).expanduser().resolve() if project is not None else project_directory()
        if project is None and env.get("MAGIC_GEO_PROJECT_ROOT", "").strip():
            root = Path(env["MAGIC_GEO_PROJECT_ROOT"]).expanduser().resolve()

        def absolute(value: str | Path) -> Path:
            path = Path(value).expanduser()
            return (root / path).resolve()

        def setting(name: str, default: Path) -> Path:
            value = env.get(f"MAGIC_GEO_{name}", "").strip()
            return absolute(value) if value else default

        work = absolute(workspace) if workspace is not None else setting("WORKSPACE", root / "runs")
        output = setting("OUTPUT_DIR", work)
        config = env.get("MAGIC_GEO_CONFIG_PATH", "").strip()
        return cls(root, work, setting("CONFIG_DIR", root / "configs"),
                   setting("SAVED_CONFIG_DIR", work / "configs"), output,
                   setting("DEBUG_DIR", output / "debug"), setting("REPORTS_DIR", output),
                   setting("EXPORTS_DIR", output), setting("STATE_DIR", work / ".magic-geo-web"),
                   setting("CALIBRATION_DIR", root / "calibration_data"),
                   absolute(config) if config else None)

    def display(self, path: Path) -> str:
        path = path.resolve()
        return path.relative_to(self.project).as_posix() if path.is_relative_to(self.project) else str(path)

    @property
    def input_roots(self) -> tuple[Path, ...]:
        return tuple(dict.fromkeys((self.project, self.workspace, self.config_dir,
                                   self.saved_config_dir, self.output_dir, self.debug_dir,
                                   self.reports_dir, self.exports_dir, self.calibration_dir)))

    @property
    def output_roots(self) -> tuple[Path, ...]:
        return tuple(dict.fromkeys((self.workspace, self.output_dir, self.reports_dir,
                                   self.exports_dir, self.debug_dir)))

    def allows_input(self, path: Path) -> bool:
        return path == self.config_path or contains(path, self.input_roots)

    def allows_output(self, path: Path) -> bool:
        return contains(path, self.output_roots) and not path.is_relative_to(self.state_dir)

    def rebase_default(self, value: str | Path, *, category: str = "output") -> Path:
        """Map existing repository defaults without changing their file names."""
        raw = Path(value)
        if raw.is_absolute():
            return raw
        roots = {"runs": self.output_dir, "configs": self.config_dir,
                 "calibration_data": self.calibration_dir}
        if raw.parts and raw.parts[0] == "runs":
            if len(raw.parts) > 1 and raw.parts[1] == "debug":
                return self.debug_dir.joinpath(*raw.parts[2:])
            if len(raw.parts) > 1 and raw.parts[1] == "configs":
                return self.saved_config_dir.joinpath(*raw.parts[2:])
            root = {"report": self.reports_dir, "export": self.exports_dir}.get(category, self.output_dir)
            return root.joinpath(*raw.parts[1:])
        if raw.parts and raw.parts[0] in roots:
            return roots[raw.parts[0]].joinpath(*raw.parts[1:])
        return self.project / raw

    def describe(self) -> dict[str, str | None]:
        return {**{name: self.display(value) if isinstance(value, Path) else value
                   for name, value in vars(self).items()}, "project": str(self.project)}


def walk_files(root: Path, *, suffixes: tuple[str, ...] = (), name: str | None = None,
               excluded: tuple[Path, ...] = (), limit: int = 2000):
    """Deterministic, bounded discovery; never traverse symlinks or internals."""
    count = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        traversable = []
        for d in sorted(dirs):
            try:
                if (not d.startswith(".") and d not in {"node_modules", "__pycache__", "build", "cmake-build-debug"}
                        and not (base / d).is_symlink() and not contains((base / d).resolve(), excluded)):
                    traversable.append(d)
            except (OSError, RuntimeError):
                continue
        dirs[:] = traversable
        for filename in sorted(files):
            path = base / filename
            try:
                if path.is_symlink() or (name and filename != name) or (suffixes and path.suffix not in suffixes):
                    continue
                if contains(path.resolve(), excluded):
                    continue
            except (OSError, RuntimeError):
                continue
            yield path
            count += 1
            if count >= limit:
                return
