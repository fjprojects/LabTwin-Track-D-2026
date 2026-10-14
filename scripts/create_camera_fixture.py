"""Build a reproducible face/blank browser camera fixture, never user video.

Default image: Matplotlib's bundled grace_hopper.jpg sample. This public sample
is used only for face-presence testing; no identity or intent is estimated.
Matplotlib is a test-tool dependency, not a new production dependency.
"""
import argparse
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--image", type=Path)
args = parser.parse_args()
if args.image:
    source = args.image
else:
    import matplotlib
    source = Path(matplotlib.get_data_path()) / "sample_data/grace_hopper.jpg"
if not source.is_file():
    raise SystemExit("The public camera test image is unavailable")
args.output.parent.mkdir(parents=True, exist_ok=True)
filters = ("[0:v]scale=640:480:force_original_aspect_ratio=decrease,"
           "pad=640:480:(ow-iw)/2:(oh-ih)/2:gray,setsar=1,fps=10,"
           "trim=duration=8,setpts=PTS-STARTPTS[face];"
           "[1:v]setsar=1,setpts=PTS-STARTPTS[blank];"
           "[face][blank]concat=n=2:v=1:a=0,format=yuv420p[out]")
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-loop", "1", "-i", str(source),
                "-f", "lavfi", "-i", "color=c=gray:s=640x480:r=10:d=12", "-filter_complex", filters,
                "-map", "[out]", "-t", "20", "-y", str(args.output)], check=True, timeout=60)
print("PASS: reproducible camera fixture generated")
