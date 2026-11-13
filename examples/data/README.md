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
  elsewhere its cells are vertical pass-through cells (`idomain` of -1) with
  no thickness, which connect layer 2 directly to layer 4, and
- layers 4 and 5 are the lower aquifer.

Layer 1 is convertible, except the base models' lake cells. Its top is the
land surface, from the mean of a 15.24 m raster of the land surface and lake
bed over each cell. The lake is the basin
of that surface flooded to 6.5 m, the largest extent of the lake in the
advanced models; a cell is in the lake where the flooded basin covers at least
half of it. The lake bed falls from the shore to the bottom of layer 1
(-1.524 m), which it reaches half way from the shore to the deepest point.
Groundwater that reaches the land surface away from the lake and the stream
leaves through seepage drains (DRN) on the layer 1 cells. Each starts to
discharge 0.1524 m (0.5 ft) below the land surface and reaches its full
conductance, the vertical hydraulic conductivity of layer 1 times the cell area
over the layer thickness, at the land surface. Every model starts from its steady-state heads,
changed by a uniform random amount of up to 0.1 m, and an advanced model's lake
from its steady-state stage.

The simulation starts with a 16,071-day steady-state stress period, which gives
the flow system before pumping, followed by 20 one-year transient periods. Two
pumping wells, `reilly` and `vc`, screened in layers 4 and 5, start in the
second stress period. The coastal GHB holds a head of 0 m and carries the
elevation of the boundary and a seawater concentration of 35 kilograms per
cubic meter as auxiliary variables, for density-dependent flow.

| Model | Grid | Stresses |
|---|---|---|
| `synthetic-valley-coastal-base-annual` | structured, 40 rows by 25 columns of 152.4 m cells | Recharge (RCH); a lake of high hydraulic conductivity layer 1 cells whose top is the water surface at the lake's largest extent, with Evapotranspiration (EVT); a stream of River (RIV) cells; seepage drains; the pumping wells, one Well (WEL) cell per layer |
| `synthetic-valley-coastal-advanced-annual` | structured, 40 rows by 25 columns of 152.4 m cells | Unsaturated Zone Flow (UZF) on the land; Streamflow Routing (SFR); Lake (LAK) on top of the aquifer, with a stage-volume-area table; seepage drains; Water Mover (MVR), which routes UZF runoff and the drains' discharge to where the land surface drains: the lake, or the stream reach it reaches; the pumping wells as Multi-Aquifer Wells (MAW) |
| `synthetic-valley-coastal-vg-base-annual` | Voronoi, 6,150 cells per layer | the base model's stresses |
| `synthetic-valley-coastal-vg-advanced-annual` | Voronoi, 6,150 cells per layer | the advanced model's stresses; this model defines the truth for the class |

The base models' land recharge is the advanced models' infiltration less
their potential evapotranspiration, times 2.08, which leaves the structured
base model's steady-state heads at the observation wells about 0.3 m below the
truth on average.

In the advanced models the lake is connected vertically to the layer 1 cell
under it, whose top is the lake bed. Where the bed is the bottom of layer 1,
the layer 1 cell is a vertical pass-through cell and the lake is connected to
layer 2. The stage-volume-area table runs from the bottom of layer 1 to
14.96 m, where the flooded basin would cross the ridge, so the lake has no
outlet.

The two structured models share their aquifer properties, which represent the
valley with one horizontal hydraulic conductivity field for both aquifers. The
Voronoi-grid models take their aquifer properties from the truth dataset
instead: a separate hydraulic conductivity field for each layer, interpolated
to the cell centers, and the clay's own vertical hydraulic conductivity. Their
other inputs come from the structured model of the same kind, at the
structured cell that holds each Voronoi cell center, except the top, the lake,
and the runoff routing, which come from the land surface raster. The Voronoi
grid is refined along the stream, around the pumping wells, and over the lake
at its largest extent.

### Data

`synthetic-valley/data` holds the data the Voronoi-grid models are built from
and the true observations:

| File | Contents |
|---|---|
| `synthetic_valley_truth.nc` | the truth dataset on the structured grid, in meters: hydraulic conductivity of each layer, the clay and its vertical hydraulic conductivity, the lake, layer elevations, and heads |
| `synthetic_valley_topography.nc` | the land surface and lake bed on 400 rows by 250 columns of 15.24 m cells, in meters, and the lake of the mesh it comes from |
| `obs_well_info.csv` | the 17 observation wells: row and column of the structured grid (counted from 1), location, well depth, and the layer of the lower-aquifer observation |
| `synthetic_valley_vg_truth.nc` | the heads in every cell at the end of each stress period of the Voronoi-grid advanced model, its geometry and hydraulic conductivity, and its observed series: heads at the observation wells, stream flow, lake stage, and flow to the sea |

### Rebuilding the models

Run these inside the pixi environment, in this order:

1. `scripts/build_topography.py --mesh <file>` writes
   `synthetic_valley_topography.nc` from the synthetic-valley mesh
   (`TriMesh_with_densified_contours.exp`, in feet), interpolated linearly within
   its triangles. It is needed only to change the raster.
2. `scripts/update_structured_models.py` puts the top, the lake, and the runoff
   routing on the two structured models, in place.
3. `scripts/build_vg_grid.py --dest <dir>` builds the Voronoi grid. It is
   needed only to change the grid.
4. `scripts/build_vg_models.py --grid <dir>` rebuilds both Voronoi-grid models
   from the structured models, the truth dataset, and the raster.
5. `scripts/write_vg_truth.py` writes `synthetic_valley_vg_truth.nc` from a run
   of the Voronoi-grid advanced model.

Runoff is routed over the raster, cell to cell, to the steepest downslope
neighbor after the pits are filled, and each UZF cell's runoff goes to where
most of its raster cells drain: the lake or a stream reach. All of a seepage
drain's discharge goes to the same place as the runoff of its cell. Water whose
path reaches the coast is not moved, since a General-Head Boundary cannot receive
water from MVR. Steps 2 and 4 run each model to find its steady-state heads.
