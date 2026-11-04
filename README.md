[![Class environment model run](https://github.com/mjr-deltares/modflow-class-dsd26/actions/workflows/model-run.yml/badge.svg)](https://github.com/mjr-deltares/modflow-class-dsd26/actions/workflows/model-run.yml)

# Course Description
Class materials and schedule for the 2026 MODFLOW 6 advanced class at the DSD in Delft

## Class Schedule

**08:30 to 09:00 — ARRIVAL** \
09:00 to 09:05 — Welcome and introductions \
09:05 to 09:20 — MODFLOW 6 and PEST++ status and plans \
09:20 to 10:20 — Advanced packages (incl. setting up class environment) \
10:20 to 10:40 — PEST++ and Iterative Ensemble Smoothing (part 1) \
**10:40 to 11:00 — COFFEE BREAK** \
11:00 to 12:00 — PEST++ and Iterative Ensemble Smoothing (part 2) \
12:00 to 12:25 — Variably Saturated Flow (part 1) \
**12.25 to 12.30 — GROUP PICTURE** \
**12:30 to 13:30 — LUNCH BREAK** \
13:30 to 14:15 — Variably Saturated Flow (part 2) \
14:15 to 15:00 — The SWI package for seawater intrusion (part 1) \
**15:00 to 15:20 — COFFEE BREAK** \
15:20 to 15:40 — The SWI package for seawater intrusion (part 2) \
15:40 to 16:00 — The MODFLOW API \
16:00 to 16:30 — MODFLOW 6 and the iMOD Suite \
16:30 to 17:00 — Wrap-up \
**17:00 to 18:00 — DRINKS**

## Installing class software

The class uses a [pixi](https://pixi.sh) environment with Python, FloPy,
PEST++, pyEMU, and a MODFLOW 6 built with the Seawater Intrusion (SWI) and
Variably Saturated Flow (VSF) packages. Follow [`INSTALL.md`](INSTALL.md) to
install it: it covers installing git and pixi, downloading the class materials,
setting up the environment, using it from JupyterLab or VS Code, updating the
materials and software with `pixi run update`, and the computers it works on.
The class notebooks are in [`examples/notebooks`](examples/notebooks), and the
models they use are described in
[`examples/data/README.md`](examples/data/README.md).

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
