"""Setuptools hook that marks wheels containing the native core as platform wheels."""

import ctypes
import sys
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.bdist_wheel import bdist_wheel
from setuptools.command.sdist import sdist


_NATIVE_NAMES = (
    "libmagic_geo_native.so",
    "magic_geo_native.dll",
    "libmagic_geo_native.dylib",
)


def _native_name() -> str:
    return (
        "magic_geo_native.dll"
        if sys.platform == "win32"
        else "libmagic_geo_native.dylib"
        if sys.platform == "darwin"
        else "libmagic_geo_native.so"
    )


class NativeDistribution(Distribution):
    """Prevent a bundled shared library from being tagged as ``py3-none-any``."""

    def has_ext_modules(self) -> bool:
        return True


class PlatformWheel(bdist_wheel):
    """The ctypes core is Python-ABI-independent but OS/architecture-specific."""

    def finalize_options(self) -> None:
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self) -> tuple[str, str, str]:
        _python, _abi, platform = super().get_tag()
        return "py3", "none", platform

    def run(self) -> None:
        native_name = _native_name()
        native_path = Path(__file__).parent / "src" / "magic_geo" / native_name
        if not native_path.is_file():
            raise RuntimeError(
                f"cannot build a wheel without {native_path}; build the native "
                "Release target with CMake first"
            )
        try:
            library = ctypes.CDLL(str(native_path.resolve()))
            for symbol in (
                "magic_geo_backend_info_json",
                "magic_geo_generate_json_v3",
                "magic_geo_generate_geo_json_v3",
                "magic_geo_generate_msgpack_v3",
                "magic_geo_generate_geo_msgpack_v3",
                "magic_geo_generate_json_v4",
                "magic_geo_generate_geo_json_v4",
                "magic_geo_generate_msgpack_v4",
                "magic_geo_generate_geo_msgpack_v4",
                "magic_geo_free_string",
                "magic_geo_free_buffer",
            ):
                getattr(library, symbol)
        except (OSError, AttributeError) as exc:
            raise RuntimeError(
                f"the staged native core is incompatible with this build host or package: "
                f"{native_path}: {exc}; the current package requires the V3 "
                "and seasonal V4 JSON/MessagePack APIs; rebuild the native "
                "Release target with CMake first"
            ) from exc
        finally:
            library = None
        super().run()


class SourceDistribution(sdist):
    """Ship rebuildable CMake sources, never a host-specific staged binary."""

    def make_release_tree(self, base_dir: str, files: list[str]) -> None:
        super().make_release_tree(base_dir, files)
        package_dir = Path(base_dir) / "src" / "magic_geo"
        for native_name in _NATIVE_NAMES:
            (package_dir / native_name).unlink(missing_ok=True)


setup(
    distclass=NativeDistribution,
    cmdclass={"bdist_wheel": PlatformWheel, "sdist": SourceDistribution},
    exclude_package_data={
        "magic_geo": [name for name in _NATIVE_NAMES if name != _native_name()]
    },
)
