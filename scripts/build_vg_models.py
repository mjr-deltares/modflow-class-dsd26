#!/usr/bin/env python
"""Build the coastal synthetic-valley models on a Voronoi grid.

Each model is the structured model of the same kind moved onto the Voronoi
cells: arrays and boundaries come from the DIS cell holding each cell center,
the hydraulic conductivity and clay from the truth dataset in
examples/data/synthetic-valley/data. Layer 3 is active only where the clay is.
Run inside the pixi environment, e.g.

    python scripts/build_vg_models.py --grid <dir with sv.disv>
"""

import argparse
import pathlib as pl
import shutil

import flopy
import numpy as np
import pandas as pd
import xarray as xr
from flopy.utils.gridintersect import GridIntersect
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import distance_transform_edt
from shapely.geometry import LineString

DATA_ROOT = pl.Path(__file__).resolve().parents[1] / "examples/data/synthetic-valley"
TRUTH = DATA_ROOT / "data/synthetic_valley_truth.nc"
WELL_INFO = DATA_ROOT / "data/obs_well_info.csv"
KINDS = ("base", "advanced")
SEAWATER_CONCENTRATION = 35.0
# m, a reach shorter than this, where the stream clips a cell corner, is added
# to the reach below it
MIN_REACH_LENGTH = 5.0


class VoronoiMap:
    """A Voronoi grid and the structured cell holding each of its cell centers."""

    def __init__(self, disv, dis):
        self.vertices = disv.vertices.array
        self.cell2d = disv.cell2d.array
        self.ncpl = disv.ncpl.data
        self.xc = np.array([r[1] for r in self.cell2d])
        self.yc = np.array([r[2] for r in self.cell2d])
        self.vxy = {int(v[0]): (float(v[1]), float(v[2])) for v in self.vertices}
        self.cverts = [[int(r[4 + i]) for i in range(int(r[3]))] for r in self.cell2d]

        self.nrow, self.ncol = dis.nrow.data, dis.ncol.data
        self.delr = float(np.atleast_1d(dis.delr.array)[0])
        self.delc = float(np.atleast_1d(dis.delc.array)[0])
        self.ylen = self.nrow * self.delc
        rc = np.array(
            [self.dis_rowcol(x, y) for x, y in zip(self.xc, self.yc, strict=True)]
        )
        self.ri, self.ci = rc[:, 0], rc[:, 1]

        # vertex pairs, and the cells on each side of them
        self.edges = {}
        for icpl, iv in enumerate(self.cverts):
            for n in range(len(iv)):
                key = tuple(sorted((iv[n - 1], iv[n])))
                self.edges.setdefault(key, []).append(icpl)

    def dis_rowcol(self, x, y):
        """(row, col) of the structured cell holding a point."""
        i = min(max(int((self.ylen - y) // self.delc), 0), self.nrow - 1)
        j = min(max(int(x // self.delr), 0), self.ncol - 1)
        return i, j

    def dis_center(self, i, j):
        return (j + 0.5) * self.delr, self.ylen - (i + 0.5) * self.delc

    def cell(self, x, y):
        """Voronoi cell holding a point."""
        return int(np.argmin((self.xc - x) ** 2 + (self.yc - y) ** 2))

    def cell_at_dis(self, i, j):
        return self.cell(*self.dis_center(i, j))

    def layers(self, arr):
        """A structured (nlay, nrow, ncol) array on the Voronoi cells."""
        return np.array([arr[k][self.ri, self.ci] for k in range(arr.shape[0])])

    def edge_geometry(self, key, icpl):
        """(length, distance from the cell center to the edge)."""
        (x0, y0), (x1, y1) = self.vxy[key[0]], self.vxy[key[1]]
        length = np.hypot(x1 - x0, y1 - y0)
        dist = (
            abs((x1 - x0) * (y0 - self.yc[icpl]) - (x0 - self.xc[icpl]) * (y1 - y0))
            / length
        )
        return length, dist


def truth_k(vmap, truth, nlay):
    """Truth K interpolated in log space between the structured cell centers."""
    tx = truth["x"].values
    ty = truth["y"].values[::-1]
    pts = np.column_stack(
        [np.clip(vmap.yc, ty[0], ty[-1]), np.clip(vmap.xc, tx[0], tx[-1])]
    )
    k11 = np.empty((nlay, vmap.ncpl))
    for k in range(nlay):
        kt = truth[f"k1_layer{k + 1}"].values[::-1]
        # K is undefined under the lake, so those cells take their nearest value
        missing = np.isnan(kt)
        if missing.any():
            _, (ii, jj) = distance_transform_edt(missing, return_indices=True)
            kt = kt[ii, jj]
        interp = RegularGridInterpolator((ty, tx), np.log10(kt))
        k11[k] = 10.0 ** interp(pts)
    return k11


def stream_reaches(vmap, gwf, first_cell, ncells):
    """(top y, bottom y, cell, length) of the reaches, upstream first.

    The structured stream runs down the center of one column from the top of
    ``first_cell`` for ``ncells`` cells.
    """
    _, i0, j0 = first_cell
    x = (j0 + 0.5) * vmap.delr
    y_up = vmap.ylen - i0 * vmap.delc
    y_dn = vmap.ylen - (i0 + ncells) * vmap.delc
    res = GridIntersect(gwf.modelgrid).intersect(LineString([(x, y_up), (x, y_dn)]))
    reaches = []
    for cid, geom, length in zip(
        res["cellids"], res["ixshapes"], res["lengths"], strict=True
    ):
        if length > 1e-6:
            ys = [p[1] for p in geom.coords]
            reaches.append((max(ys), min(ys), int(cid), float(length)))
    reaches.sort(reverse=True)
    merged, carry = [], 0.0
    for yt, yb, icpl, length in reaches:
        if length < MIN_REACH_LENGTH:
            carry += length
            continue
        merged.append((yt, yb, icpl, length + carry))
        carry = 0.0
    return merged


def linear_in_y(vmap, cellids, values):
    """Coefficients of a value that is linear in y through structured cell centers."""
    y = np.array([vmap.ylen - (c[1] + 0.5) * vmap.delc for c in cellids])
    return np.polyfit(y, values, 1)


def coastal_ghb(vmap, top, botm, idomain, k11, skip):
    """GHB stress-period data at sea level along the southern edge.

    The conductance per unit length of coastline is the structured models'.
    """
    flow_length = 0.5 * vmap.delc
    spd = {}
    for k in range(botm.shape[0]):
        for key, cells in vmap.edges.items():
            (x0, y0), (x1, y1) = vmap.vxy[key[0]], vmap.vxy[key[1]]
            if len(cells) != 1 or abs(y0) > 1e-6 or abs(y1) > 1e-6:
                continue
            icpl = cells[0]
            if icpl == skip or idomain[k, icpl] <= 0:
                continue
            cell_top = top[icpl] if k == 0 else botm[k - 1, icpl]
            cell_bot = botm[k, icpl]
            cond = k11[k, icpl] * abs(x1 - x0) * (cell_top - cell_bot) / flow_length
            if (k, icpl) in spd:
                spd[(k, icpl)][2] += cond
                continue
            elevation = 0.5 * (min(cell_top, 0.0) + cell_bot)
            spd[(k, icpl)] = [
                (k, icpl),
                0.0,
                cond,
                elevation,
                SEAWATER_CONCENTRATION,
                "coast",
            ]
    return [tuple(v) for v in spd.values()]


def head_obs(vmap, obs, wells):
    """Head observations: wells at their surveyed locations, the rest at the
    structured cell centers."""
    continuous = {}
    for fname, rec in obs.continuous.get_data().items():
        if fname in ("sv.gwf.aq.csv", "sv.gwf.wt.csv"):
            continuous[fname] = [
                (name, "head", (cid[0], vmap.cell(x, y)))
                for name, cid, x, y in zip(
                    rec["obsname"], rec["id"], wells["x"], wells["y"], strict=True
                )
            ]
        else:
            continuous[fname] = [
                (name, otype, (cid[0], vmap.cell_at_dis(cid[1], cid[2])))
                for name, otype, cid in zip(
                    rec["obsname"], rec["obstype"], rec["id"], strict=True
                )
            ]
    return continuous


def layered(arr):
    """Per-layer values, with a constant for each uniform layer."""
    return [a.flat[0].item() if np.all(a == a.flat[0]) else a for a in arr]


def period_values(data, nper, fields):
    """{field: value in each period} for period data that is uniform over its
    rows, carried forward through periods with no data."""
    values = {f: [] for f in fields}
    current = None
    for kper in range(nper):
        if kper in data:
            d = data[kper]
            current = {}
            for f in fields:
                u = np.unique(d[f])
                if u.size != 1:
                    raise ValueError(f"{f} varies between cells in period {kper + 1}")
                current[f] = u[0].item()
        for f in fields:
            values[f].append(current[f])
    return values


def stepwise_ts(package, filename, sim_s, series):
    """Attach a stepwise time series holding {name: value in each period}."""
    perlen = sim_s.tdis.perioddata.array["perlen"]
    times = np.concatenate([[0.0], np.cumsum(perlen)])
    names = list(series)
    rows = []
    for n, t in enumerate(times):
        kper = min(n, len(perlen) - 1)
        rows.append((float(t), *(series[name][kper] for name in names)))
    package.ts.initialize(
        filename=filename,
        timeseries=rows,
        time_series_namerecord=names,
        interpolation_methodrecord=["stepwise"] * len(names),
    )


def wel_spd(vmap, wel):
    """WEL stress-period data with each well at its structured cell center."""
    spd = {}
    for kper, d in wel.stress_period_data.get_data().items():
        rows = []
        for r in d:
            c = r["cellid"]
            row = [(c[0], vmap.cell_at_dis(c[1], c[2])), r["q"]]
            if "boundname" in d.dtype.names:
                row.append(r["boundname"])
            rows.append(tuple(row))
        spd[kper] = rows
    return spd


def build(kind, grid_ws, dest):
    src = DATA_ROOT / f"synthetic-valley-coastal-{kind}-annual"
    sim_s = flopy.mf6.MFSimulation.load(sim_ws=src, verbosity_level=0)
    s = sim_s.get_model()
    dis = s.dis
    nlay = dis.nlay.data
    disv_g = (
        flopy.mf6.MFSimulation.load(
            sim_ws=grid_ws, verbosity_level=0, load_only=["disv"]
        )
        .get_model()
        .disv
    )
    vmap = VoronoiMap(disv_g, dis)
    truth = xr.open_dataset(TRUTH)
    wells = pd.read_csv(WELL_INFO)

    top = dis.top.array[vmap.ri, vmap.ci]
    botm = vmap.layers(dis.botm.array)
    idomain = vmap.layers(dis.idomain.array)
    # layer 3 is the clay; elsewhere its cells pass flow between layers 2 and 4
    clay = truth["clay_location"].values[vmap.ri, vmap.ci] == 1
    idomain[2, ~clay] = -1

    k11 = truth_k(vmap, truth, nlay)
    k11[2, clay] = truth["clay_kv"].values[vmap.ri, vmap.ci][clay]
    # an active lake in layer 1 keeps the structured model's high K
    lake = truth["lake_location"].values[vmap.ri, vmap.ci] == 1
    k_s = vmap.layers(s.npf.k.array)
    k11[0, lake] = k_s[0, lake]

    sim = flopy.mf6.MFSimulation(sim_name="sv", sim_ws=dest, memory_print_option=None)
    # the default precision rounds the period data the structured models carry
    sim.simulation_data.float_precision = 12
    sim.simulation_data.float_characters = 20
    flopy.mf6.ModflowTdis(
        sim,
        time_units="days",
        nper=sim_s.tdis.nper.data,
        perioddata=sim_s.tdis.perioddata.array.tolist(),
    )
    flopy.mf6.ModflowIms(sim)
    gwf = flopy.mf6.ModflowGwf(
        sim, modelname="sv", save_flows=True, newtonoptions="under_relaxation"
    )
    flopy.mf6.ModflowGwfdisv(
        gwf,
        length_units="meters",
        nlay=nlay,
        ncpl=vmap.ncpl,
        nvert=len(vmap.vertices),
        top=top,
        botm=layered(botm),
        idomain=layered(idomain),
        vertices=vmap.vertices.tolist(),
        cell2d=vmap.cell2d.tolist(),
    )
    flopy.mf6.ModflowGwfic(gwf, strt=vmap.layers(s.ic.strt.array))
    flopy.mf6.ModflowGwfnpf(
        gwf,
        save_specific_discharge=True,
        k33overk=True,
        icelltype=layered(vmap.layers(s.npf.icelltype.array)),
        k=k11,
        k33=layered(vmap.layers(s.npf.k33.array)),
    )
    flopy.mf6.ModflowGwfsto(
        gwf,
        iconvert=layered(vmap.layers(s.sto.iconvert.array)),
        ss=layered(vmap.layers(s.sto.ss.array)),
        sy=layered(vmap.layers(s.sto.sy.array)),
        steady_state={0: True},
        transient={1: True},
    )

    if kind == "advanced":
        outlet = build_advanced_boundaries(vmap, sim_s, gwf, top, idomain)
    else:
        outlet = build_base_boundaries(vmap, sim_s, gwf)

    flopy.mf6.ModflowGwfwel(
        gwf,
        pname="prediction",
        filename="sv.prediction.well",
        stress_period_data=wel_spd(vmap, s.get_package("prediction")),
    )
    ghb = coastal_ghb(vmap, top, botm, idomain, k11, outlet)
    flopy.mf6.ModflowGwfghb(
        gwf,
        pname="ghb-1",
        auxiliary=["ELEVATION", "CONCENTRATION"],
        boundnames=True,
        print_flows=True,
        stress_period_data={0: ghb},
        observations={
            "sv.ghb.obs.csv": [("coast-swgw", "ghb", "coast")],
            "filename": "sv.ghb.obs",
        },
    )
    # the model's head observations, not those of a boundary package
    obs_s = [
        p
        for p in s.packagelist
        if p.package_type == "obs" and "sv.gwf.aq.csv" in p.continuous.get_data()
    ][0]
    flopy.mf6.ModflowUtlobs(
        gwf,
        pname=obs_s.package_name,
        filename=pl.Path(obs_s.filename).name,
        print_input=True,
        continuous=head_obs(vmap, obs_s, wells),
    )
    flopy.mf6.ModflowGwfoc(gwf)

    if dest.exists():
        shutil.rmtree(dest)
    sim.write_simulation(silent=True)
    # timing, solver, and output control are the structured model's
    for name in ("sv.tdis", "sv.ims", "sv.oc"):
        shutil.copy(src / name, dest / name)
    print(f"{dest.name}: {vmap.ncpl} cells per layer, {len(ghb)} GHB cells")


def build_advanced_boundaries(vmap, sim_s, gwf, top, idomain):
    """SFR, LAK, UZF, MVR, and MAW; returns the stream outlet cell."""
    s = sim_s.get_model()
    sfr_s = s.sfr.packagedata.array
    reaches = stream_reaches(vmap, gwf, sfr_s["cellid"][0], len(sfr_s))
    rtp_fit = linear_in_y(vmap, sfr_s["cellid"], sfr_s["rtp"])
    r0 = sfr_s[0]
    nreach = len(reaches)
    packagedata = []
    for n, (yt, yb, icpl, length) in enumerate(reaches):
        packagedata.append(
            (
                n,
                (0, icpl),
                length,
                r0["rwid"],
                r0["rgrd"],
                float(np.polyval(rtp_fit, 0.5 * (yt + yb))),
                r0["rbth"],
                r0["rhk"],
                r0["man"],
                1 if n in (0, nreach - 1) else 2,
                1.0,
                0,
                "riv",
            )
        )
    connectiondata = (
        [[0, -1]]
        + [[n, n - 1, -(n + 1)] for n in range(1, nreach - 1)]
        + [[nreach - 1, nreach - 2]]
    )
    # the downstream-flow observation goes at the bottom of the same structured
    # reach (the observation file is 1-based)
    sfr_obs = s.sfr.obs.continuous.get_data()["sv.sfr.obs.csv"]
    iobs = int(sfr_obs["id"][1]) - 1
    y_obs = vmap.ylen - (sfr_s["cellid"][iobs][1] + 1) * vmap.delc
    iobs = int(np.argmin([abs(r[1] - y_obs) for r in reaches]))
    flopy.mf6.ModflowGwfsfr(
        gwf,
        pname="sfr-1",
        boundnames=True,
        save_flows=True,
        mover=True,
        unit_conversion=86400.0,
        nreaches=nreach,
        packagedata=packagedata,
        connectiondata=connectiondata,
        observations={
            "sv.sfr.obs.csv": [
                ("riv-swgw", "sfr", "riv"),
                ("riv-flow", "downstream-flow", (iobs,)),
            ],
            "filename": "sv.sfr.obs",
        },
    )

    # the lake fills the inactive layer 1 cells, connected horizontally to the
    # active cells beside them and vertically to layer 2
    lak_cd_s = s.lak.connectiondata.array
    bedleak = lak_cd_s["bedleak"][0]
    belev = float(lak_cd_s["belev"][lak_cd_s["claktype"] == "horizontal"][0])
    lake_cells = np.where(idomain[0] <= 0)[0]
    lake_set = set(lake_cells.tolist())
    connections = []
    for icpl in lake_cells:
        iv = vmap.cverts[icpl]
        for n in range(len(iv)):
            key = tuple(sorted((iv[n - 1], iv[n])))
            for nb in vmap.edges[key]:
                if nb in lake_set or idomain[0, nb] <= 0:
                    continue
                width, dist = vmap.edge_geometry(key, nb)
                connections.append(
                    ((0, nb), "horizontal", bedleak, belev, top[nb], dist, width)
                )
        connections.append(((1, icpl), "vertical", bedleak, 0.0, 0.0, 0.0, 0.0))
    lak_s = s.lak.packagedata.array[0]
    flopy.mf6.ModflowGwflak(
        gwf,
        pname="lak-1",
        boundnames=True,
        print_input=True,
        print_stage=True,
        stage_filerecord="sv.lak.hds",
        mover=True,
        nlakes=1,
        packagedata=[(0, lak_s["strt"], len(connections), lak_s["boundname"])],
        connectiondata=[(0, n, *c) for n, c in enumerate(connections)],
        perioddata=dict(s.lak.perioddata.get_data().items()),
        observations={
            "sv.lake.obs.csv": [
                ("lake-stage", "stage", lak_s["boundname"]),
                ("lake-swgw", "lak", lak_s["boundname"]),
            ],
            "filename": "sv.lak.obs",
        },
    )

    # UZF on every active layer 1 cell, with the parameters and mover receiver
    # of the structured cell under it
    uz_s = s.uzf.packagedata.array
    uz_id = {(int(c[1]), int(c[2])): n for n, c in enumerate(uz_s["cellid"])}
    receiver = {
        int(r["id1"]): (r["pname2"], int(r["id2"]), r["mvrtype"], r["value"])
        for r in s.mvr.perioddata.get_data(0)
    }
    uz_src = [
        uz_id[(vmap.ri[icpl], vmap.ci[icpl])]
        for icpl in range(vmap.ncpl)
        if idomain[0, icpl] > 0
    ]
    uz_cells = [icpl for icpl in range(vmap.ncpl) if idomain[0, icpl] > 0]
    packagedata = []
    for n, (icpl, m) in enumerate(zip(uz_cells, uz_src, strict=True)):
        r = uz_s[m]
        # an ivertcon of -1 is written as 0, no UZF cell below
        packagedata.append(
            (
                n,
                (0, icpl),
                r["landflag"],
                -1,
                r["surfdep"],
                r["vks"],
                r["thtr"],
                r["thts"],
                r["thti"],
                r["eps"],
            )
        )
    # every cell gets the same rates, so the period data is written once and the
    # rates that change come from a time series
    fields = ("finf", "pet", "extdp", "extwc", "ha", "hroot", "rootact")
    values = period_values(s.uzf.perioddata.get_data(), sim_s.tdis.nper.data, fields)
    series = {}
    row = []
    for f in fields:
        if len(set(values[f])) > 1:
            series[f"uzf_{f}"] = values[f]
            row.append(f"uzf_{f}")
        else:
            row.append(values[f][0])
    perioddata = {0: [(n, *row) for n in range(len(uz_src))]}
    uzf = flopy.mf6.ModflowGwfuzf(
        gwf,
        pname="uzf-1",
        mover=True,
        simulate_et=True,
        nuzfcells=len(packagedata),
        ntrailwaves=s.uzf.ntrailwaves.data,
        nwavesets=s.uzf.nwavesets.data,
        packagedata=packagedata,
        perioddata=perioddata,
    )
    stepwise_ts(uzf, "sv.uzf.ts", sim_s, series)
    mvr = [("uzf-1", n, *receiver[m]) for n, m in enumerate(uz_src)]
    flopy.mf6.ModflowGwfmvr(
        gwf,
        maxmvr=len(mvr),
        maxpackages=3,
        packages=[["uzf-1"], ["lak-1"], ["sfr-1"]],
        perioddata={0: mvr},
    )

    maw_cd = []
    for r in s.maw.connectiondata.array:
        k, i, j = r["cellid"]
        maw_cd.append(
            (
                r["ifno"],
                r["icon"],
                (k, vmap.cell_at_dis(i, j)),
                r["scrn_top"],
                r["scrn_bot"],
                r["hk_skin"],
                r["radius_skin"],
            )
        )
    flopy.mf6.ModflowGwfmaw(
        gwf,
        pname="pwell",
        boundnames=True,
        nmawwells=s.maw.nmawwells.data,
        packagedata=s.maw.packagedata.array.tolist(),
        connectiondata=maw_cd,
        perioddata=dict(s.maw.perioddata.get_data().items()),
    )
    return reaches[-1][2]


def build_base_boundaries(vmap, sim_s, gwf):
    """RCH, EVT, RIV, and the pumping WEL; returns the stream outlet cell."""
    s = sim_s.get_model()
    nper = sim_s.tdis.nper.data

    # recharge is uniform over the land and over the lake, so each cell takes
    # the time series of its zone
    rch_data = s.get_package("rch").stress_period_data.get_data()
    zone = {
        (int(c[1]), int(c[2])): b
        for c, b in zip(rch_data[0]["cellid"], rch_data[0]["boundname"], strict=True)
    }
    series = {}
    for b in sorted(set(zone.values())):
        by_zone = {kper: d[d["boundname"] == b] for kper, d in rch_data.items()}
        series[f"rch_{b}"] = period_values(by_zone, nper, ("recharge",))["recharge"]
    rch_spd = []
    for icpl in range(vmap.ncpl):
        b = zone[(vmap.ri[icpl], vmap.ci[icpl])]
        rch_spd.append(((0, icpl), f"rch_{b}", b))
    rch = flopy.mf6.ModflowGwfrch(
        gwf,
        pname="rch_0",
        boundnames=True,
        maxbound=vmap.ncpl,
        stress_period_data={0: rch_spd},
    )
    stepwise_ts(rch, "sv.rch.ts", sim_s, series)

    # lake evaporation, on the cells over the structured lake cells
    evt_data = s.get_package("evt").stress_period_data.get_data()
    values = period_values(evt_data, nper, ("surface", "rate", "depth"))
    evt_cells = {(int(c[1]), int(c[2])) for c in evt_data[0]["cellid"]}
    evt_spd = [
        ((0, icpl), values["surface"][0], "evt_rate", values["depth"][0])
        for icpl in range(vmap.ncpl)
        if (vmap.ri[icpl], vmap.ci[icpl]) in evt_cells
    ]
    evt = flopy.mf6.ModflowGwfevt(
        gwf,
        pname="evt_0",
        maxbound=len(evt_spd),
        stress_period_data={0: evt_spd},
    )
    stepwise_ts(evt, "sv.evt.ts", sim_s, {"evt_rate": values["rate"]})

    # stage, bottom, and conductance per unit length of the structured reaches
    riv_s = s.riv.stress_period_data.get_data(0)
    reaches = stream_reaches(vmap, gwf, riv_s["cellid"][0], len(riv_s))
    stage_fit = linear_in_y(vmap, riv_s["cellid"], riv_s["stage"])
    rbot_fit = linear_in_y(vmap, riv_s["cellid"], riv_s["rbot"])
    cond_per_length = float(riv_s["cond"][0]) / vmap.delc
    riv_spd = []
    for yt, yb, icpl, length in reaches:
        y = 0.5 * (yt + yb)
        riv_spd.append(
            (
                (0, icpl),
                float(np.polyval(stage_fit, y)),
                cond_per_length * length,
                float(np.polyval(rbot_fit, y)),
                "riv",
            )
        )
    flopy.mf6.ModflowGwfriv(
        gwf,
        pname="riv-1",
        boundnames=True,
        print_flows=True,
        stress_period_data={0: riv_spd},
        observations={
            "sv.riv.obs.csv": [("riv-swgw", "riv", "riv")],
            "filename": "sv.riv.obs",
        },
    )

    flopy.mf6.ModflowGwfwel(
        gwf,
        pname="pwell",
        filename="sv.pwell.wel",
        boundnames=True,
        stress_period_data=wel_spd(vmap, s.get_package("pwell")),
    )
    return reaches[-1][2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--grid",
        type=pl.Path,
        default=DATA_ROOT / "synthetic-valley-coastal-vg-advanced-annual",
        help="model directory whose sv.disv holds the Voronoi grid",
    )
    parser.add_argument("--kind", choices=KINDS, nargs="+", default=list(KINDS))
    parser.add_argument(
        "--dest",
        type=pl.Path,
        default=DATA_ROOT,
        help="directory to write the models in (default: the repository data)",
    )
    args = parser.parse_args(argv)
    for kind in args.kind:
        build(kind, args.grid, args.dest / f"synthetic-valley-coastal-vg-{kind}-annual")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
