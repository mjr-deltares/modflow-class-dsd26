#!/usr/bin/env python
"""Add the land surface, lake, and seepage drains to the structured synthetic-valley models.

The top of each cell is the mean land surface elevation over the cell, from
the 15.24 m raster described in scripts/sv_surface.py, and layer 1 is
convertible, so its saturated thickness follows the water table.

In the base model the lake is a set of layer 1 cells with a very high
hydraulic conductivity, whose top is the lake surface at its highest level;
evapotranspiration and recharge at the lake rate are applied to them. The
recharge on the land is the advanced model's infiltration minus its potential
evapotranspiration, scaled (see BASE_RECHARGE_SCALE).

In the advanced model the lake sits on top of the aquifer and leaks through its
bed to the layer 1 cell beneath it, or to layer 2 where the lake bed is at the
bottom of layer 1 and the layer 1 cell passes water straight through. A table
gives the lake volume and area at each lake level. There are no unsaturated
zone (UZF) cells under the lake, and the runoff of each UZF cell is sent to
where it drains over the land surface: the lake or a stream reach.

In both models, groundwater that reaches the land surface away from the lake
and the stream is removed by seepage drains; in the advanced model that water
goes where the runoff of the cell goes. Both models start from their own
steady-state heads. The models are changed in place. Run inside the pixi
environment, e.g.

    python scripts/update_structured_models.py
"""

import argparse
import pathlib as pl
import shutil

import flopy
import numpy as np
from scipy.ndimage import distance_transform_edt
from sv_surface import (
    BASE_RECHARGE_SCALE,
    COAST,
    DATA_ROOT,
    LAKE,
    LAKE_EXTENT,
    LAKE_FLOOR,
    LAKE_K,
    LAKE_K33,
    Surface,
    drain_package,
    drain_rows,
    lake_package,
    mover_records,
    start_from_steady_state,
)

KINDS = ("base", "advanced")
CHANGED = ("dis", "npf", "ic", "rch", "evt", "lak", "laktab", "uzf", "mvr", "drn")
# m, the head-change criterion of the advanced models' linear solver; it is
# tight enough that the runoff and seepage the Water Mover sends to a short
# stream reach stop changing from one solver iteration to the next, which lets
# the steady-state solution converge
ADVANCED_INNER_DVCLOSE = 3.048e-9
# the line that adds the drains to the model name file, which is otherwise left
# as it is
DRN_ENTRY = "  drn6  sv.drn  drn-1"


def aquifer_k(k, nrow, ncol):
    """Layer 1 hydraulic conductivity of the aquifer.

    The high values of the base model's lake cells are replaced by the value of
    the nearest aquifer cell.
    """
    lake = (k >= 0.1 * LAKE_K).reshape(nrow, ncol)
    _, (ii, jj) = distance_transform_edt(lake, return_indices=True)
    return k.reshape(nrow, ncol)[ii, jj].ravel()


def uniform_rows(data, fields):
    """The value of each field in each stress period, for input that is the same
    in every cell; returns {period: {field: value}}.
    """
    values = {}
    for kper, d in data.items():
        values[kper] = {}
        for f in fields:
            u = np.unique(d[f])
            if u.size != 1:
                raise ValueError(f"{f} varies between cells in period {kper + 1}")
            values[kper][f] = u[0].item()
    return values


def update(kind, ws, surface):
    sim = flopy.mf6.MFSimulation.load(sim_ws=ws, verbosity_level=0, write_headers=False)
    sim.simulation_data.float_precision = 12
    sim.simulation_data.float_characters = 20
    gwf = sim.get_model()
    dis = gwf.dis
    nlay, nrow, ncol = dis.nlay.data, dis.nrow.data, dis.ncol.data
    members = surface.members(gwf.modelgrid)
    top, lake, bed = surface.cells(members)

    k = dis_layers(gwf.npf.k.array)
    k33 = dis_layers(gwf.npf.k33.array)
    k33[0] = float(np.median(k33[0][k[0] < 0.1 * LAKE_K]))
    k[0] = aquifer_k(k[0], nrow, ncol)
    idomain = dis_layers(dis.idomain.array)
    icelltype = np.zeros((nlay, nrow * ncol), dtype=int)
    icelltype[0] = 1

    if kind == "base":
        top[lake] = LAKE_EXTENT
        k[0, lake], k33[0, lake] = LAKE_K, LAKE_K33
        # the lake cells are treated as always saturated; with their very high
        # hydraulic conductivity, letting their saturated thickness follow the
        # head makes the steady-state solution fail to converge
        icelltype[0, lake] = 0
        note = base_boundaries(gwf, lake, ncol)
        stream = [
            i * ncol + j for _, i, j in gwf.riv.stress_period_data.get_data(0)["cellid"]
        ]
        uzf_records, outlet = [], None
    else:
        # where the lake bed is at the bottom of layer 1, layer 1 has no
        # thickness and passes water straight through to layer 2
        to_layer2 = lake & (bed - LAKE_FLOOR <= 1.0e-6)
        to_layer1 = lake & ~to_layer2
        top[to_layer1] = bed[to_layer1]
        top[to_layer2] = LAKE_FLOOR
        idomain[0] = 1
        idomain[0, to_layer2] = -1
        note, uzf_records, outlet = advanced_boundaries(
            gwf, surface, members, lake, to_layer2, ncol
        )
        stream = [i * ncol + j for _, i, j in gwf.sfr.packagedata.array["cellid"]]

    # seepage drains on the land cells, away from the lake and the stream
    land = ~lake
    land[stream] = False
    cells = np.nonzero(land)[0]
    area = gwf.modelgrid.area
    rows = drain_rows(
        [(0, n // ncol, n % ncol) for n in cells],
        top[cells],
        dis_layers(dis.botm.array)[0][cells],
        (k[0] * k33[0])[cells],
        area[cells],
    )
    if gwf.get_package("drn-1") is not None:
        gwf.remove_package("drn-1")
    drain_package(gwf, rows, mover=kind == "advanced")
    nam = ws / "sv.nam"
    text = nam.read_text()
    if DRN_ENTRY not in text:
        nam.write_text(text.replace("END packages", f"{DRN_ENTRY}\nEND packages", 1))
    note += f"; {len(rows)} drains"
    if kind == "advanced":
        drn_records = [
            ("drn-1", *r) for r in mover_records(cells, outlet, "FACTOR", 1.0)
        ]
        gwf.mvr.packages = [["uzf-1"], ["lak-1"], ["sfr-1"], ["drn-1"]]
        gwf.mvr.maxpackages = 4
        gwf.mvr.perioddata = {0: uzf_records + drn_records}
        gwf.mvr.maxmvr = len(uzf_records) + len(drn_records)
        note += f", {len(drn_records)} moved to the lake or the stream"

    shape = (nlay, nrow, ncol)
    dis.top = top.reshape(nrow, ncol)
    dis.idomain = idomain.reshape(shape)
    gwf.npf.k = k.reshape(shape)
    gwf.npf.k33 = k33.reshape(shape)
    gwf.npf.icelltype = icelltype.reshape(shape)
    # write only the input files that change, so the others are left as they are
    for package in gwf.packagelist:
        if package.package_type in CHANGED:
            package.write()
    if kind == "advanced":
        ims = sim.get_package("ims")
        ims.inner_dvclose = ADVANCED_INNER_DVCLOSE
        ims.write()
    note += "; " + start_from_steady_state(ws)
    print(f"{ws.name}: {lake.sum()} lake cells; {note}")


def dis_layers(arr):
    """A copy of a (layer, row, column) array with the cells of each layer in one row."""
    return arr.reshape(arr.shape[0], -1).copy()


def base_boundaries(gwf, lake, ncol):
    """Recharge on the lake and land cells and evaporation on the lake cells."""
    # the lake recharge is the rainfall; the land recharge is the advanced
    # model's infiltration minus its potential evapotranspiration, scaled
    uzf = (
        flopy.mf6.MFSimulation.load(
            sim_ws=DATA_ROOT / "synthetic-valley-coastal-advanced-annual",
            verbosity_level=0,
            load_only=["uzf"],
        )
        .get_model()
        .uzf
    )
    rates = uniform_rows(uzf.perioddata.get_data(), ("finf", "pet"))
    rch = gwf.get_package("rch")
    data = rch.stress_period_data.get_data()
    values = {
        kper: {
            "lake": d["recharge"][d["boundname"] == "lake"][0],
            "land": BASE_RECHARGE_SCALE * (rates[kper]["finf"] - rates[kper]["pet"]),
        }
        for kper, d in data.items()
    }
    spd = {}
    for kper, d in data.items():
        d = d.copy()
        for r in d:
            _, i, j = r["cellid"]
            zone = "lake" if lake[i * ncol + j] else "land"
            r["boundname"] = zone
            r["recharge"] = values[kper][zone]
        spd[kper] = d
    rch.stress_period_data = spd

    evt = gwf.get_package("evt")
    data = evt.stress_period_data.get_data()
    fields = data[0].dtype.names[1:]
    values = uniform_rows(data, fields)
    cells = [(0, n // ncol, n % ncol) for n in np.nonzero(lake)[0]]
    evt.stress_period_data = {
        kper: [(c, *(v[f] for f in fields)) for c in cells]
        for kper, v in values.items()
    }
    evt.maxbound = len(cells)
    return f"{len(cells)} EVT cells"


def advanced_boundaries(gwf, surface, members, lake, to_layer2, ncol):
    """Lake, unsaturated zone, and Water Mover input for the lake on the aquifer."""
    lak_s = gwf.lak
    bedleak = float(lak_s.connectiondata.array["bedleak"][0])
    pdata = lak_s.packagedata.array[0]
    perioddata = dict(lak_s.perioddata.get_data().items())
    gwf.remove_package("lak-1")
    nodes = np.nonzero(lake)[0]
    connections = [
        ((1 if to_layer2[n] else 0, n // ncol, n % ncol), bedleak) for n in nodes
    ]
    lake_package(
        gwf,
        connections,
        float(pdata["strt"]),
        pdata["boundname"],
        perioddata,
        surface.stage_table(),
    )
    strt = dis_layers(gwf.ic.strt.array)
    strt[0, lake] = pdata["strt"]
    gwf.ic.strt = strt.reshape(gwf.ic.strt.array.shape)

    # an unsaturated zone (UZF) cell on every land cell, with the properties of
    # the UZF cell that was there, or of the nearest one
    uzf = gwf.uzf
    uz_s = uzf.packagedata.array
    uz_node = np.array([i * ncol + j for _, i, j in uz_s["cellid"]])
    land = np.nonzero(~lake)[0]
    row, col = land // ncol, land % ncol
    nearest = [
        int(np.argmin((uz_node // ncol - i) ** 2 + (uz_node % ncol - j) ** 2))
        for i, j in zip(row, col, strict=True)
    ]
    packagedata = []
    for n, (node, m) in enumerate(zip(land, nearest, strict=True)):
        r = uz_s[m]
        # no UZF cell below this one (-1, written to the file as 0)
        packagedata.append(
            (
                n,
                (0, node // ncol, node % ncol),
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
    fields = ("finf", "pet", "extdp", "extwc", "ha", "hroot", "rootact")
    values = uniform_rows(uzf.perioddata.get_data(), fields)
    uzf.packagedata = packagedata
    uzf.nuzfcells = len(packagedata)
    uzf.perioddata = {
        kper: [(n, *(v[f] for f in fields)) for n in range(len(land))]
        for kper, v in values.items()
    }

    # send each cell's runoff to where it drains over the land surface
    reaches = {}
    for r in gwf.sfr.packagedata.array:
        _, i, j = r["cellid"]
        reaches[i * ncol + j] = int(r["ifno"])
    coast = [
        i * ncol + j
        for k, i, j in gwf.ghb.stress_period_data.get_data(0)["cellid"]
        if k == 0
    ]
    outlet = surface.runoff_outlets(members, lake, reaches, coast)
    first = gwf.mvr.perioddata.get_data(0)[0]
    records = mover_records(land, outlet, first["mvrtype"], float(first["value"]))
    to_lake = sum(r[1] == LAKE for r in records)
    to_coast = sum(outlet[n][0] == COAST for n in land)
    note = (
        f"{to_layer2.sum()} connected to layer 2; {len(land)} UZF cells; runoff "
        f"from {to_lake} to the lake, {len(records) - to_lake} to the stream, "
        f"{to_coast} to the coast"
    )
    return note, [("uzf-1", *r) for r in records], outlet


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--kind", choices=KINDS, nargs="+", default=list(KINDS))
    parser.add_argument(
        "--dest",
        type=pl.Path,
        default=None,
        help="directory to copy the models to and change there (default: in place)",
    )
    args = parser.parse_args(argv)
    surface = Surface()
    for kind in args.kind:
        ws = DATA_ROOT / f"synthetic-valley-coastal-{kind}-annual"
        if args.dest is not None:
            dest = args.dest / ws.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(ws, dest)
            ws = dest
        update(kind, ws, surface)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
