#!/usr/bin/env bash
# Activation hook (Unix): regenerate flopy's MODFLOW 6 classes if a flopy
# reinstall replaced them. Only once mf6 is installed, so `pixi run install`
# is what installs it, and never fails activation.
if [ -f "${CONDA_PREFIX}/share/modflow-class-dsd26/release" ]; then
  python "${PIXI_PROJECT_ROOT}/scripts/get_mf6.py" --quiet || \
    echo "[get_mf6] WARNING: could not update the flopy classes; run 'pixi run get-mf6 --force'." >&2
fi
