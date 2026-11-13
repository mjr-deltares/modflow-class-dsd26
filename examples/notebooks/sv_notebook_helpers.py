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
    "sv.ims",
    "sv.dis",
    "sv.ic",
    "sv.npf",
    "sv.drn",
    "sv.uzf",
    "sv.sfr",
    "sv.sfr.obs",
    "sv.lak",
    "sv.lak.obs",
    "sv.lak.tab",
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


def true_observations():
    """Every observed series in the truth, one column per observation, by time (days).

    The columns are the model's observation names in lower case: the heads at
    the observation wells (``wt01-i2-j17`` ...), the flows to the stream and
    the sea (``riv-swgw``, ``coast-swgw``), the lake stage, and the heads at
    the pumping and scenario wells (``reilly``, ``vc``, ``dw``).
    """
    ds = xr.open_dataset(TRUTH, decode_times=False)
    names = [v for v in ds.data_vars if v.startswith("obs_")]
    df = pd.DataFrame(
        {v[4:].lower(): ds[v].values for v in names}, index=ds["time"].values
    )
    df.index.name = "time"
    return df


def simulated_heads(ws, kind):
    """Simulated heads at the observation wells, read from the observation output."""
    return pd.read_csv(pl.Path(ws) / f"sv.gwf.{kind}.csv", index_col=0)


def build_advanced_without_maw(ws):
    """Write the base model with the advanced packages, except MAW, to ``ws``.

    The recharge, evapotranspiration, river, and pumping well packages are
    replaced by the advanced model's unsaturated zone (UZF), stream (SFR), lake
    (LAK), and Water Mover (MVR) packages. The solver settings, the grid and land
    surface, the starting heads, the hydraulic conductivity, and the seepage
    drains also come from the advanced model, because under the lake its layer 1
    cells are aquifer rather than the base model's very high hydraulic
    conductivity cells.
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


def restore_lake_k(k_file="sv.npf_k_layer1.txt", lake_file="lake_k.txt"):
    """Put the lake's hydraulic conductivity back into layer 1 after the K
    parameters are applied.

    `lake_file` holds the lake's K in the lake cells and 0 elsewhere. PstFrom
    copies this function into forward_run.py, so it does its own import.
    """
    import numpy as np

    k = np.loadtxt(k_file)
    lake = np.loadtxt(lake_file)
    k[lake > 0.0] = lake[lake > 0.0]
    np.savetxt(k_file, k, fmt="%15.6E")


def make_homogeneous(gwf, lake_k=1000.0):
    """Give each layer one value of every property, and recharge one rate per period.

    The hydraulic conductivity, vertical anisotropy, specific storage, and
    specific yield of each layer become the geometric mean of its active cells,
    and the recharge of each period, if the model has a recharge package, the
    mean rate of the cells that receive it. The lake cells in layer 1, whose
    hydraulic conductivity is above ``lake_k``, keep their values. This changes
    the model in memory; write it afterward.
    """
    import numpy as np

    idomain = gwf.dis.idomain.array
    lake = np.zeros(idomain.shape, dtype=bool)
    lake[0] = gwf.npf.k.array[0] > lake_k
    active = (idomain > 0) & ~lake
    for data in [gwf.npf.k, gwf.npf.k33, gwf.sto.ss, gwf.sto.sy]:
        values = data.array.copy()
        for k in range(values.shape[0]):
            mean = np.exp(np.log(values[k][active[k]]).mean())
            values[k][~lake[k]] = mean
        data.set_data(values)

    if gwf.get_package("rch") is None:
        return  # the advanced model has UZF, whose inputs are already uniform
    recharge = {}
    for kper, rate in gwf.rch.recharge.get_data().items():
        rate = rate.copy()
        wet = rate > 0.0
        rate[wet] = rate[wet].mean()
        recharge[kper] = rate
    gwf.rch.recharge.set_data(recharge)


def stream_flux_predictions(
    obs_file, column="RIV-SWGW", history_end=19723.0, out_file="sv.predictions.csv"
):
    """Write the groundwater discharge to the stream: steady state, history, future.

    ``obs_file`` is the stream observation file MODFLOW 6 writes (RIV in the base
    model, SFR in the advanced model), and ``column`` its aquifer-stream flow, which
    is negative when groundwater flows to the stream. The three predictions (m3/d)
    are the discharge of the steady state, the first output time; the smallest
    discharge of the history, through ``history_end``; and the smallest of the
    future after it. PstFrom copies this function into forward_run.py, so it does
    its own import.
    """
    import pandas as pd

    flows = pd.read_csv(obs_file, index_col=0)
    discharge = -flows[column]  # groundwater to the stream, positive
    history = discharge.loc[discharge.index <= history_end]
    future = discharge.loc[discharge.index > history_end]
    predictions = pd.DataFrame(
        {"discharge": [discharge.iloc[0], history.min(), future.min()]},
        index=pd.Index(["steadystate", "minhistory", "minfuture"], name="prediction"),
    )
    predictions.to_csv(out_file)
    return predictions
