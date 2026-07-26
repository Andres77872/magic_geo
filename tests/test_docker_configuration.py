from __future__ import annotations

import re
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_TEXT = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
DOCKERFILE_TEXT = (ROOT / "Dockerfile").read_text(encoding="utf-8")
ENV_EXAMPLE_TEXT = (ROOT / ".env.example").read_text(encoding="utf-8")
DEPLOYMENT_GUIDE_TEXT = (ROOT / "docs/docker_deployment.md").read_text(
    encoding="utf-8"
)


def _env_example() -> dict[str, str]:
    return dict(
        re.findall(
            r"^([A-Z][A-Z0-9_]*)=(.*)$",
            ENV_EXAMPLE_TEXT,
            flags=re.MULTILINE,
        )
    )


def test_env_example_covers_every_compose_setting() -> None:
    referenced = set(
        re.findall(r"\$\{(MAGIC_GEO_[A-Z0-9_]+)", COMPOSE_TEXT)
    )

    assert set(_env_example()) == referenced


def test_container_workspace_is_absolute_and_confined_to_app() -> None:
    workspace = PurePosixPath(_env_example()["MAGIC_GEO_CONTAINER_WORKSPACE"])

    assert workspace.is_absolute()
    assert workspace.is_relative_to("/app")


def test_compose_couples_runtime_workspace_port_and_mount() -> None:
    assert (
        "MAGIC_GEO_WORKSPACE: "
        "${MAGIC_GEO_CONTAINER_WORKSPACE:-/app/runs}"
    ) in COMPOSE_TEXT
    assert (
        '"${MAGIC_GEO_WORLDS_DIR:-./worlds}:'
        '${MAGIC_GEO_CONTAINER_WORKSPACE:-/app/runs}"'
    ) in COMPOSE_TEXT
    assert (
        '"${MAGIC_GEO_PUBLISH_HOST:-127.0.0.1}:'
        '${MAGIC_GEO_PORT:-8642}:${MAGIC_GEO_PORT:-8642}"'
    ) in COMPOSE_TEXT


def test_compose_injects_only_runtime_configuration() -> None:
    assert "env_file:" not in COMPOSE_TEXT
    for variable in (
        "MAGIC_GEO_HOST",
        "MAGIC_GEO_PORT",
        "MAGIC_GEO_WORKSPACE",
        "MAGIC_GEO_NATIVE_LIBRARY",
    ):
        assert re.search(
            rf"^      {variable}:",
            COMPOSE_TEXT,
            flags=re.MULTILINE,
        )

    for variable in (
        "MAGIC_GEO_WORLDS_DIR",
        "MAGIC_GEO_PUBLISH_HOST",
        "MAGIC_GEO_PYTHON_VERSION",
        "MAGIC_GEO_APP_UID",
        "MAGIC_GEO_APP_GID",
        "MAGIC_GEO_ENABLE_CUDA",
    ):
        assert not re.search(
            rf"^      {variable}:",
            COMPOSE_TEXT,
            flags=re.MULTILINE,
        )


def test_image_runs_unprivileged_and_has_a_local_healthcheck() -> None:
    assert "USER magicgeo" in DOCKERFILE_TEXT
    assert "HEALTHCHECK " in DOCKERFILE_TEXT
    assert "http://127.0.0.1:" in DOCKERFILE_TEXT
    assert "/api/status" in DOCKERFILE_TEXT


def test_deployment_guide_documents_the_complete_template_and_workflow() -> None:
    for variable in _env_example():
        assert f"`{variable}`" in DEPLOYMENT_GUIDE_TEXT

    for command in (
        "docker compose up --build -d",
        "docker compose run --rm magic-geo generate",
        "docker compose run --rm magic-geo backend",
        "docker compose run --rm magic-geo validate-geo",
    ):
        assert command in DEPLOYMENT_GUIDE_TEXT
