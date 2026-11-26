"""Assemble the Maven modules from compiled classes and pinned resources."""

import argparse
import json
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from inputs import INPUTS, digest, lock


MODULES = ("builder", "gradle")
R8 = INPUTS / "tools/aosstudio-r8-9.5.29-agp.jar"
DATABASE = "resources/api_database.ser"


def module_path(module: str) -> Path:
    return Path("com/android/tools/build") / module / lock()["version"]


def zip_entry(target: ZipFile, name: str, data: bytes) -> None:
    info = ZipInfo(name, (2026, 11, 16, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    target.writestr(info, data, compress_type=ZIP_DEFLATED)


def stage_sources(module: str, target: Path) -> None:
    name = f"{module}-{lock()['version']}-sources.jar"
    with ZipFile(INPUTS / "source" / name) as sources:
        names = [
            path
            for path in sources.namelist()
            if path.endswith((".java", ".kt"))
            # The main publication also places generated Java under java/.
            # The package-root entries are its canonical generated sources.
            and not (module == "gradle" and path.startswith("java/"))
        ]
        if not names:
            raise ValueError(f"No published sources in {name}")
        sources.extractall(target, names)


def package_module(module: str, classes: Path, repository: Path) -> None:
    relative = module_path(module)
    target = repository / relative
    target.mkdir(parents=True, exist_ok=True)
    stem = f"{module}-{lock()['version']}"
    jar_path = target / f"{stem}.jar"
    written: set[str] = set()

    with (
        ZipFile(INPUTS / "resource" / jar_path.name) as resources,
        ZipFile(jar_path, "w") as output,
    ):
        for name in sorted(resources.namelist()):
            if name.endswith((".class", ".kotlin_module", "/", ".SF", ".RSA", ".DSA")):
                continue
            if module == "builder" and (
                name == "r8-version.properties"
                or name.startswith(("META-INF/services/", "resources/"))
            ):
                continue
            zip_entry(output, name, resources.read(name))
            written.add(name)
        for file in sorted(classes.rglob("*")):
            if file.is_file():
                name = file.relative_to(classes).as_posix()
                if name in written:
                    raise ValueError(f"Duplicate module entry: {name}")
                zip_entry(output, name, file.read_bytes())
                written.add(name)
        if module == "builder":
            with ZipFile(R8) as r8:
                for name in sorted(r8.namelist()):
                    if name == "META-INF/MANIFEST.MF" or name.endswith("/"):
                        continue
                    if name in written:
                        raise ValueError(f"Duplicate R8 entry: {name}")
                    zip_entry(output, name, r8.read(name))
                    written.add(name)

    source = INPUTS / "publication" / relative
    shutil.copyfile(source / f"{stem}.pom", target / f"{stem}.pom")
    metadata = json.loads((source / f"{stem}.module").read_text())
    checksums = {
        algorithm: digest(jar_path, algorithm)
        for algorithm in ("md5", "sha1", "sha256", "sha512")
    }
    matches = 0
    for variant in metadata["variants"]:
        for file in variant.get("files", []):
            if file["name"] == jar_path.name:
                file.update(checksums, size=jar_path.stat().st_size)
                matches += 1
    if not matches:
        raise ValueError(f"Missing published module file metadata for {stem}")
    (target / f"{stem}.module").write_text(json.dumps(metadata, indent=2) + "\n")


def copy_markers(repository: Path) -> None:
    publication = INPUTS / "publication"
    for marker in sorted(publication.rglob("*.gradle.plugin-*.pom")):
        destination = repository / marker.relative_to(publication)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(marker, destination)


def verify(repository: Path) -> None:
    version = lock()["version"]
    for module in MODULES:
        path = repository / module_path(module)
        stem = f"{module}-{version}"
        jar = path / f"{stem}.jar"
        module_metadata = json.loads((path / f"{stem}.module").read_text())
        checksums = {
            algorithm: digest(jar, algorithm)
            for algorithm in ("md5", "sha1", "sha256", "sha512")
        }
        for variant in module_metadata["variants"]:
            for file in variant.get("files", []):
                if file["name"] == jar.name and (
                    file["size"] != jar.stat().st_size
                    or any(file[key] != value for key, value in checksums.items())
                ):
                    raise ValueError(f"Inconsistent Maven artifact metadata for {jar}")
    with (
        ZipFile(
            repository / module_path("builder") / f"builder-{version}.jar"
        ) as builder,
        ZipFile(R8) as r8,
    ):
        for name in (
            "com/android/tools/r8/D8.class",
            "com/android/tools/r8/R8.class",
            DATABASE,
        ):
            if builder.read(name) != r8.read(name):
                raise ValueError(f"Published R8 input changed during assembly: {name}")
        version_metadata = "r8-version.properties"
        if version_metadata in builder.namelist() and (
            version_metadata not in r8.namelist()
            or builder.read(version_metadata) != r8.read(version_metadata)
        ):
            raise ValueError("The builder retained upstream R8 build provenance")
    print(f"AGP {version} Maven metadata and embedded R8 verified")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("sources", "package", "markers", "verify"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--module", choices=MODULES)
    parser.add_argument("--classes", type=Path)
    args = parser.parse_args()
    if args.command == "markers":
        copy_markers(args.path)
    elif args.command == "verify":
        verify(args.path)
    elif args.command == "sources":
        stage_sources(args.module, args.path)
    else:
        package_module(args.module, args.classes, args.path)


if __name__ == "__main__":
    main()
