"""Helpers for the variably saturated flow (VSF) notebook.

This module keeps the mechanical parts of the VSF notebook out of the way so the
notebook can focus on what changes when the Richards-based VSF package goes into
the synthetic-valley model:

- ``SOILS`` and the van Genuchten functions give the soil-characteristic curves.
- ``load_valley`` loads the base valley model that the notebook starts from.
- ``lake_stage`` and ``set_lake`` hold the lake at the base model's level.
- ``refine_top_layer`` splits layer 1 into thin sublayers and remaps the grid,
  the aquifer properties, and every boundary package onto the finer grid.
- ``water_table`` turns a VSF pressure-head field into a water-table surface.
- ``aquifer_budget`` runs ZONEBUDGET for the aquifer outside the lake.

Units follow the synthetic-valley model: meters and days.
"""

import pathlib as pl

import flopy
import numpy as np
from sv_notebook_helpers import BASE_MODEL

# van Genuchten soil parameters (Carsel & Parrish, 1988), converted to the
# model units of meters and days. ``porosity`` is the saturated water content
# (theta_s); ``satres`` is the residual *saturation* (theta_r / theta_s) that the
# VSF package expects; ``alpha`` is in 1/m; ``ks`` is the saturated hydraulic
# conductivity in m/d.
SOILS = {
    "sand": {
        "porosity": 0.43,
        "satres": 0.045 / 0.43,
        "alpha": 14.5,
        "n": 2.68,
        "ks": 7.13,
    },
    "loam": {
        "porosity": 0.43,
        "satres": 0.078 / 0.43,
        "alpha": 3.6,
        "n": 1.56,
        "ks": 0.25,
    },
    "clay": {
        "porosity": 0.38,
        "satres": 0.068 / 0.38,
        "alpha": 0.8,
        "n": 1.09,
        "ks": 0.05,
    },
}


def van_genuchten_saturation(psi, soil):
    """Water saturation (0-1) at pressure head ``psi`` (m) for a ``SOILS`` entry.

    ``psi`` is negative in the unsaturated zone. At and above the water table
    (``psi >= 0``) the medium is fully saturated.
    """
    psi = np.asarray(psi, dtype=float)
    n = soil["n"]
    m = 1.0 - 1.0 / n
    sr = soil["satres"]
    se = np.where(psi < 0.0, (1.0 + (soil["alpha"] * -psi) ** n) ** (-m), 1.0)
    return sr + (1.0 - sr) * se


def van_genuchten_theta(psi, soil):
    """Volumetric water content theta at pressure head ``psi`` (m)."""
    return soil["porosity"] * van_genuchten_saturation(psi, soil)


def van_genuchten_kr(psi, soil):
    """Relative permeability (0-1) at pressure head ``psi`` (m)."""
    psi = np.asarray(psi, dtype=float)
    n = soil["n"]
    m = 1.0 - 1.0 / n
    sr = soil["satres"]
    sat = van_genuchten_saturation(psi, soil)
    se = np.clip((sat - sr) / (1.0 - sr), 0.0, 1.0)
    kr = np.sqrt(se) * (1.0 - (1.0 - se ** (1.0 / m)) ** m) ** 2
    return np.where(psi < 0.0, kr, 1.0)


def water_table(head, phead):
    """Water-table elevation per column from VSF head and pressure-head arrays.

    The water table is the shallowest cell whose pressure head is non-negative;
    its hydraulic head equals the water-table elevation. ``head`` and ``phead``
    are ``(nlay, nrow, ncol)`` arrays. Returns a masked ``(nrow, ncol)`` array.
    """
    nlay, nrow, ncol = head.shape
    wt = np.full((nrow, ncol), np.nan)
    # inactive and pass-through cells are written as 1e30, which is not saturated
    wet = (phead >= 0.0) & (phead < 1e29)
    for i in range(nrow):
        for j in range(ncol):
            sat = np.nonzero(wet[:, i, j])[0]
            if sat.size:
                wt[i, j] = head[sat[0], i, j]
    return np.ma.masked_invalid(wt)


def _rebuild_boundaries(gwf, riv_layer=None, ghb_layer=None):
    """Rebuild the river and coastal GHB without their observation packages.

    The base packages point at observation files for the base grid. ``riv_layer``
    and ``ghb_layer`` choose each cell's layer; by default the layer is kept.
    """
    riv = gwf.get_package("RIV-1").stress_period_data.get_data()[0]
    riv_new = []
    for c in riv:
        layer, i, j = c[0]
        layer = riv_layer(i, j, c[1]) if riv_layer else layer
        riv_new.append([(layer, i, j), *list(c)[1:]])
    gwf.remove_package("RIV-1")
    flopy.mf6.ModflowGwfriv(
        gwf, boundnames=True, stress_period_data={0: riv_new}, pname="RIV-1"
    )

    ghb = gwf.get_package("GHB-1").stress_period_data.get_data()[0]
    ghb_new = []
    for c in ghb:
        layer, i, j = c[0]
        layer = ghb_layer(layer, i, j, c[1]) if ghb_layer else layer
        ghb_new.append([(layer, i, j), *list(c)[1:]])
    gwf.remove_package("GHB-1")
    flopy.mf6.ModflowGwfghb(
        gwf,
        auxiliary=["elevation", "concentration"],
        boundnames=True,
        stress_period_data={0: ghb_new},
        pname="GHB-1",
    )


def load_valley(ws):
    """Load the base synthetic-valley model, ready to be written to ``ws``.

    Evapotranspiration (EVT), the land-surface seepage drains (DRN), and the
    observation packages are left out. Recharge, the river, the coastal
    general-head boundary, and the pumping wells stay.
    """
    sim = flopy.mf6.MFSimulation.load(
        sim_name="sv", sim_ws=str(BASE_MODEL), verbosity_level=0
    )
    gwf = sim.get_model("sv")
    for name in ("EVT_0", "DRN-1", "GWF-OBS", "GHB_OBS", "RIV_OBS"):
        if name in gwf.get_package_list():
            gwf.remove_package(name)
    _rebuild_boundaries(gwf)
    sim.set_sim_path(str(ws))
    return sim, gwf


# terms of the aquifer budget and the ZONEBUDGET names they come from
BUDGET_TERMS = {
    "RCH": "RCH",
    "LAKE": "ZONE_2",
    "RIV": "RIV",
    "GHB": "GHB",
    "STO-SY": "STO_SY",
    "STO-UZ": "STO_UZ",
    "STO-SS": "STO_SS",
    "WEL": "PWELL_WEL",
    "WEL2": "PREDICTION_WEL",
}


def lake_cells(gwf):
    """Cells of the lake, which the valley builds from very permeable cells."""
    return gwf.npf.k.array > 1.0e4


def lake_stage(ws, gwf):
    """Lake level (m) at the end of every time step of a base-valley run.

    Returns ``(times, stages)``; the level is the mean head in the lake cells of
    layer 1.
    """
    lake = lake_cells(gwf)[0]
    heads = flopy.utils.HeadFile(str(pl.Path(ws) / "sv.hds"))
    times = np.array(heads.get_times())
    stages = np.array([heads.get_data(totim=t)[0][lake].mean() for t in times])
    return times, stages


def set_lake(gwf, times, stages):
    """Hold every lake cell at the lake level with constant heads (CHD).

    ``times`` and ``stages`` are the ends of the time steps and the level at each,
    as from ``lake_stage``; the model must use the same time steps. Each level is
    held through its time step.
    """
    cells = [tuple(int(v) for v in c) for c in np.argwhere(lake_cells(gwf))]
    chd = flopy.mf6.ModflowGwfchd(
        gwf, stress_period_data={0: [[c, "stage"] for c in cells]}, pname="CHD-LAKE"
    )
    # MODFLOW 6 averages a time series over each time step, so a stepwise series
    # that starts each level at the start of its step gives that level exactly
    starts = [0.0, *times[:-1]]
    series = [(float(t), float(h)) for t, h in zip(starts, stages)]
    chd.ts.initialize(
        filename="sv.lake.ts",
        timeseries=[*series, (float(times[-1]), float(stages[-1]))],
        time_series_namerecord="stage",
        interpolation_methodrecord="stepwise",
    )


def set_substeps(sim, nstp):
    """Split every transient stress period into ``nstp`` time steps.

    The steady-state first period keeps its single step.
    """
    perioddata = sim.tdis.perioddata.get_data()
    sim.tdis.perioddata.set_data(
        [
            (float(p[0]), 1 if n == 0 else nstp, float(p[2]))
            for n, p in enumerate(perioddata)
        ]
    )


def refine_top_layer(sim, target_dz=0.25, refine_depth=2.0):
    """Split layer 1 into thin sublayers so the unsaturated zone has cells.

    The top ``refine_depth`` meters of layer 1 are divided into sublayers of about
    ``target_dz`` meters, and one transition cell takes what is left down to the
    original layer-1 bottom. The deeper layers are unchanged, so the layer
    numbers below layer 1 move down by the number of new sublayers.

    Everything that lives on the grid is remapped on ``sim`` in place: the
    discretization, the starting heads, the hydraulic conductivity and storage,
    recharge (still on the top cell), and the river, coastal general-head
    boundary, and wells. A boundary that was in layer 1 goes in the sublayer that
    brackets its control elevation, so it exchanges water with the aquifer
    there. Returns the number of refined sublayers ``n_ref``; the transition
    cell is layer ``n_ref``.
    """
    gwf = sim.get_model("sv")
    dis = gwf.dis
    nrow, ncol = dis.nrow.array, dis.ncol.array
    delr, delc = dis.delr.array, dis.delc.array
    native_nlay = dis.nlay.array
    top = dis.top.array.copy()
    botm = dis.botm.array.copy()
    idomain = dis.idomain.array.copy()
    k = gwf.npf.k.array.copy()
    k33 = gwf.npf.k33.array.copy()
    sy = gwf.sto.sy.array.copy()
    ss = gwf.sto.ss.array.copy()
    strt = gwf.ic.strt.array.copy()

    n_ref = max(1, int(np.ceil(refine_depth / target_dz)))
    refine_base = np.maximum(top - refine_depth, botm[0] + 0.01)

    # new cell-face elevations: land surface, n_ref refined faces, the native
    # layer-1 bottom (a transition cell), then the unchanged deeper layers
    faces = [top]
    for s in range(1, n_ref + 1):
        faces.append(top - (top - refine_base) * s / n_ref)
    faces.append(botm[0])
    faces.extend(botm[1:])
    new_botm = np.array(faces[1:])
    new_nlay = n_ref + native_nlay

    def stack(arr):
        """Copy the native layer 1 into each of the n_ref + 1 top cells."""
        return np.concatenate([np.repeat(arr[:1], n_ref + 1, axis=0), arr[1:]], axis=0)

    sub_tops = np.array(faces[: n_ref + 1])
    sub_bots = np.array(faces[1 : n_ref + 2])

    def sublayer_for(i, j, elevation):
        """Top-stack sublayer whose interval brackets ``elevation``."""
        for s in range(n_ref + 1):
            if sub_bots[s][i, j] < elevation <= sub_tops[s][i, j]:
                return s
        return 0 if elevation > sub_tops[0][i, j] else n_ref

    def deeper(layer):
        return layer if layer == 0 else layer + n_ref

    gwf.remove_package("DIS")
    flopy.mf6.ModflowGwfdis(
        gwf,
        nlay=new_nlay,
        nrow=nrow,
        ncol=ncol,
        delr=delr,
        delc=delc,
        top=top,
        botm=new_botm,
        idomain=stack(idomain).astype(int),
    )
    gwf.ic.strt.set_data(stack(strt))
    gwf.npf.k.set_data(stack(k))
    gwf.npf.k33.set_data(stack(k33))
    gwf.sto.ss.set_data(stack(ss))
    gwf.sto.sy.set_data(stack(sy))

    # recharge stays on the top cell, so only the wells and the head-dependent
    # boundaries need new layers
    for name in ("PWELL", "PREDICTION"):
        pkg = gwf.get_package(name)
        pkg.stress_period_data.set_data(
            {
                per: [[(deeper(c[0][0]), c[0][1], c[0][2]), *list(c)[1:]] for c in rows]
                for per, rows in pkg.stress_period_data.get_data().items()
            }
        )

    _rebuild_boundaries(
        gwf,
        riv_layer=lambda i, j, stage: sublayer_for(i, j, stage),
        ghb_layer=lambda layer, i, j, head: (
            sublayer_for(i, j, head) if layer == 0 else deeper(layer)
        ),
    )
    return n_ref


def read_water_tables(ws, vsf, times=None):
    """Water table at the end of each stress period, as ``(times, array)``.

    A model without VSF has the water table in the layer-1 head. A VSF model
    finds it with ``water_table`` from the head and pressure-head files. ``times``
    selects the output times; by default every time in the head file is used, so
    pass the end of each stress period to skip the sub-steps of a VSF run.
    """
    ws = pl.Path(ws)
    heads = flopy.utils.HeadFile(str(ws / "sv.hds"))
    times = heads.get_times() if times is None else times
    if vsf:
        pheads = flopy.utils.HeadFile(str(ws / "sv.phd"))
        tables = [
            water_table(heads.get_data(totim=t), pheads.get_data(totim=t))
            for t in times
        ]
    else:
        tables = [np.ma.masked_greater(heads.get_data(totim=t)[0], 1e29) for t in times]
    return np.array(times), np.ma.array(tables)


def aquifer_budget(ws, gwf):
    """Water budget of the aquifer outside the lake, at every time step.

    Runs ZONEBUDGET (zbud6) on the budget file in ``ws`` with the lake cells as a
    zone of their own. Returns a DataFrame indexed by time (days) with the stress
    period ``kper`` and the inflow and outflow rates (m3/d) of each term in
    ``BUDGET_TERMS`` as ``<term>_IN`` and ``<term>_OUT``; ``LAKE`` is the flow
    between the aquifer and the lake cells.
    """
    zones = np.where(lake_cells(gwf), 2, 1)
    zb = gwf.output.zonebudget(zones)
    zb.change_model_ws(str(ws))
    zb.write_input()
    success, _ = zb.run_model(silent=True)
    assert success, "ZONEBUDGET did not run"
    table = zb.get_dataframes(net=False, pivot=True, start_datetime=None)
    table = table[table["zone"] == 1].set_index("totim").sort_index()
    budget = table[["kper"]].copy()
    for term, name in BUDGET_TERMS.items():
        if term == "LAKE":
            budget["LAKE_IN"], budget["LAKE_OUT"] = (
                table["FROM_ZONE_2"],
                table["TO_ZONE_2"],
            )
        else:
            for side in ("IN", "OUT"):
                column = f"{name}_{side}"
                budget[f"{term}_{side}"] = table[column] if column in table else 0.0
    return budget
