# Installing the class software

The class uses a [pixi](https://pixi.sh) environment kept inside this folder:
its own Python, Python packages, PEST++, and the class MODFLOW 6, which has the
Seawater Intrusion (SWI) and Variably Saturated Flow (VSF) packages that are
not yet in a MODFLOW 6 release (see
[MODFLOW 6 preview build](README.md#modflow-6-preview-build)). Nothing is
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
brought up to date with `git pull`. `pixi run setup`

1. installs the Python environment (about 2 GB),
2. installs `mf6`, `libmf6`, `zbud6`, and `mf5to6` from the latest
   [release](https://github.com/mjr-deltares/modflow-class-dsd26/releases) of
   this repository,
3. generates FloPy's MODFLOW 6 classes from the definition files of that
   release, so FloPy has `ModflowGwfswi`, `ModflowGwfvsf`, and the other
   classes for the new packages, and
4. runs `mf6` and `zbud6` to check that they start on your machine.

If it stops partway, run `pixi run setup` again; it picks up where it stopped.
Do this before you travel.

## 4. Use the environment

```bash
pixi run jupyter            # start JupyterLab
pixi shell                  # a terminal with mf6, python, and flopy ready to run
```

To work in VS Code instead, open this folder with **File > Open Folder** after
`pixi run setup`. `.vscode/settings.json` makes the pixi environment the default
Python interpreter, so notebooks open with it as their kernel, and VS Code
offers to install the Python and Jupyter extensions it needs. On Windows the
interpreter is `.pixi\envs\default\python.exe`, which the setting does not
point to; pick it once with **Python: Select Interpreter**.

The models used in the class are described in
[`examples/data/README.md`](examples/data/README.md).

## 5. Update

Before the class, and when the instructors ask:

```bash
git pull
pixi run update-mf6         # install the latest class MODFLOW 6 if it is newer
```

## Commands

Run `pixi run help` to list them in the terminal.

| Command | What it does |
|---|---|
| `setup` | install the class MODFLOW 6, then check that it starts |
| `install` / `get-mf6` | install the class MODFLOW 6 and generate the FloPy classes for it |
| `update-mf6` | install the latest class MODFLOW 6 if it is newer |
| `verify` | check that `mf6` and `zbud6` start |
| `jupyter` | start JupyterLab |
| `help` | list every command |

## Which computers this works on

The class MODFLOW 6 is built for Windows (Intel or AMD), Linux (Intel or AMD),
and macOS 14 (Sonoma) or later on Apple silicon (M1 and later). It is not built
for Intel Macs or ARM Linux, and the environment will not install on them;
contact the instructors before the class if that is your computer.
