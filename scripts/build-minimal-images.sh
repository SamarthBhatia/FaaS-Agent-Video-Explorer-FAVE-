#!/bin/bash
#
# Build FAVE Minimal Base Images
#
# Creates optimized base images for each function type:
#   - minimal-core:   ~500 MB (orchestrator, deepspeech)
#   - minimal-ffmpeg: ~800 MB (ffmpeg-0, ffmpeg-1, ffmpeg-2, ffmpeg-3)
#   - minimal-librosa: ~1.2 GB (librosa)
#   - minimal-onnx:   ~1.0 GB (object-detector)
#
# Usage:
#   ./scripts/build-minimal-images.sh           # Build all minimal images
#   ./scripts/build-minimal-images.sh --compare # Build and show size comparison
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_IMAGE_DIR="${SCRIPT_DIR}/../base-image"

COMPARE=false
if [[ "$1" == "--compare" ]]; then
    COMPARE=true
fi

echo "========================================"
echo "Building FAVE Minimal Base Images"
echo "========================================"
echo ""

cd "$BASE_IMAGE_DIR"

# Build minimal-core
echo "Building fave-minimal-core:dev..."
docker build -f Dockerfile.minimal-core -t fave-minimal-core:dev .
echo ""

# Build minimal-ffmpeg
echo "Building fave-minimal-ffmpeg:dev..."
docker build -f Dockerfile.minimal-ffmpeg -t fave-minimal-ffmpeg:dev .
echo ""

# Build minimal-librosa
echo "Building fave-minimal-librosa:dev..."
docker build -f Dockerfile.minimal-librosa -t fave-minimal-librosa:dev .
echo ""

# Build minimal-onnx
echo "Building fave-minimal-onnx:dev..."
docker build -f Dockerfile.minimal-onnx -t fave-minimal-onnx:dev .
echo ""

echo "========================================"
echo "Build Complete!"
echo "========================================"
echo ""

# Show image sizes
echo "Image Sizes:"
echo "------------"
docker images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | grep -E "(fave-minimal|fave-base)"

if [ "$COMPARE" = true ]; then
    echo ""
    echo "========================================"
    echo "Size Comparison (Original vs Minimal)"
    echo "========================================"
    echo ""

    # Get sizes
    BASE_SIZE=$(docker images fave-base:dev --format "{{.Size}}" 2>/dev/null || echo "N/A")
    CORE_SIZE=$(docker images fave-minimal-core:dev --format "{{.Size}}" 2>/dev/null || echo "N/A")
    FFMPEG_SIZE=$(docker images fave-minimal-ffmpeg:dev --format "{{.Size}}" 2>/dev/null || echo "N/A")
    LIBROSA_SIZE=$(docker images fave-minimal-librosa:dev --format "{{.Size}}" 2>/dev/null || echo "N/A")
    ONNX_SIZE=$(docker images fave-minimal-onnx:dev --format "{{.Size}}" 2>/dev/null || echo "N/A")

    echo "| Image Type           | Original      | Minimal       | Savings |"
    echo "|---------------------|---------------|---------------|---------|"
    echo "| Base (full)         | ${BASE_SIZE}  | N/A           | 0%      |"
    echo "| Core (orchestrator) | ${BASE_SIZE}  | ${CORE_SIZE}  | ~75%    |"
    echo "| FFmpeg stages       | ${BASE_SIZE}  | ${FFMPEG_SIZE} | ~62%    |"
    echo "| Librosa stage       | ${BASE_SIZE}  | ${LIBROSA_SIZE} | ~44%    |"
    echo "| ONNX detector       | ${BASE_SIZE}  | ${ONNX_SIZE}  | ~53%    |"
    echo ""
    echo "Function Mapping:"
    echo "  - orchestrator       → fave-minimal-core"
    echo "  - stage-deepspeech   → fave-minimal-core"
    echo "  - stage-ffmpeg-0/1/2/3 → fave-minimal-ffmpeg"
    echo "  - stage-librosa      → fave-minimal-librosa"
    echo "  - stage-object-detector → fave-minimal-onnx"
fi
