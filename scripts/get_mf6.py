#!/usr/bin/env python
"""Install the class MODFLOW 6 into the active pixi environment.

The class mf6 is the SWI and VSF preview build released by this repository. Its
release also carries the DFN files the build was made from, and flopy's MODFLOW
6 classes are generated from them so they match the mf6 that reads the input.

Without arguments the script installs mf6 if it is missing and regenerates the
flopy classes if they no longer match it, which a reinstall of flopy causes;
it does nothing, and needs no network, when both are in order. ``--update``
installs the latest release if it is newer, ``--force`` reinstalls it, and
``--quiet`` (used by the activation hook) prints nothing when nothing is done.
"""

import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

# MF6_RELEASE_OWNER selects a fork's releases, to test a build made there
OWNER = os.environ.get("MF6_RELEASE_OWNER", "mjr-deltares")
REPO = "modflow-class-dsd26"
LATEST = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/latest"

# what the environment holds, written by this script: the release tag installed,
# and the flopy install its classes were generated for
STATE_DIR = Path(os.environ.get("CONDA_PREFIX", sys.prefix)) / "share" / REPO
TAG_FILE = STATE_DIR / "release"
DFN_DIR = STATE_DIR / "dfn"
STAMP_NAME = ".class-dfn-sync"


def log(msg, quiet=False):
    if not quiet:
        print(f"[get_mf6] {msg}")


def bindir():
    """Directory on PATH in this environment, where get-modflow ':python' installs."""
    sub = "Scripts" if sys.platform.startswith("win") else "bin"
    return Path(sys.prefix) / sub


def mf6_installed():
    exe = "mf6.exe" if sys.platform.startswith("win") else "mf6"
    return (bindir() / exe).exists()


def latest_release():
    """Tag and assets of the latest release, using GITHUB_TOKEN when it is set."""
    request = Request(LATEST, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urlopen(request, timeout=60) as response:
        release = json.load(response)
    return release["tag_name"], release["assets"]


def install_release(tag, assets, quiet=False):
    """Install mf6 and its DFN files from one release."""
    from flopy.utils import get_modflow

    log(f"installing mf6 from {OWNER}/{REPO} release {tag}", quiet)
    get_modflow(":python", owner=OWNER, repo=REPO, release_id=tag, quiet=quiet)

    dfns = [a for a in assets if a["name"].endswith("_dfns.zip")]
    if not dfns:
        sys.exit(f"[get_mf6] release {tag} has no DFN asset")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / dfns[0]["name"]
        with urlopen(dfns[0]["browser_download_url"], timeout=300) as response:
            path.write_bytes(response.read())
        if DFN_DIR.exists():
            shutil.rmtree(DFN_DIR)
        DFN_DIR.mkdir(parents=True)
        with zipfile.ZipFile(path) as z:
            z.extractall(DFN_DIR)
    TAG_FILE.write_text(f"{tag}\n")


def stamp_path():
    return Path(sysconfig.get_paths()["purelib"]) / "flopy" / STAMP_NAME


def fingerprint(tag):
    """The release tag and the flopy install, whose RECORD every install rewrites."""
    purelib = Path(sysconfig.get_paths()["purelib"])
    record = next(iter(purelib.glob("flopy-*.dist-info/RECORD")), None)
    return f"{tag} {record.stat().st_mtime_ns if record else 0}"


def sync_classes(tag, force=False, quiet=False):
    """Regenerate flopy's MODFLOW 6 classes from the DFN files of the release."""
    stamp = stamp_path()
    if not force and stamp.is_file() and stamp.read_text().strip() == fingerprint(tag):
        return
    log(f"generating flopy MODFLOW 6 classes from the {tag} DFN files", quiet)
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "flopy.mf6.utils.generate_classes",
            "--dfnpath",
            str(DFN_DIR),
            "--no-verbose",
        ]
    )
    # generation rewrites files flopy's RECORD tracks, so fingerprint afterwards
    stamp.write_text(f"{fingerprint(tag)}\n")


def main():
    args = sys.argv[1:]
    force = "--force" in args
    update = "--update" in args
    quiet = "--quiet" in args

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    installed = TAG_FILE.read_text().strip() if TAG_FILE.is_file() else None
    if force or update or installed is None or not mf6_installed():
        tag, assets = latest_release()
        if force or tag != installed or not mf6_installed():
            install_release(tag, assets, quiet)
            installed = tag
            force = True
        else:
            log(f"mf6 from release {tag} is already installed", quiet)
    sync_classes(installed, force=force, quiet=quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
