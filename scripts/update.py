#!/usr/bin/env python
"""Bring the class materials up to date, and put back changes set aside.

``update`` fetches the latest class materials from the class repository and
reinstalls the software. If files that came with the materials have been
changed, it asks whether to set the changes aside, overwrite them, or leave the
materials as they are; ``--stash`` and ``--overwrite`` answer ahead of time, and
``--no-install`` skips the reinstall. ``restore`` puts the changes an update set
aside back on top of the updated files. Files that did not come with the
materials, such as model runs, are never touched.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://github.com/mjr-deltares/modflow-class-dsd26.git"
BRANCH = "main"

# written into the label of what update sets aside, so restore can tell it from
# anything set aside by hand
STASH_MARKER = "pre-update (modflow-class-dsd26)"

# files pixi may rewrite on its own, which are overwritten without asking
IGNORED_PATHS = {"pixi.lock"}


def log(msg):
    print(f"[update] {msg}", flush=True)


def run(cmd, check=True, env=None):
    """Run a command in the repository, echoing it first."""
    print(f"  $ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    if check and proc.returncode != 0:
        sys.exit(f"[update] command failed ({proc.returncode}): {' '.join(cmd)}")
    return proc.returncode


def git_out(args):
    """Output of a git command, or "" if it fails."""
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def changed_files():
    """Files that came with the materials and have been changed."""
    out = git_out(["status", "--porcelain", "--untracked-files=no"])
    lines = [line for line in out.splitlines() if line.strip()]
    return [line for line in lines if line[3:].strip() not in IGNORED_PATHS]


def ask(changes, commits):
    """Ask what to do about changed files: "stash", "overwrite", or "skip"."""
    log("these files you changed would be overwritten by the update:")
    for line in changes[:20]:
        print(f"      {line}")
    if len(changes) > 20:
        print(f"      ... and {len(changes) - 20} more")
    if commits:
        print(f"      (plus {commits} commit(s) of your own)")
    print()
    print("  What would you like to do?")
    print(
        "    [s] set them aside - keeps your work; put it back with 'pixi run restore'"
    )
    print("    [y] overwrite them - your changes are LOST")
    print("    [n] skip the update - leave everything as it is (default)")
    print()

    if not sys.stdin.isatty():
        log(
            "no one is here to answer; skipping. Run again with --stash or --overwrite."
        )
        return "skip"

    while True:
        try:
            answer = input("  Choice [s/y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "skip"
        if answer in ("s", "stash"):
            return "stash"
        if answer in ("y", "yes", "o", "overwrite"):
            return "overwrite"
        if answer in ("", "n", "no", "skip"):
            return "skip"
        print("  Please answer s, y, or n.")


def pixi_env():
    """Environment for a nested pixi call, without this environment's variables."""
    env = dict(os.environ)
    for var in list(env):
        if var.startswith(("PIXI_", "CONDA_")):
            del env[var]
    return env


def reinstall():
    """Install the packages recorded in pixi.lock and the latest class MODFLOW 6."""
    log("reinstalling the software")
    env = pixi_env()
    # --locked installs the recorded versions without rewriting pixi.lock
    if run(["pixi", "install", "--locked"], check=False, env=env) != 0:
        log("pixi.lock does not match pixi.toml; letting pixi work out the versions")
        run(["pixi", "install"], env=env)
    if run(["pixi", "run", "update-mf6"], check=False, env=env) != 0:
        sys.exit(
            "[update] the materials are up to date, but the software could not be "
            "reinstalled.\n  Run 'pixi run update-mf6' to try again."
        )


def update(args):
    branch = git_out(["branch", "--show-current"])
    if branch != BRANCH:
        sys.exit(
            f"[update] the materials are on '{branch or 'no branch'}', not "
            f"'{BRANCH}'.\n  Switch back with 'git switch {BRANCH}' and run the "
            "update again."
        )

    log(f"fetching the latest class materials from {URL}")
    run(["git", "fetch", URL, BRANCH])

    changes = changed_files()
    commits = int(git_out(["rev-list", "--count", "FETCH_HEAD..HEAD"]) or 0)
    if changes or commits:
        if args.stash:
            choice = "stash"
        elif args.overwrite:
            choice = "overwrite"
        else:
            choice = ask(changes, commits)

        if choice == "skip":
            log("skipped; nothing was changed")
            return 0
        if choice == "stash" and changes:
            run(["git", "stash", "push", "-m", STASH_MARKER])
            log("your changes are set aside; put them back with 'pixi run restore'")
        if commits:
            log(
                f"{commits} commit(s) of your own are dropped by the update; "
                "'git reflog' can still recover them"
            )

    # reset rather than merge, so that the materials match the class repository
    # whatever state they were left in
    run(["git", "reset", "--hard", "FETCH_HEAD"])
    log(f"the materials are now at {git_out(['log', '-1', '--format=%h %s'])}")

    if not args.no_install:
        reinstall()
    return 0


def restore(args):
    out = git_out(["stash", "list", "--format=%gd\t%s"])
    stashes = [line.split("\t", 1) for line in out.splitlines() if "\t" in line]
    ours = [ref for ref, desc in stashes if STASH_MARKER in desc]

    if not ours:
        if stashes:
            log("nothing was set aside by 'pixi run update', but there is:")
            for ref, desc in stashes:
                print(f"      {ref}  {desc}")
            print("\n  Put one back by hand with 'git stash pop <ref>'.")
        else:
            log("nothing was set aside, so there is nothing to put back")
        return 0

    if changed_files() and sys.stdin.isatty():
        log("other files have been changed since; the two versions may collide.")
        try:
            if input("  Continue? [y/N]: ").strip().lower() not in ("y", "yes"):
                log("skipped; what was set aside is untouched")
                return 0
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

    log("putting your changes back")
    if run(["git", "stash", "pop", ours[0]], check=False) != 0:
        # unmerged paths mean the files were written with conflict markers; none
        # means git refused to start and nothing changed
        if git_out(["ls-files", "--unmerged"]):
            print(
                "  Your changes and the update touch the same lines. Both versions\n"
                "  are written into those files between <<<<<<< and >>>>>>> markers,\n"
                "  and the set-aside copy is kept, so nothing is lost. Edit the files\n"
                "  down to what you want, then run\n"
                "      git add <file>\n"
                "      git stash drop\n"
                "  or, to take the updated files instead,\n"
                "      git reset --hard && git stash drop"
            )
        else:
            print(
                "  Your changes could not be put back because the same files have\n"
                "  been edited again since. Nothing has changed and nothing is lost.\n"
                "  Set the newer edits aside with 'git stash push -m \"newer edits\"',\n"
                "  or discard them with 'git checkout -- .', then run\n"
                "  'pixi run restore' again."
            )
        return 1

    log("your changes are back")
    if len(ours) > 1:
        log(f"{len(ours) - 1} older set(s) of changes from earlier updates remain")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["update", "restore"])
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--stash", action="store_true", help="set changed files aside without asking"
    )
    group.add_argument(
        "--overwrite", action="store_true", help="discard changed files without asking"
    )
    parser.add_argument(
        "--no-install", action="store_true", help="do not reinstall the software"
    )
    args = parser.parse_args()
    return update(args) if args.command == "update" else restore(args)


if __name__ == "__main__":
    sys.exit(main())
