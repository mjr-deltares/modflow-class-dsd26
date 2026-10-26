"""Helpers for the synthetic-valley notebooks."""

import pathlib as pl
import pickle
import shutil

import flopy
import pandas as pd
import xarray as xr

DATA_ROOT = pl.Path(__file__).resolve().parent.parent / "data" / "synthetic-valley"
BASE_MODEL = DATA_ROOT / "synthetic-valley-coastal-base-annual"
ADVANCED_MODEL = DATA_ROOT / "synthetic-valley-coastal-advanced-annual"
TRUTH = DATA_ROOT / "data" / "synthetic_valley_vg_truth.nc"

# files only the base model uses, and the advanced-model files that replace
# them; MAW (sv.maw) is left for the notebook to add
BASE_ONLY = ("sv.rch", "sv.evt", "sv.riv", "sv.riv.obs", "sv.pwell.wel", "sv.gwf.obs")
ADVANCED_FILES = (
    "sv.dis",
    "sv.uzf",
    "sv.sfr",
    "sv.sfr.obs",
    "sv.lak",
    "sv.lak.obs",
    "sv.mvr",
    "sv.obs",
    "sv.prediction.well",
)
# observation of the stream flow leaving the model at the last reach
OUTFLOW_OBS = "riv-outflow"


def true_heads(kind):
    """True heads at the observation wells, one column per well, by time (days).

    ``kind`` is "wt" for the water table or "aq" for the lower aquifer.
    """
    ds = xr.open_dataset(TRUTH, decode_times=False)
    names = [v for v in ds.data_vars if v.startswith(f"obs_{kind}")]
    df = pd.DataFrame(
        {v[4:].upper(): ds[v].values for v in names}, index=ds["time"].values
    )
    df.index.name = "time"
    return df


def simulated_heads(ws, kind):
    """Simulated heads at the observation wells, read from the observation output."""
    return pd.read_csv(pl.Path(ws) / f"sv.gwf.{kind}.csv", index_col=0)


def build_advanced_without_maw(ws):
    """Write the base model with the advanced packages except MAW to ``ws``.

    RCH, EVT, RIV, and the pumping WEL are replaced by UZF, SFR, LAK, and MVR
    from the advanced model, and the lake cells in layer 1 are made inactive.
    """
    ws = pl.Path(ws)
    if ws.exists():
        shutil.rmtree(ws)
    shutil.copytree(BASE_MODEL, ws)
    for name in BASE_ONLY:
        (ws / name).unlink()
    for name in ADVANCED_FILES:
        shutil.copy(ADVANCED_MODEL / name, ws / name)

    # the advanced name file, without MAW
    nam = (ADVANCED_MODEL / "sv.nam").read_text().splitlines()
    (ws / "sv.nam").write_text(
        "\n".join(line for line in nam if not line.strip().lower().startswith("maw6"))
        + "\n"
    )

    # observe the flow out of the last reach, which is where the stream leaves
    # the model
    sfr = flopy.mf6.MFSimulation.load(
        sim_ws=ws, verbosity_level=0, load_only=["sfr"]
    ).get_model()
    nreaches = sfr.sfr.nreaches.data
    obs = (ws / "sv.sfr.obs").read_text()
    obs = obs.replace(
        "END continuous",
        f"  {OUTFLOW_OBS}  ext-outflow  {nreaches}\nEND continuous",
        1,
    )
    (ws / "sv.sfr.obs").write_text(obs)
    return flopy.mf6.MFSimulation.load(sim_ws=ws, verbosity_level=0)


def sfr_discharge(ws):
    """Stream discharge out of the model (m3/d, positive) at each output time."""
    df = pd.read_csv(pl.Path(ws) / "sv.sfr.obs.csv", index_col=0)
    return -df[OUTFLOW_OBS.upper()]


def record_sfr_discharge(path, rate, discharge):
    """Add the discharge for a pumping rate to the saved runs and return them all.

    The runs are a dictionary keyed by pumping rate, pickled to ``path``; a run
    already saved for the same rate is replaced.
    """
    path = pl.Path(path)
    runs = {}
    if path.exists():
        with open(path, "rb") as f:
            runs = pickle.load(f)
    runs[float(rate)] = discharge
    runs = dict(sorted(runs.items(), reverse=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(runs, f)
    return runs
