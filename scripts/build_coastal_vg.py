#!/usr/bin/env python
"""Build the coastal synthetic-valley Voronoi-grid model.

The model is synthetic-valley-vg from jdhughes-dev/mf6-training plus a
general-head boundary (GHB) at sea level on the cells along the southern edge,
like the coastal structured models. The cell holding the stream outlet is left
out so the stream keeps the only surface outflow there. Run inside the pixi
environment, e.g.

    pixi run build-coastal-vg --source <mf6-training>/examples/data/synthetic-valley/synthetic-valley-vg
"""

import argparse
import pathlib as pl
import shutil
import sys

import flopy
import numpy as np

DEST = (
    pl.Path(__file__).resolve().parents[1]
    / "examples/data/synthetic-valley/synthetic-valley-coastal-vg"
)
# kg/m3, the concentration BUY gets its density from, as in the structured models
SEAWATER_CONCENTRATION = 35.0
# m, the distance from the cell center to the coast in the structured models,
# half of their 500 ft rows, so the coast has the same conductance per unit
# length of coastline
FLOW_LENGTH = 0.5 * 500.0 * 0.3048


def southern_edge_cells(disv):
    """(cell2d index, face width) of the cells on the southern edge."""
    verts = {int(v[0]): (float(v[1]), float(v[2])) for v in disv.vertices.array}
    ymin = min(y for _, y in verts.values())
    cells = []
    for row in disv.cell2d.array:
        icpl, nvert = int(row[0]), int(row[3])
        iverts = [int(row[4 + i]) for i in range(nvert)]
        width = 0.0
        for i in range(nvert):
            (x0, y0), (x1, y1) = verts[iverts[i - 1]], verts[iverts[i]]
            if np.isclose(y0, ymin) and np.isclose(y1, ymin):
                width += abs(x1 - x0)
        if width > 0.0:
            cells.append((icpl, width))
    return cells


def stream_outlets(sfr):
    """cell2d indices of the SFR reaches with no downstream connection."""
    cellids = {int(r["ifno"]): r["cellid"] for r in sfr.packagedata.array}
    outlets = set()
    for row in sfr.connectiondata.array:
        connections = [c for c in list(row)[1:] if c is not None and not np.isnan(c)]
        if all(c >= 0 for c in connections):
            outlets.add(int(cellids[int(row[0])][1]))
    return outlets


def coastal_ghb_data(gwf, sea_level=0.0, cond_mult=1.0, flow_length=FLOW_LENGTH):
    """GHB stress-period data for a sea-level boundary along the southern edge."""
    disv = gwf.disv
    top = disv.top.array
    botm = disv.botm.array
    idomain = disv.idomain.array
    k11 = gwf.npf.k.array
    skip = stream_outlets(gwf.sfr)

    spd = []
    for k in range(disv.nlay.data):
        for icpl, width in southern_edge_cells(disv):
            if icpl in skip or idomain[k, icpl] <= 0:
                continue
            cell_top = top[icpl] if k == 0 else botm[k - 1, icpl]
            cell_bot = botm[k, icpl]
            thickness = cell_top - cell_bot
            cond = cond_mult * k11[k, icpl] * width * thickness / flow_length
            elevation = 0.5 * (min(cell_top, sea_level) + cell_bot)
            spd.append(
                (
                    (k, icpl),
                    sea_level,
                    cond,
                    elevation,
                    SEAWATER_CONCENTRATION,
                    "coast",
                )
            )
    return spd


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--source", required=True, type=pl.Path, help="synthetic-valley-vg model"
    )
    parser.add_argument(
        "--cond-mult",
        type=float,
        default=1.0,
        help="scale every GHB conductance (default 1.0)",
    )
    parser.add_argument(
        "--flow-length",
        type=float,
        default=FLOW_LENGTH,
        help=f"distance from the cell center to the coast (default {FLOW_LENGTH:.1f} m)",
    )
    args = parser.parse_args(argv)

    sim = flopy.mf6.MFSimulation.load(
        sim_name="sv", sim_ws=args.source, write_headers=False, verbosity_level=0
    )
    gwf = sim.get_model()
    spd = coastal_ghb_data(gwf, cond_mult=args.cond_mult, flow_length=args.flow_length)
    flopy.mf6.ModflowGwfghb(
        gwf,
        pname="ghb-1",
        auxiliary=["ELEVATION", "CONCENTRATION"],
        boundnames=True,
        print_flows=True,
        stress_period_data={0: spd},
        observations={
            "sv.ghb.obs.csv": [("coast-swgw", "ghb", "coast")],
            "filename": "sv.ghb.obs",
        },
    )
    # copy the source files as they are, since rewriting them all with flopy
    # rounds some values, and write only the GHB files
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(args.source, DEST)
    sim.set_sim_path(DEST)
    gwf.ghb.write()
    gwf.ghb.obs.write()
    nam = DEST / "sv.nam"
    text = nam.read_text()
    nam.write_text(text.replace("END packages", "  GHB6  sv.ghb  ghb-1\nEND packages", 1))
    # the stream outlet's inflow from the mover converges slowly in the steady
    # state period once the coast lowers the heads around it
    ims = DEST / "sv.ims"
    text = ims.read_text()
    if "OUTER_MAXIMUM  500" not in text:
        sys.exit("sv.ims has no OUTER_MAXIMUM 500 to raise")
    ims.write_text(text.replace("OUTER_MAXIMUM  500", "OUTER_MAXIMUM  1000", 1))
    print(f"{DEST.name}: {len(spd)} GHB cells")
    return 0


if __name__ == "__main__":
    sys.exit(main())
