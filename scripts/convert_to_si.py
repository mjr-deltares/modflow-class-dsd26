#!/usr/bin/env python
"""Convert a structured synthetic-valley model from feet to meters.

Every quantity with a length dimension is scaled by the power of 0.3048 its
dimension carries (lengths, rates in ft/d, conductances in ft2/d, flows in
ft3/d, specific storage in 1/ft), so the converted model gives the same
results in meters. Ratios, fractions, water contents, leakances (1/d), and
-999 placeholders are left as they are. Manning's n is also left as it is,
taken as an SI value, so SFR flows differ from those of the feet model, which
has no LENGTH_CONVERSION. Run inside the pixi environment, e.g.

    pixi run convert-to-si examples/data/synthetic-valley/synthetic-valley-coastal-base-annual
"""

import argparse
import pathlib as pl
import sys

import flopy
import numpy as np

FT = 0.3048  # meters per foot
PLACEHOLDER = -999.0

# field: power of length, for list data that is set the same way in every
# package that has it
LIST_FIELDS = {
    "ghb": {"bhead": 1, "cond": 2, "elevation": 1},
    "riv": {"stage": 1, "cond": 2, "rbot": 1},
    "wel": {"q": 3},
    "rch": {"recharge": 1},
    "evt": {"surface": 1, "rate": 1, "depth": 1},
    "uzf": {"finf": 1, "pet": 1, "extdp": 1, "ha": 1, "hroot": 1},
}
# MAW and LAK period settings given by keyword
SETTINGS = {
    "maw": {"rate": 3},
    "lak": {"rainfall": 1, "evaporation": 1, "stage": 1, "runoff": 3, "inflow": 3, "withdrawal": 3},
}


def uniform_or_array(values):
    """A single value for a uniform array, so it is written as a constant."""
    first = values.flat[0]
    return float(first) if np.all(values == first) else values


def scale_array(data, power):
    """Scale a griddata array by 0.3048**power, keeping layers and constants."""
    if not data.has_data():
        return
    values = data.array * FT**power
    # (nlay, nrow, ncol) arrays are set layer by layer
    if values.ndim == 3:
        data.set_data([uniform_or_array(values[k]) for k in range(values.shape[0])])
    else:
        data.set_data(uniform_or_array(values))


def scale_fields(rec, fields):
    """Scale the fields of a record array in place, skipping -999 placeholders."""
    for name, power in fields.items():
        if name not in rec.dtype.names:
            continue
        values = rec[name]
        for i in range(len(values)):
            if values[i] != PLACEHOLDER:
                values[i] = values[i] * FT**power


def scale_list(data, fields):
    """Scale list data, which is either one record array or one per stress period."""
    if not data.has_data():
        return
    value = data.get_data()
    if isinstance(value, dict):
        for kper in value:
            if value[kper] is not None:
                scale_fields(value[kper], fields)
    else:
        scale_fields(value, fields)
    data.set_data(value)


def scale_settings(data, column, settings):
    """Scale MAW or LAK period settings given by keyword."""
    if not data.has_data():
        return
    value = data.get_data()
    for kper, rec in value.items():
        for i in range(len(rec)):
            power = settings.get(str(rec[column][i]).lower())
            if power is not None:
                rec[f"{column}_data"][i] = float(rec[f"{column}_data"][i]) * FT**power
        value[kper] = rec
    data.set_data(value)


def convert(gwf):
    dis = gwf.dis
    if str(dis.length_units.get_data()).lower() != "feet":
        sys.exit(f"{gwf.model_ws}: LENGTH_UNITS is not feet")
    dis.length_units = "meters"
    for name in ("delr", "delc", "top", "botm"):
        scale_array(getattr(dis, name), 1)
    scale_array(gwf.ic.strt, 1)
    # K33OVERK makes k33 a ratio, which stays as it is
    scale_array(gwf.npf.k, 1)
    if gwf.get_package("sto") is not None:
        scale_array(gwf.sto.ss, -1)

    for pkg in gwf.packagelist:
        ptype = pkg.package_type
        if ptype in LIST_FIELDS:
            data = pkg.perioddata if ptype == "uzf" else pkg.stress_period_data
            scale_list(data, LIST_FIELDS[ptype])
        if ptype == "uzf":
            scale_list(pkg.packagedata, {"surfdep": 1, "vks": 1})
        elif ptype == "sfr":
            scale_list(
                pkg.packagedata, {"rlen": 1, "rwid": 1, "rtp": 1, "rbth": 1, "rhk": 1}
            )
            if pkg.perioddata.has_data():
                sys.exit("SFR period data is not converted")
        elif ptype == "maw":
            scale_list(pkg.packagedata, {"radius": 1, "bottom": 1, "strt": 1})
            scale_list(
                pkg.connectiondata,
                {"scrn_top": 1, "scrn_bot": 1, "hk_skin": 1, "radius_skin": 1},
            )
            scale_settings(pkg.perioddata, "mawsetting", SETTINGS["maw"])
        elif ptype == "lak":
            if pkg.tables.has_data() or pkg.outlets.has_data():
                sys.exit("LAK tables and outlets are not converted")
            scale_list(pkg.packagedata, {"strt": 1})
            scale_list(
                pkg.connectiondata,
                {"belev": 1, "telev": 1, "connlen": 1, "connwidth": 1},
            )
            scale_settings(pkg.perioddata, "laksetting", SETTINGS["lak"])
        elif ptype == "mvr":
            rec = pkg.perioddata.get_data()
            for kper in rec:
                if np.any(np.char.lower(rec[kper]["mvrtype"].astype(str)) != "factor"):
                    sys.exit("only FACTOR movers are converted")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("model_ws", type=pl.Path, help="model to convert in place")
    args = parser.parse_args(argv)

    sim = flopy.mf6.MFSimulation.load(
        sim_ws=args.model_ws, write_headers=False, verbosity_level=0
    )
    # write every value with its full precision
    sim.simulation_data.float_precision = 12
    sim.simulation_data.float_characters = 21
    convert(sim.get_model())
    ims = sim.get_package("ims")
    for name in ("outer_dvclose", "inner_dvclose"):
        data = getattr(ims, name)
        if data.has_data():
            data.set_data(data.get_data() * FT)
    sim.write_simulation(silent=True)
    print(f"{args.model_ws.name}: converted to meters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
