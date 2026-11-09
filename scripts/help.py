"""List the class pixi tasks in the order they are used.

Run by `pixi run help`. Tasks are grouped by the `# --- <section> ---` comments
in pixi.toml and listed in the order they appear there, with each task's
dependencies in the same section indented below it.
"""

import re
import sys
import tomllib
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent.parent / "pixi.toml"
TABLE = "[feature.mf6.tasks]"
SECTION = re.compile(r"^#\s*---\s*(.+?)\s*-*\s*$")
TASK = re.compile(r"^([A-Za-z0-9_-]+)\s*=")


def sections(text):
    """Section titles and their task names, in file order."""
    found = []
    inside = False
    for line in text.splitlines():
        if line.startswith("["):
            inside = line.strip() == TABLE
            continue
        if not inside:
            continue
        match = SECTION.match(line)
        if match:
            found.append((match.group(1).capitalize(), []))
            continue
        match = TASK.match(line)
        if match:
            if not found:
                found.append(("Tasks", []))
            found[-1][1].append(match.group(1))
    return found


def rows(name, members, tasks, depth=0):
    """A task and, indented below it, its dependencies in the same section."""
    yield depth, name, tasks[name].get("description", "")
    for dep in tasks[name].get("depends-on", []):
        if dep in members:
            yield from rows(dep, members, tasks, depth + 1)


def main():
    text = MANIFEST.read_text(encoding="utf-8")
    tasks = tomllib.loads(text)["feature"]["mf6"]["tasks"]
    listed = []
    for title, names in sections(text):
        members = set(names)
        # a task another task in the section depends on is listed under it
        nested = set()
        for name in names:
            for dep in tasks[name].get("depends-on", []):
                nested.add(dep)
        lines = []
        for name in names:
            if name not in nested:
                lines.extend(rows(name, members, tasks))
        listed.append((title, lines))

    width = 0
    for _, lines in listed:
        for depth, name, _ in lines:
            width = max(width, 2 * depth + len(name))
    for title, lines in listed:
        print(title)
        for depth, name, description in lines:
            label = "  " * depth + name
            print(f"  {label:<{width}}  {description}")
    print("\nRun one with: pixi run <task>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
