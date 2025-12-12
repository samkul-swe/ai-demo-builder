#!/bin/bash
set -e

echo "🎬 Setting up FFmpeg layer for AWS Lambda"
echo "=========================================="
echo ""

# Create directory structure
echo "Creating directory structure..."
mkdir -p layers/ffmpeg/python/bin

cd layers/ffmpeg

# Download FFmpeg
echo "Downloading FFmpeg static build (this may take a minute)..."
wget --progress=bar:force https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz

# Extract
echo ""
echo "Extracting..."
tar xf ffmpeg-release-amd64-static.tar.xz

# Find directory
FFMPEG_DIR=$(ls -d ffmpeg-*-amd64-static 2>/dev/null | head -1)

if [ -z "$FFMPEG_DIR" ]; then
    echo "❌ ERROR: Could not find extracted FFmpeg directory"
    ls -la
    exit 1
fi

echo "Found FFmpeg directory: $FFMPEG_DIR"

# Copy binaries
echo "Copying binaries..."
cp "$FFMPEG_DIR/ffmpeg" python/bin/
cp "$FFMPEG_DIR/ffprobe" python/bin/

# Make executable
chmod +x python/bin/ffmpeg
chmod +x python/bin/ffprobe

# Verify
echo ""
echo "✅ FFmpeg layer setup complete!"
echo ""
echo "Binaries installed:"
ls -lh python/bin/

# Get sizes
FFMPEG_SIZE=$(du -h python/bin/ffmpeg | awk '{print $1}')
FFPROBE_SIZE=$(du -h python/bin/ffprobe | awk '{print $1}')

echo ""
echo "Summary:"
echo "  ffmpeg:  $FFMPEG_SIZE"
echo "  ffprobe: $FFPROBE_SIZE"
echo "  Location: layers/ffmpeg/python/bin/"
echo ""

# Verify structure
cd ../..
echo "Directory structure:"
tree layers/ffmpeg -L 3 2>/dev/null || ls -R layers/ffmpeg

# Cleanup
cd layers/ffmpeg
rm -rf "$FFMPEG_DIR"
rm ffmpeg-release-amd64-static.tar.xz
cd ../..

echo ""
echo "✅ Ready for CDK deployment!"
echo ""
echo "Next steps:"
echo "  1. Run: cdk bootstrap aws://288418345946/us-west-1"
echo "  2. Run: cdk deploy"

