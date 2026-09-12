"""Exercise the wheel's actual symbol gate without building a wheel."""
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


LEGACY_REQUIRED = (
    "magic_geo_backend_info_json",
    "magic_geo_generate_json_v3", "magic_geo_generate_geo_json_v3",
    "magic_geo_generate_msgpack_v3", "magic_geo_generate_geo_msgpack_v3",
    "magic_geo_free_string", "magic_geo_free_buffer",
)
V4_REQUIRED = (
    "magic_geo_generate_json_v4", "magic_geo_generate_geo_json_v4",
    "magic_geo_generate_msgpack_v4", "magic_geo_generate_geo_msgpack_v4",
)


@pytest.fixture(scope="module")
def packaging():
    # Setuptools is the declared build dependency, not a runtime dependency.
    # Runtime-only test installations can omit this packaging-specific group.
    pytest.importorskip("setuptools")
    with patch("setuptools.setup") as setup:
        namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "setup.py"))
    setup.assert_called_once()
    return namespace


def library(symbols):
    return SimpleNamespace(**{name: Mock(name=name) for name in symbols})


def wheel_command(packaging):
    return packaging["PlatformWheel"](packaging["NativeDistribution"]())


@pytest.mark.parametrize("missing", [*LEGACY_REQUIRED, *V4_REQUIRED])
def test_each_required_legacy_and_v4_symbol_blocks_wheel_if_missing(packaging, missing):
    staged = library(name for name in (*LEGACY_REQUIRED, *V4_REQUIRED) if name != missing)
    with patch.object(Path, "is_file", return_value=True), \
         patch.object(packaging["ctypes"], "CDLL", return_value=staged), \
         patch.object(packaging["bdist_wheel"], "run") as build:
        with pytest.raises(RuntimeError, match="requires the V3 and seasonal V4.*rebuild") as error:
            wheel_command(packaging).run()
    assert missing in str(error.value)
    build.assert_not_called()


def test_stale_v3_only_library_is_rejected_before_any_wheel_build(packaging):
    with patch.object(Path, "is_file", return_value=True), \
         patch.object(packaging["ctypes"], "CDLL", return_value=library(LEGACY_REQUIRED)), \
         patch.object(packaging["bdist_wheel"], "run") as build:
        with pytest.raises(RuntimeError, match="magic_geo_generate_json_v4"):
            wheel_command(packaging).run()
    build.assert_not_called()


@pytest.mark.parametrize("platform,name", [
    ("linux", "libmagic_geo_native.so"), ("win32", "magic_geo_native.dll"),
    ("darwin", "libmagic_geo_native.dylib"),
])
def test_complete_library_reaches_wheel_builder_with_platform_specific_path(packaging, platform, name):
    command = wheel_command(packaging)
    staged = library((*LEGACY_REQUIRED, *V4_REQUIRED))
    with patch.object(packaging["sys"], "platform", platform), \
         patch.object(Path, "is_file", return_value=True), \
         patch.object(packaging["ctypes"], "CDLL", return_value=staged) as load, \
         patch.object(packaging["bdist_wheel"], "run") as build:
        command.run()
    assert Path(load.call_args.args[0]).name == name
    build.assert_called_once()
    # The packaging gate checks exported addresses; it does not run expensive
    # generators or call native allocation/free functions.
    for function in vars(staged).values():
        function.assert_not_called()


def test_missing_binary_and_unloadable_host_binary_fail_before_build(packaging):
    with patch.object(Path, "is_file", return_value=False), \
         patch.object(packaging["ctypes"], "CDLL") as load, \
         patch.object(packaging["bdist_wheel"], "run") as build:
        with pytest.raises(RuntimeError, match="without.*Release target with CMake"):
            wheel_command(packaging).run()
    load.assert_not_called()
    build.assert_not_called()
    with patch.object(Path, "is_file", return_value=True), \
         patch.object(packaging["ctypes"], "CDLL", side_effect=OSError("wrong architecture")), \
         patch.object(packaging["bdist_wheel"], "run") as build:
        with pytest.raises(RuntimeError, match="incompatible with this build host or package.*wrong architecture"):
            wheel_command(packaging).run()
    build.assert_not_called()


def test_platform_wheel_tag_still_has_no_python_abi(packaging):
    command = wheel_command(packaging)
    with patch.object(packaging["bdist_wheel"], "get_tag", return_value=("cp313", "cp313", "host_platform")):
        assert command.get_tag() == ("py3", "none", "host_platform")
    with patch.object(packaging["bdist_wheel"], "finalize_options"):
        command.finalize_options()
    assert command.root_is_pure is False
    assert packaging["NativeDistribution"]().has_ext_modules()
