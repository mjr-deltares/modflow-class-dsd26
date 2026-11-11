#!/usr/bin/env bash
# Activation hook (Unix): install the class MODFLOW 6 the first time the
# environment is used, and afterwards regenerate flopy's MODFLOW 6 classes if a
# flopy reinstall replaced them. pixi does not show the hook's output, and the
# hook never fails activation; a failed install is retried on the next use.
python "${PIXI_PROJECT_ROOT}/scripts/get_mf6.py" --quiet || \
  echo "[get_mf6] WARNING: could not install MODFLOW 6 or update the flopy classes; run 'pixi run get-mf6 --force'." >&2
