@echo off
rem Activation hook (Windows): regenerate flopy's MODFLOW 6 classes if a flopy
rem reinstall replaced them. Only once mf6 is installed, and never fails activation.
if exist "%CONDA_PREFIX%\share\modflow-class-dsd26\release" (
  python "%PIXI_PROJECT_ROOT%\scripts\get_mf6.py" --quiet || echo [get_mf6] WARNING: could not update the flopy classes; run "pixi run get-mf6 --force". 1>&2
)
