[![Run class model](https://github.com/mjr-deltares/modflow-class-dsd26/actions/workflows/model-run.yml/badge.svg)](https://github.com/mjr-deltares/modflow-class-dsd26/actions/workflows/model-run.yml)

# Course Description
Class materials and schedule for the 2026 MODFLOW 6 advanced class at the DSD in Delft

## Class Schedule

**08:30 to 09:00 — ARRIVAL** \
09:00 to 09:05 — Welcome and introductions \
09:05 to 09:20 — MODFLOW 6 status and plans \
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

## The class MODFLOW 6

The class uses a development build of MODFLOW 6 with two packages that are not
yet in a MODFLOW 6 release: the Seawater Intrusion (SWI) Package and the
Variably Saturated Flow (VSF) Package, which solves the Richards equation for
unsaturated flow. It is built for Linux, Windows, and macOS on Apple silicon,
and posted under
[Releases](https://github.com/mjr-deltares/modflow-class-dsd26/releases) of
this repository, tagged with the UTC date and time of the build. The build is
checked nightly and made again whenever either package has changed. Builds are
posted as pre-releases, and the last 10 are kept. `pixi run setup` installs the
latest, and `pixi run update` installs a newer one, along with the latest class
materials, when there is one.

Outside the class environment, install the latest build with FloPy:

```shell
get-modflow --owner mjr-deltares --repo modflow-class-dsd26 :python
```

and generate the FloPy classes for the SWI and VSF packages from the DFN asset
of the same release, unzipped:

```shell
python -m flopy.mf6.utils.generate_classes --dfnpath <path to unzipped dfns>
```

These builds are provisional and are not MODFLOW 6 releases. How they are made
is described in [`.github/BUILD.md`](.github/BUILD.md).
