# Building the class MODFLOW 6

How `.github/workflows/preview-build.yml` builds the class MODFLOW 6 release,
and what to do when the build stops.

Each release is a developmode build of MODFLOW 6 from two development branches,
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
Each build is posted under [Releases](https://github.com/mjr-deltares/modflow-class-dsd26/releases), tagged with the UTC date
and time of the build and the two commits (`YYYYMMDD-HHMM-<feat-swi>-<vsf-dev>`);
builds are posted as pre-releases, so another release, such as the class
presentations, can be marked Latest. The last `KEEP_BUILDS` (10) builds are
kept; other releases are never deleted.

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

To test a build made in a fork, set `MF6_RELEASE_OWNER` to the fork's owner
before `pixi run get-mf6 --force`, and `scripts/get_mf6.py` installs the fork's
latest release instead.
