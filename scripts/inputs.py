"""Obtain the exact sources, runtime artifacts and tool releases for AGP."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import TypedDict, cast


ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "out/inputs"


class Artifact(TypedDict):
    url: str
    sha256: str
    license: str
    role: str


class Lock(TypedDict):
    version: str
    files: dict[str, Artifact]


def lock() -> Lock:
    return cast(Lock, json.loads((ROOT / "locks/inputs.json").read_text()))


def digest(path: Path, algorithm: str = "sha256") -> str:
    with path.open("rb") as stream:
        return file_digest(stream, algorithm).hexdigest()


def fetch(name: str, artifact: Artifact) -> None:
    destination = INPUTS / name
    if destination.is_file() and digest(destination) == artifact["sha256"]:
        return
    url = artifact["url"]
    if not url.startswith("https://"):
        raise ValueError(f"Only HTTPS inputs are supported: {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as directory:
        pending = Path(directory) / destination.name
        subprocess.run(
            [
                "curl",
                "--disable",
                "--location",
                "--fail",
                "--silent",
                "--show-error",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--connect-timeout",
                "20",
                "--max-time",
                "300",
                "--retry",
                "3",
                "--output",
                pending,
                url,
            ],
            check=True,
        )
        if digest(pending) != artifact["sha256"]:
            raise ValueError(f"SHA-256 mismatch for {url}")
        pending.replace(destination)


def main() -> None:
    release = lock()
    if sys.argv[1:] == ["classpath"]:
        print(
            *(
                INPUTS / name
                for name, entry in release["files"].items()
                if entry["role"] in {"classpath", "compile"}
            ),
            sep="\n",
        )
        return
    if sys.argv[1:] == ["version"]:
        print(release["version"])
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        tasks = [
            pool.submit(fetch, name, entry) for name, entry in release["files"].items()
        ]
        for task in tasks:
            task.result()


if __name__ == "__main__":
    main()
