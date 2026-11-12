# Installing the class software

The class uses a [pixi](https://pixi.sh) environment kept inside this folder:
its own Python, Python packages, PEST++, and the class MODFLOW 6, which has the
Seawater Intrusion (SWI) and Variably Saturated Flow (VSF) packages that are
not yet in a MODFLOW 6 release (see
[The class MODFLOW 6](README.md#the-class-modflow-6)). Nothing is
installed system-wide, and whatever Python you already use is untouched.

## 1. Install git

Check whether you have it:

```bash
git --version
```

If the command is not found, install it:

- **Windows** (PowerShell): `winget install --id Git.Git -e`, or the installer
  from [git-scm.com/download/win](https://git-scm.com/download/win)
- **macOS**: `xcode-select --install`, or `brew install git`
- **Linux**: `sudo apt install git` (Debian, Ubuntu) or `sudo dnf install git`
  (Fedora, RHEL)

## 2. Install pixi

- **Windows** (PowerShell):
  `powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"`,
  or `winget install prefix-dev.pixi`
- **macOS** and **Linux**: `curl -fsSL https://pixi.sh/install.sh | sh`, or
  `brew install pixi` on macOS

Open a new terminal afterwards so that `git` and `pixi` are found, and check
with `pixi --version`. If you already have pixi, update it with
`pixi self-update`.

## 3. Install the class environment

```bash
git clone https://github.com/mjr-deltares/modflow-class-dsd26.git
cd modflow-class-dsd26
pixi run setup
```

Use `git clone` rather than GitHub's **Download ZIP**, so the materials can be
brought up to date with `pixi run update` (see [Update](#5-update)).
`pixi run setup`

1. installs the Python environment (about 2 GB),
2. installs `mf6`, `libmf6`, `zbud6`, and `mf5to6` from the latest
   [release](https://github.com/mjr-deltares/modflow-class-dsd26/releases) of
   this repository,
3. generates FloPy's MODFLOW 6 classes from the definition files of that
   release, so FloPy has `ModflowGwfswi`, `ModflowGwfvsf`, and the other
   classes for the new packages, and
4. runs `mf6`, `zbud6`, and `pestpp-ies` to check that they start on your
   machine.

If it stops partway, run `pixi run setup` again; it picks up where it stopped.
Do this before you travel.

If the environment was installed another way, such as `pixi install`, the first
`pixi run` or `pixi shell` installs MODFLOW 6 and generates the FloPy classes.
This takes a few seconds and prints nothing; run `pixi run setup` to check that
everything starts.

## 4. Use the environment

```bash
pixi run jupyter            # start JupyterLab
pixi shell                  # a terminal with mf6, PEST++, python, and flopy ready to run
```

The class notebooks are in `examples/notebooks`.

To work in VS Code instead, open this folder with `pixi run code`, which first
installs MODFLOW 6 if it is missing. Opened with **File > Open Folder**, VS Code
does not install it, so run `pixi run setup` before opening the folder that way.
`.vscode/settings.json` makes the pixi environment the default Python
interpreter, so notebooks open with it as their kernel. VS Code offers to
install the extensions it needs: Python, Jupyter, and pixi-code, which lists the
pixi environment in the interpreter and kernel pickers. On Windows the setting
does not point to the interpreter, `.pixi\envs\default\python.exe`; pick the
pixi environment once with **Python: Select Interpreter**.

The models used in the class are described in
[`examples/data/README.md`](examples/data/README.md).

## 5. Update

Before the class, and when the instructors ask:

```bash
pixi run update
```

This downloads the latest class materials, replaces your copy with them, and
reinstalls the software, including the latest class MODFLOW 6, in case it has
changed.

### Files you have changed

Running a notebook changes it, because a notebook stores its output inside
itself. If the update would overwrite a file you changed, it lists the files
and asks what to do:

```
[update] these files you changed would be overwritten by the update:
       M examples/notebooks/synthetic-valley-a-base.ipynb

  What would you like to do?
    [s] set them aside - keeps your work; put it back with 'pixi run restore'
    [y] overwrite them - your changes are LOST
    [n] skip the update - leave everything as it is (default)

  Choice [s/y/N]:
```

- **`s`** sets your changes aside and updates the materials. Put the changes
  back on top of the updated files with `pixi run restore`. If you and the
  update changed the same lines of a file, `restore` writes both versions into
  the file between `<<<<<<<` and `>>>>>>>` markers, keeps the set-aside copy,
  and prints the commands to finish either way.
- **`y`** discards your changes and replaces the files with the latest versions.
- **`n`**, the default, leaves everything as it is.

Only files that came with the materials count. Model runs, such as
`examples/notebooks/models`, and other files you created are never touched.

To answer ahead of time:

```bash
pixi run update --stash         # always keep your changes
pixi run update --overwrite     # always discard your changes
pixi run update --no-install    # update the files, skip reinstalling the software
```

To keep your own work out of the way of updates, copy a notebook to a new name
or folder before changing it.

`pixi run update` works on the `main` branch; if you have switched to another
branch, it asks you to switch back first.

## Commands

Run `pixi run help` to list them in the terminal, grouped and in the order
they are used.

| Command | What it does |
|---|---|
| `setup` | install the class MODFLOW 6, then check that it and PEST++ start |
| `install` / `get-mf6` | install the class MODFLOW 6 and generate the FloPy classes for it |
| `verify` | check that `mf6`, `zbud6`, and `pestpp-ies` start |
| `update` | get the latest class materials and reinstall the software |
| `restore` | put back the changes an update set aside |
| `update-mf6` | install the latest class MODFLOW 6 if it is newer |
| `jupyter` | start JupyterLab |
| `code` | open this folder in VS Code (needs the `code` command on the PATH) |
| `help` | list every command in the order they are used |

## Which computers this works on

The class MODFLOW 6 is built for Windows (Intel or AMD), Linux (Intel or AMD),
and macOS 14 (Sonoma) or later on Apple silicon (M1 and later). It is not built
for Intel Macs or ARM Linux, and the environment will not install on them;
contact the instructors before the class if that is your computer.
