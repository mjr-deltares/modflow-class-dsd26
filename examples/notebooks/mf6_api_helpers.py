"""Helpers for the MODFLOW 6 API notebooks (mf6-api-a to mf6-api-f).

The API notebooks drive MODFLOW 6 through its shared library, which pixi installs
with the class MODFLOW 6. These helpers find the library and draw the live
convergence plot of notebook b.
"""

import pathlib as pl
import shutil
import sys

import flopy
import numpy as np
from IPython.display import clear_output, display


def find_mf6_libraries():
    """Return the paths of the MODFLOW 6 shared library and executable.

    The API runs MODFLOW 6 through its shared library (libmf6.so on Linux,
    libmf6.dylib on macOS, libmf6.dll on Windows) rather than the mf6 program.
    `pixi run setup` installs both in the same folder of the pixi environment,
    bin on Linux and macOS and Scripts on Windows.
    """
    if sys.platform.startswith("win"):
        lib_file = "libmf6.dll"
    elif sys.platform == "darwin":
        lib_file = "libmf6.dylib"
    else:
        lib_file = "libmf6.so"
    exe = shutil.which("mf6")
    if exe is None:
        raise FileNotFoundError(
            "mf6 is not in the pixi environment; run `pixi run setup`"
        )
    exe = pl.Path(exe)
    # the folder of mf6 first, then the other folders of the environment
    prefix = pl.Path(sys.prefix)
    folders = (
        exe.parent,
        prefix / "bin",
        prefix / "Scripts",
        prefix / "Library" / "bin",
        prefix / "lib",
    )
    for folder in folders:
        if (folder / lib_file).is_file():
            return folder / lib_file, exe
    raise FileNotFoundError(
        f"{lib_file} is not in the pixi environment; run `pixi run setup`"
    )


def plot_convergence(fig, ax, history, max_ticks=25):
    """Redraw the convergence plot from the outer iterations solved so far.

    history holds one (iteration, largest head change, stress period, time step)
    tuple per outer iteration. Each time step gets the same width on the x-axis,
    so the long steady-state solve does not crowd out the transient time steps.
    Call it once per time step to watch the model converge as it runs.
    """
    ax.clear()
    if history:
        # the first and last iteration of each time step
        blocks, first = [], 0
        for n in range(len(history)):
            if n == len(history) - 1 or history[n][2:] != history[n + 1][2:]:
                blocks.append((first, n))
                first = n + 1

        # spread the iterations of each time step across its slot
        xs, ys = [], []
        for slot, (n0, n1) in enumerate(blocks):
            count = n1 - n0 + 1
            for m, n in enumerate(range(n0, n1 + 1)):
                xs.append(slot + (m + 0.5) / count)
                change = history[n][1]
                # a change of exactly zero cannot be drawn on a log axis
                ys.append(np.nan if change == 0.0 else change)
        ax.semilogy(
            xs, ys, marker="o", ms=3, lw=0.8, color="0.25", mfc="#2a78d6", mec="0.25"
        )

        # label at most max_ticks time steps
        stride = max(1, -(-len(blocks) // max_ticks))
        ticks, labels = [], []
        for slot, (_, n1) in enumerate(blocks):
            if slot % stride == 0 or slot == len(blocks) - 1:
                ticks.append(slot + 0.5)
                labels.append(f"{history[n1][2]}\n{history[n1][3]}")
                if slot > 0:
                    ax.axvline(slot, color="0.6", lw=0.5)
        ax.set_xticks(ticks)
        ax.set_xticklabels(labels)

    flopy.plot.styles.heading(ax=ax, heading="Outer iterations")
    flopy.plot.styles.xlabel(ax=ax, label="Stress period and time step")
    flopy.plot.styles.ylabel(ax=ax, label="Largest head change (m)")
    flopy.plot.styles.remove_edge_ticks(ax=ax)

    clear_output(wait=True)
    display(fig)
