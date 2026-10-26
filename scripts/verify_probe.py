"""Check that the named programs are installed and will start.

Run by `pixi run verify` inside the class environment. Only the environment's
own program folders are searched, so another MODFLOW install on the PATH is not
mistaken for the class one. Exits non-zero if anything is missing or will not
start.

Catches the failure a student actually hits: the install finished, but a program
is missing, blocked by Gatekeeper or antivirus software, or built for a different
processor.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Programs that print a version banner and exit 0. The rest are still started -
# that is the only way to catch one built for a different processor - but their
# exit status is ignored, since a program started without an input file exits
# how it likes. Input is closed and each call is given a time limit so that
# nothing can sit waiting for the student to type something.
VERSION_FLAG = {"mf6": "-v"}

# where the environment keeps programs: bin on Linux and macOS, Scripts (where
# get-modflow ":python" installs) and Library/bin on Windows
PROGRAM_DIRS = os.pathsep.join(
    str(Path(sys.prefix) / d) for d in ("bin", "Scripts", "Library/bin")
)


def main(names: list[str]) -> int:
    missing: list[str] = []
    broken: list[str] = []

    for name in names:
        path = shutil.which(name, path=PROGRAM_DIRS)
        if path is None:
            print(f"  MISSING  {name}")
            missing.append(name)
            continue

        flag = VERSION_FLAG.get(name)
        cmd = [path, flag] if flag else [path]

        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except OSError as exc:
            # The important case: built for a different processor (Exec format
            # error), blocked by Gatekeeper or antivirus, or not runnable at all.
            print(f"  BROKEN   {name:<12} {path}\n           {exc}")
            broken.append(name)
            continue
        except subprocess.TimeoutExpired:
            # It started, which is all that is being asked of it here.
            print(f"  ok       {name:<12} {path} (started)")
            continue

        if flag and proc.returncode != 0:
            print(f"  BROKEN   {name:<12} {path} (exit {proc.returncode})")
            broken.append(name)
            continue

        banner = (proc.stdout or proc.stderr).strip().splitlines() if flag else []
        print(f"  ok       {name:<12} {banner[0] if banner else path}")

    if missing or broken:
        print()
        if missing:
            print(f"error: not installed: {', '.join(missing)}")
        if broken:
            print(f"error: installed but would not start: {', '.join(broken)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
