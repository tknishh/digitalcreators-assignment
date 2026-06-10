#!/usr/bin/env bash
# Generate short synthetic test videos with FFmpeg (requires ffmpeg installed)
set -euo pipefail

OUT_DIR="${1:-./test_videos}"
mkdir -p "$OUT_DIR"

for i in 1 2 3; do
  ffmpeg -y -f lavfi -i "testsrc=duration=8:size=640x360:rate=30" \
    -f lavfi -i "sine=frequency=440:duration=8" \
    -c:v libx264 -c:a aac -shortest \
    "$OUT_DIR/sample_${i}.mp4"
done

echo "Created 3 test videos in $OUT_DIR"
