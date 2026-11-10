import argparse
import sys
from pathlib import Path
from gpx_writer import GpxWriter
from nmea_parser import NmeaParser
from track_filter import TrackFilter


def main():
    parser = argparse.ArgumentParser(description="Prevede NMEA log do GPX trasy.")
    parser.add_argument("input", help="vstupni NMEA soubor")
    parser.add_argument("output", nargs="?", help="vystupni GPX soubor (default: output/<nazev>.gpx)")
    parser.add_argument("--min-time", type=float, default=0, help="min. casovy rozdil v sekundach")
    parser.add_argument("--min-heading", type=float, default=0, help="min. zmena smeru ve stupnich")
    parser.add_argument("--min-distance", type=float, default=0, help="min. vzdalenost v metrech")
    args = parser.parse_args()

    out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(exist_ok=True)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute() and output.parent == Path("."):
            output = out_dir / output.name
    else:
        output = out_dir / (Path(args.input).stem + ".gpx")
    output = str(output)

    segments = NmeaParser().parse_file(args.input)
    track_filter = TrackFilter(args.min_time, args.min_heading, args.min_distance)
    filtered = track_filter.apply(segments)

    if not filtered:
        print("zadne platne body pro export", file=sys.stderr)
        return 1

    GpxWriter().write(output, filtered)
    total = sum(len(segment) for segment in filtered)
    print(f"exportovano {total} bodu do {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
