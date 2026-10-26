# Class models and data

## Synthetic valley

The synthetic valley is a coastal aquifer system that drains south to the sea.
It is described in Hughes, J.D., Langevin, C.D., Paulinski, S.R., Larsen, J.D.,
and Brakenhoff, D., 2024, FloPy workflows for creating structured and
unstructured MODFLOW models: Groundwater, v. 62, no. 1, p. 124–139,
https://doi.org/10.1111/gwat.13327. The models here come from
[jdhughes-dev/mf6-training](https://github.com/jdhughes-dev/mf6-training),
converted from feet to meters, with a General-Head Boundary (GHB) at sea level
added along the southern edge.

Every model works in meters and days and has five layers:

- layers 1 and 2 are the upper aquifer,
- layer 3 is a clay confining unit, active only where the clay is present;
  elsewhere its cells are vertical pass-through cells (`idomain` of -1) that
  connect layer 2 directly to layer 4, and
- layers 4 and 5 are the lower aquifer.

The simulation starts with a 16,071-day steady-state stress period, which gives
the flow system before pumping, followed by 20 one-year transient periods. Two
pumping wells, `reilly` and `vc`, screened in layers 4 and 5, start in the
second stress period. The coastal GHB holds a head of 0 m and carries the
elevation of the boundary and a seawater concentration of 35 kilograms per
cubic meter as auxiliary variables, for density-dependent flow.

| Model | Grid | Stresses |
|---|---|---|
| `synthetic-valley-coastal-base-annual` | structured, 40 rows by 25 columns of 152.4 m cells | Recharge (RCH); a lake of high hydraulic conductivity cells with Evapotranspiration (EVT); a stream of River (RIV) cells; the pumping wells, one Well (WEL) cell per layer |
| `synthetic-valley-coastal-advanced-annual` | structured, 40 rows by 25 columns of 152.4 m cells | Unsaturated Zone Flow (UZF); Streamflow Routing (SFR); Lake (LAK); Water Mover (MVR), which routes UZF runoff to the lake and stream; the pumping wells as Multi-Aquifer Wells (MAW) |
| `synthetic-valley-coastal-vg-base-annual` | Voronoi, 6,300 cells per layer | the base model's stresses |
| `synthetic-valley-coastal-vg-advanced-annual` | Voronoi, 6,300 cells per layer | the advanced model's stresses; this model defines the truth for the class |

The two structured models share their aquifer properties, which represent the
valley with one horizontal hydraulic conductivity field for both aquifers. The
Voronoi-grid models take their aquifer properties from the truth dataset
instead: a separate hydraulic conductivity field for each layer, interpolated
to the cell centers, and the clay's own vertical hydraulic conductivity. Their
other inputs come from the structured model of the same kind, at the
structured cell that holds each Voronoi cell center.

### Data

`synthetic-valley/data` holds the data the Voronoi-grid models are built from
and the true observations:

| File | Contents |
|---|---|
| `synthetic_valley_truth.nc` | the truth dataset on the structured grid, in meters: hydraulic conductivity of each layer, the clay and its vertical hydraulic conductivity, the lake, layer elevations, and heads |
| `obs_well_info.csv` | the 17 observation wells: row and column of the structured grid (counted from 1), location, well depth, and the layer of the lower-aquifer observation |
| `synthetic_valley_vg_truth.nc` | the heads in every cell at the end of each stress period of the Voronoi-grid advanced model, its geometry and hydraulic conductivity, and its observed series: heads at the observation wells, stream flow, lake stage, and flow to the sea |

### Rebuilding the Voronoi-grid models

`scripts/build_vg_models.py` rebuilds both Voronoi-grid models from the
structured models and the truth dataset, and `--grid` builds them on another
Voronoi grid. `scripts/write_vg_truth.py` writes `synthetic_valley_vg_truth.nc`
from a run of the Voronoi-grid advanced model. Run both inside the pixi
environment.
