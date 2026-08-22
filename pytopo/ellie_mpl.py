#!/usr/bin/env python3

# The Ellie, using matplotlib, for when Qt isn't available

import sys, os

from trackstats import analyze_track, parse_trackstat_args

try:
    import pylab as plt
    have_plt = True
except ImportError:
    have_plt = False
    print("plt (matplotlib) isn't installed; "
          "will print stats only, no plotting", file=sys.stderr)

if 'numpy' not in sys.modules:
    print("Ellie requires the numpy module")
    sys.exit(1)


def plot_track(trackfile, out, args):
    # Set up the plots. First, will there be a speed plot, or just elevations?
    if "Speeds" in out or "Calculated Speeds" in out:
        numplots = 2
    else:
        numplots = 1

    fig, axes = plt.subplots(nrows=numplots, ncols=1,
                             figsize=(8, 3.5 * numplots))
                             # figsize is  width, height in inches

    # First plot: elevation profile
    ax = axes[0]
    ax.plot(out['Distances'], out['Elevations'],
               label="GPS elevation data", color="gray")
    ax.plot(out['Distances'], out['Smoothed elevations'],
               color="red", label="smoothed (b=%.1f, hw=%d)" % (args.beta,
                                                                args.halfwin))

    if args.metric:
        ax.set_xlabel("kilometers")
        ax.set_ylabel("meters")
        climb_units = 'm'
        dist_units = 'km'
    else:
        ax.set_xlabel("miles")
        ax.set_ylabel("feet")
        climb_units = "'"
        dist_units = 'mi'
    ax.grid(True)
    ax.legend()
    ax.title.set_text("Elevation profile (%d%s climb in %.1f %s)"
                      % (out['Smoothed total climb'], climb_units,
                         out['Distances'][-1], dist_units))

    # Now for the second plot: speeds
    if len(axes) == 2 and ("Speeds" in out or "Calculated Speeds" in out):
        ax = axes[1]
        if "Speeds" in out:
            ax.plot(out['Speeds'], color="red", label="Speed (from GPX)")
        if "Calculated Speeds" in out:
            ax.plot(out['Calculated Speeds'], color="blue",
                    label="Speed (calculated)")
        ax.set_xlabel("time (no units)")
        if args.metric:
            ax.set_ylabel("km/hour")
        else:
            ax.set_ylabel("mi/hour")
        ax.grid(True)
        ax.legend()
        ax.title.set_text("Speed (average %.1f moving)"
                          % out["Average moving speed"])

    # Set the window titlebar to something other than "Figure 1"
    title = "%s: %s" % (os.path.basename(sys.argv[0]), trackfile)
    try:
        # gcf stands for "get current figure"
        # Old way:
        plt.gcf().canvas.set_window_title(title)
    except AttributeError:
        # New (2022-3) way:
        plt.gcf().canvas.manager.set_window_title(title)

    fig.tight_layout()        # Or equivalently,  "plt.tight_layout()"
    plt.show()


def main():
    args = parse_trackstat_args(sys.argv)

    for trackfile in args.track_files:
        out = analyze_track(trackfile, args)
        plot_track(trackfile, out, args)


#
# main() to gather stats from a file passed in on the commandline
# and graph them if possible, else just print them.
#
if __name__ == '__main__':
    main()
