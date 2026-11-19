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


def build_variable_density(sim, ws, buoyancy=True):
    """Write ``sim`` and a seawater transport model to ``ws``; return the new simulation.

    ``sim`` is a simulation of the coastal valley whose GHB lists the
    concentration and elevation of the sea as auxiliary variables; it is not
    changed. The transport model ("salt") simulates the salt the coastal GHB
    brings into the aquifer, and the Buoyancy (BUY) package gives the flow model
    the density of the salty water. With ``buoyancy=False``, BUY is left out and
    the coastal GHB heads are raised to equivalent freshwater heads instead.
    """
    ws = pl.Path(ws)
    sim_ws = pl.Path(sim.sim_path)
    if ws.resolve() == sim_ws.resolve():
        raise ValueError("ws must differ from the workspace of sim")
    if ws.exists():
        shutil.rmtree(ws)

    # write a copy of sim to ws and build on the copy, so sim is not changed
    sim.set_sim_path(ws)
    sim.write_simulation(silent=True)
    sim.set_sim_path(sim_ws)
    sim = flopy.mf6.MFSimulation.load(
        sim_ws=ws, exe_name=sim.exe_name, write_headers=False, verbosity_level=0
    )
    gwf = sim.get_model()
    ghb = gwf.get_package("ghb")
    dis = gwf.dis

    # fresh water is 1,000 kg/m³ and gains 0.7 kg/m³ for each kg/m³ of salt
    if buoyancy:
        # the density of the sea at each GHB comes from its concentration
        # auxiliary variable
        flopy.mf6.ModflowGwfbuy(
            gwf,
            denseref=1000.0,
            nrhospecies=1,
            packagedata=[(0, 0.7, 0.0, "salt", "concentration")],
        )
    else:
        # equivalent freshwater head at the elevation of each GHB
        data = ghb.stress_period_data.get_data(0)
        ratio = (1000.0 + 0.7 * data["concentration"]) / 1000.0
        data["bhead"] += (ratio - 1.0) * (data["bhead"] - data["elevation"])
        ghb.stress_period_data.set_data({0: data})

    gwt = flopy.mf6.ModflowGwt(sim, modelname="salt")
    ims_gwt = flopy.mf6.ModflowIms(
        sim,
        filename="salt.ims",
        linear_acceleration="bicgstab",
        outer_maximum=50,
        outer_dvclose=1.0e-6,
        inner_maximum=300,
        inner_dvclose=1.0e-7,
    )
    sim.register_solution_package(ims_gwt, [gwt.name])

    flopy.mf6.ModflowGwtdis(
        gwt,
        nlay=dis.nlay.data,
        nrow=dis.nrow.data,
        ncol=dis.ncol.data,
        delr=dis.delr.array,
        delc=dis.delc.array,
        top=dis.top.array,
        botm=dis.botm.array,
        idomain=dis.idomain.array,
    )
    flopy.mf6.ModflowGwtic(gwt, strt=0.0)
    flopy.mf6.ModflowGwtmst(gwt, porosity=0.25)
    # upstream weighting, which stays stable in the 16,071-day steady-state step
    flopy.mf6.ModflowGwtadv(gwt, scheme="upstream")
    # longitudinal, horizontal transverse, and vertical transverse dispersivity, m
    flopy.mf6.ModflowGwtdsp(gwt, alh=15.0, ath1=1.5, atv=0.15)
    # the GHB water takes the concentration listed in its auxiliary variable
    flopy.mf6.ModflowGwtssm(gwt, sources=[(ghb.package_name, "AUX", "concentration")])
    flopy.mf6.ModflowGwtoc(
        gwt,
        concentration_filerecord="salt.ucn",
        saverecord=[("CONCENTRATION", "ALL")],
    )
    flopy.mf6.ModflowGwfgwt(
        sim, exgtype="GWF6-GWT6", exgmnamea=gwf.name, exgmnameb=gwt.name
    )
    sim.write_simulation(silent=True)
    return sim


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


# base-model layer (counted from 0) -> layer of the three-layer model: the two
# upper-aquifer layers and the two lower-aquifer layers are each combined
THREE_LAYER_MAP = {0: 0, 1: 0, 2: 1, 3: 2, 4: 2}


def _merge_cells(recarray, sum_fields=()):
    """Move list-input cells to the three-layer model.

    Cells that land in the same three-layer cell are combined, adding the
    fields in ``sum_fields`` (a conductance or a pumping rate).
    """
    merged = {}
    for rec in recarray:
        k, i, j = rec["cellid"]
        cellid = (THREE_LAYER_MAP[k], i, j)
        values = {n: rec[n] for n in rec.dtype.names if n != "cellid"}
        if cellid in merged:
            for n in sum_fields:
                merged[cellid][n] += values[n]
        else:
            merged[cellid] = values
    return [(cellid, *values.values()) for cellid, values in merged.items()]


def build_three_layer(ws):
    """Write the base model with three layers to ``ws`` and load it.

    Layers 1 and 2 (the upper aquifer) become layer 1, the clay stays as layer
    2, and layers 4 and 5 (the lower aquifer) become layer 3. Each combined
    layer takes the properties of its upper layer, which in the base model are
    the same for both, except that the lake cells of layer 1 now reach the
    bottom of the upper aquifer. Layer 1 stays convertible, as in the base
    model. The coastal GHB conductances and the pumping rates of cells that are
    combined are added together.
    """
    ws = pl.Path(ws)
    if ws.exists():
        shutil.rmtree(ws)
    base = flopy.mf6.MFSimulation.load(sim_ws=BASE_MODEL, verbosity_level=0)
    b = base.get_model("sv")
    keep = [0, 2, 3]  # base layer whose properties each new layer takes
    bottom = [1, 2, 4]  # base layer whose bottom is each new layer's bottom

    sim = flopy.mf6.MFSimulation(sim_name="sv", sim_ws=ws)
    flopy.mf6.ModflowTdis(
        sim,
        time_units="days",
        nper=base.tdis.nper.data,
        perioddata=base.tdis.perioddata.array.tolist(),
    )
    ims = base.get_package("ims")
    flopy.mf6.ModflowIms(
        sim,
        print_option="summary",
        complexity=ims.complexity.data,
        outer_dvclose=ims.outer_dvclose.data,
        outer_maximum=ims.outer_maximum.data,
        inner_maximum=ims.inner_maximum.data,
        inner_dvclose=ims.inner_dvclose.data,
        linear_acceleration="bicgstab",
        # plain ILU preconditioner; with SWI, the modified ILU of MODERATE
        # (relaxation 0.97) stalls the linear solve for some sea levels
        relaxation_factor=0.0,
    )
    gwf = flopy.mf6.ModflowGwf(
        sim, modelname="sv", newtonoptions="newton under_relaxation", save_flows=True
    )
    botm = b.dis.botm.array
    flopy.mf6.ModflowGwfdis(
        gwf,
        length_units="meters",
        nlay=3,
        nrow=b.dis.nrow.data,
        ncol=b.dis.ncol.data,
        delr=b.dis.delr.array,
        delc=b.dis.delc.array,
        top=b.dis.top.array,
        botm=botm[bottom],
        idomain=b.dis.idomain.array[keep],
    )
    flopy.mf6.ModflowGwfic(gwf, strt=b.ic.strt.array[keep])
    flopy.mf6.ModflowGwfnpf(
        gwf,
        icelltype=b.npf.icelltype.array[keep],
        k=b.npf.k.array[keep],
        k33=b.npf.k33.array[keep],
        k33overk=True,
        save_specific_discharge=True,
    )
    flopy.mf6.ModflowGwfsto(
        gwf,
        iconvert=b.sto.iconvert.array[keep],
        ss=b.sto.ss.array[keep],
        sy=b.sto.sy.array[keep],
        steady_state={0: True},
        transient={1: True},
    )

    # recharge, evapotranspiration, the river, and the drains are in layer 1
    spd = b.rch.stress_period_data.get_data()
    flopy.mf6.ModflowGwfrch(
        gwf,
        boundnames=True,
        stress_period_data={kper: d.tolist() for kper, d in spd.items()},
    )
    spd = b.evt.stress_period_data.get_data()
    flopy.mf6.ModflowGwfevt(
        gwf, stress_period_data={kper: d.tolist() for kper, d in spd.items()}
    )
    spd = b.riv.stress_period_data.get_data()
    flopy.mf6.ModflowGwfriv(
        gwf,
        boundnames=True,
        stress_period_data={kper: d.tolist() for kper, d in spd.items()},
        observations={"sv.riv.obs.csv": [("riv-swgw", "riv", "riv")]},
    )
    # seepage drains at the land surface, in layer 1
    spd = b.drn.stress_period_data.get_data()
    flopy.mf6.ModflowGwfdrn(
        gwf,
        auxiliary=["ddrn"],
        auxdepthname="ddrn",
        boundnames=True,
        stress_period_data={kper: d.tolist() for kper, d in spd.items()},
    )

    # the sea, with the elevation auxiliary variable reset to the middle of the
    # part of each combined cell that is below sea level
    top = gwf.dis.top.array
    new_botm = gwf.dis.botm.array
    ghb = []
    for cellid, bhead, cond, _, conc, name in _merge_cells(
        b.ghb.stress_period_data.get_data(0), sum_fields=("cond",)
    ):
        k, i, j = cellid
        cell_top = top[i, j] if k == 0 else new_botm[k - 1, i, j]
        elevation = 0.5 * (min(cell_top, 0.0) + new_botm[k, i, j])
        ghb.append((cellid, bhead, cond, elevation, conc, name))
    flopy.mf6.ModflowGwfghb(
        gwf,
        auxiliary=["elevation", "concentration"],
        boundnames=True,
        print_flows=True,
        stress_period_data={0: ghb},
        observations={"sv.ghb.obs.csv": [("coast-swgw", "ghb", "coast")]},
    )

    # the pumping wells, in the lower aquifer
    for pname in ("pwell", "prediction"):
        spd = b.get_package(pname).stress_period_data.get_data()
        flopy.mf6.ModflowGwfwel(
            gwf,
            pname=pname,
            filename=f"sv.{pname}.wel",
            boundnames=pname == "pwell",
            stress_period_data={
                kper: _merge_cells(d, sum_fields=("q",))
                for kper, d in spd.items()
                if d is not None
            },
        )

    # the observation wells, in their new layers
    continuous = {}
    for fname, recs in b.get_package("gwf-obs").continuous.data.items():
        continuous[fname] = [
            (r["obsname"], "head", (THREE_LAYER_MAP[r["id"][0]], *r["id"][1:]))
            for r in recs
        ]
    flopy.mf6.ModflowUtlobs(gwf, continuous=continuous, filename="sv.gwf.obs")
    flopy.mf6.ModflowGwfoc(
        gwf,
        head_filerecord="sv.hds",
        budget_filerecord="sv.cbc",
        budgetcsv_filerecord="sv-budget.csv",
        saverecord=[("head", "all"), ("budget", "all")],
    )
    sim.write_simulation(silent=True)
    return flopy.mf6.MFSimulation.load(sim_ws=ws, verbosity_level=0)
