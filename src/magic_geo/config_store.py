"""Discover and read editable generation configs, independent of HTTP/UI."""

from __future__ import annotations

from pathlib import Path
from hashlib import sha256
import yaml

from .config import ConfigError, parse_config_yaml
from .paths import RuntimePaths, walk_files

MAX_CONFIG_BYTES = 1_000_000


class ConfigStore:
    def __init__(self, paths: RuntimePaths):
        self.paths = paths

    def read(self, value: str | Path) -> dict:
        raw = Path(value).expanduser()
        path = self.paths.project / raw
        resolved = path.resolve()
        roots = (self.paths.config_dir, self.paths.saved_config_dir)
        root_files = (self.paths.project / "magic-geo.yaml", self.paths.project / "magic-geo.yml")
        if path.is_symlink() or not (resolved == self.paths.config_path or resolved in root_files
                                    or any(resolved.is_relative_to(root) for root in roots)):
            raise ValueError("configuration must be inside a configured config directory")
        if resolved.stat().st_size > MAX_CONFIG_BYTES:
            raise ValueError("configuration exceeds the 1,000,000-byte editor limit")
        with resolved.open("r", encoding="utf-8") as stream:
            yaml = stream.read(MAX_CONFIG_BYTES + 1)
        if len(yaml.encode("utf-8")) > MAX_CONFIG_BYTES:
            raise ValueError("configuration exceeds the 1,000,000-byte editor limit")
        try:
            config = parse_config_yaml(yaml, source=self.paths.display(resolved))
            error = None
        except ConfigError as exc:
            config, error = None, exc.to_dict()
        return {"path": self.paths.display(resolved), "name": resolved.name, "yaml": yaml,
                "revision": sha256(yaml.encode("utf-8")).hexdigest(),
                "valid": error is None, "error": error,
                "world_name": config.run.name if config else None}

    def preferred(self) -> list[Path]:
        p = self.paths
        return ([p.config_path] if p.config_path else []) + [
            p.project / "magic-geo.yaml", p.project / "magic-geo.yml",
            p.saved_config_dir / "world.yaml", p.config_dir / "earthlike_seed.yaml",
        ]

    def catalog(self) -> dict:
        p = self.paths
        preferred = self.preferred()
        candidates = list(preferred)
        for root in dict.fromkeys((p.saved_config_dir, p.config_dir)):
            candidates.extend(walk_files(root, suffixes=(".yaml", ".yml")))
        entries, seen = [], set()
        for path in candidates:
            if path is None or path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                item = self.read(path)
                # Scenario matrices are YAML too; only world configs belong in
                # the picker. Keep malformed conventional/explicit files visible.
                if not item["valid"] and path not in preferred:
                    payload = yaml.safe_load(item["yaml"])
                    if not isinstance(payload, dict) or not {"run", "mesh", "climate", "config_version"}.intersection(payload):
                        continue
                entries.append({key: value for key, value in item.items() if key != "yaml"})
            except (OSError, UnicodeError, ValueError, yaml.YAMLError):
                continue
        explicit_error = None
        if p.config_path:
            selected = p.display(p.config_path)
            if not any(item["path"] == selected for item in entries):
                explicit_error = f"Configured file is missing or unreadable: {selected} (MAGIC_GEO_CONFIG_PATH)"
        else:
            selected = next((item["path"] for item in entries if item["valid"]), None)
        return {"configs": entries, "default": selected, "error": explicit_error,
                "save_directory": p.display(p.saved_config_dir),
                "search_directories": [p.display(root) for root in dict.fromkeys((p.saved_config_dir, p.config_dir))]}

    def default(self) -> Path | None:
        if self.paths.config_path:
            return self.paths.config_path
        # Most invocations have a conventional default. Avoid scanning and
        # parsing an entire library on each submitted operation.
        for path in self.preferred():
            try:
                if self.read(path)["valid"]:
                    return path
            except (OSError, UnicodeError, ValueError):
                continue
        selected = self.catalog()["default"]
        return self.paths.project / selected if selected else None
