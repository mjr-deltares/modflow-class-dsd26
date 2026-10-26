# Course Description
Class materials and schedule for the 2026 MODFLOW 6 advanced class at the DSD in Delft

[![Class environment model run](https://github.com/mjr-deltares/modflow-class-dsd26/actions/workflows/model-run.yml/badge.svg)](https://github.com/mjr-deltares/modflow-class-dsd26/actions/workflows/model-run.yml)

## Getting started

The class uses a [pixi](https://pixi.sh) environment kept inside this folder:
its own Python, Python packages, and the class MODFLOW 6, which has the
Seawater Intrusion (SWI) and Variably Saturated Flow (VSF) packages that are
not yet in a MODFLOW 6 release (see [MODFLOW 6 preview build](#modflow-6-preview-build)).
Nothing is installed system-wide, and whatever Python you already use is
untouched.

### 1. Install git

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

### 2. Install pixi

- **Windows** (PowerShell):
  `powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"`,
  or `winget install prefix-dev.pixi`
- **macOS** and **Linux**: `curl -fsSL https://pixi.sh/install.sh | sh`, or
  `brew install pixi` on macOS

Open a new terminal afterwards so that `git` and `pixi` are found, and check
with `pixi --version`. If you already have pixi, update it with
`pixi self-update`.

### 3. Install the class environment

```bash
git clone https://github.com/mjr-deltares/modflow-class-dsd26.git
cd modflow-class-dsd26
pixi run setup
```

Use `git clone` rather than GitHub's **Download ZIP**, so the materials can be
brought up to date with `git pull`. `pixi run setup`

1. installs the Python environment (about 2 GB),
2. installs `mf6`, `libmf6`, `zbud6`, and `mf5to6` from the latest
   [release](../../releases) of this repository,
3. generates FloPy's MODFLOW 6 classes from the definition files of that
   release, so FloPy has `ModflowGwfswi`, `ModflowGwfvsf`, and the other
   classes for the new packages, and
4. runs `mf6` and `zbud6` to check that they start on your machine.

If it stops partway, run `pixi run setup` again; it picks up where it stopped.
Do this before you travel.

### 4. Use the environment

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

The synthetic-valley models used in the class are in
`examples/data/synthetic-valley`, in meters and days:

| Model | Grid | Represents |
|---|---|---|
| `synthetic-valley-coastal-base-annual` | structured | the valley with RCH, EVT, RIV, and WEL, and a coastal GHB |
| `synthetic-valley-coastal-advanced-annual` | structured | the valley with UZF, SFR, LAK, MVR, and MAW, and a coastal GHB |
| `synthetic-valley-coastal-vg-base-annual` | Voronoi | the base model on a Voronoi grid |
| `synthetic-valley-coastal-vg-advanced-annual` | Voronoi | the advanced model on a Voronoi grid, which defines the truth |

`examples/data/synthetic-valley/data` holds the truth dataset the models are
built from and the heads and observations of the Voronoi-grid advanced model.

### 5. Update

Before the class, and when the instructors ask:

```bash
git pull
pixi run update-mf6         # install the latest class MODFLOW 6 if it is newer
```

### Commands

Run `pixi run help` to list them in the terminal.

| Command | What it does |
|---|---|
| `setup` | install the class MODFLOW 6, then check that it starts |
| `install` / `get-mf6` | install the class MODFLOW 6 and generate the FloPy classes for it |
| `update-mf6` | install the latest class MODFLOW 6 if it is newer |
| `verify` | check that `mf6` and `zbud6` start |
| `jupyter` | start JupyterLab |
| `help` | list every command |

### Which computers this works on

The class MODFLOW 6 is built for Windows (Intel or AMD), Linux (Intel or AMD),
and macOS on Apple silicon (M1 and later). It is not built for Intel Macs or
ARM Linux, and the environment will not install on them; contact the
instructors before the class if that is your computer.

## MODFLOW 6 preview build

Developmode builds of MODFLOW 6 with two development branches used in the class,
neither of which has been merged into MODFLOW 6:

- the `feat-swi` branch of
  [christianlangevin/modflow6](https://github.com/christianlangevin/modflow6/tree/feat-swi),
  the Seawater Intrusion (SWI) Package, and
- the `vsf-dev` branch of
  [mjr-deltares/modflow6](https://github.com/mjr-deltares/modflow6/tree/vsf-dev),
  the Variably Saturated Flow (VSF) Package, which solves the Richards equation
  for unsaturated flow,

merged into a single `mf6`.

The build uses the MODFLOW 6 release workflow in developmode, as the
[MODFLOW 6 nightly build](https://github.com/MODFLOW-ORG/modflow6-nightly-build) does:
binaries for Linux and Windows built with the Intel classic compiler, binaries for
macOS on Apple silicon built with gfortran, the tests, and the documentation.
Each build is posted under [Releases](../../releases), tagged with the UTC date
and time of the build and the two commits (`YYYYMMDD-HHMM-<feat-swi>-<vsf-dev>`);
the newest is marked Latest, and the last 10 are kept.

`vsf-dev` is merged into `feat-swi` once, in the first job, by the
`.github/actions/merge-vsf` action; the merge commit is passed to the build,
documentation, and distribution jobs as a git bundle, so every platform builds
the same source. The two branches conflict in
`src/Model/GroundWaterFlow/gwf.f90`; the resolution is recorded in
`.github/rr-cache` and replayed by `git rerere`. If a change to either branch
causes a conflict with no recorded resolution, the build stops at the merge in
the first job and lists the files. Resolve the merge locally with rerere enabled
and copy the new entries in `.git/rr-cache` to `.github/rr-cache`:

```shell
git clone -b feat-swi https://github.com/christianlangevin/modflow6.git
cd modflow6
mkdir -p .git/rr-cache && cp -R ../.github/rr-cache/. .git/rr-cache/
git config rerere.enabled true
git pull --no-rebase https://github.com/mjr-deltares/modflow6.git vsf-dev
# resolve the conflicts, then
git add -A && git commit --no-edit
cp -R .git/rr-cache/. ../.github/rr-cache/
```

The extended Windows build (parallel and NetCDF) is left out. To do that, the
workflow calls a copy of `.github/workflows/release.yml` from `feat-swi` with
the extended entries removed from the build and distribution matrices,
`${{ github.repository_owner }}/modflow6` replaced by `christianlangevin/modflow6`,
and steps added to check out the merge commit from the bundle. If the release workflow on the
branch changes, refresh the copy:

```shell
curl -sL https://raw.githubusercontent.com/christianlangevin/modflow6/feat-swi/.github/workflows/release.yml > .github/workflows/release.yml
```

and make the same changes again.

The workflow runs nightly in mjr-deltares/modflow-class-dsd26 and builds only
when either branch has changed since the last release. Run it by hand from the
Actions tab, with `force` to rebuild unchanged branches; a fork runs it only by
hand.

Install the latest build with FloPy:

```shell
get-modflow --owner mjr-deltares --repo modflow-class-dsd26 :python
```

and generate the FloPy classes for the merged packages from the DFN asset of the
same release, unzipped:

```shell
python -m flopy.mf6.utils.generate_classes --dfnpath <path to unzipped dfns>
```

These builds are provisional and are not MODFLOW 6 releases.
