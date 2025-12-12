#!/bin/bash

# Manual Lambda Dependency Installation Script
# Installs Python dependencies for all Lambda functions without Docker

echo "========================================"
echo "Lambda Dependency Installation"
echo "========================================"
echo ""

# Check if we're in the right directory
if [ ! -d "lambda" ]; then
    echo "❌ Error: lambda directory not found"
    echo "Please run this script from your project root directory"
    exit 1
fi

echo "This will install Python dependencies for all Lambda functions."
echo "Press Enter to continue..."
read

# Counter for tracking
TOTAL=0
SUCCESS=0
SKIPPED=0

# Find all Lambda function directories with requirements.txt
echo ""
echo "Finding Lambda functions with requirements.txt..."
echo "=================================================="
echo ""

LAMBDA_DIRS=$(find lambda -name "requirements.txt" -type f -exec dirname {} \;)

for lambda_dir in $LAMBDA_DIRS; do
    TOTAL=$((TOTAL + 1))
    
    echo ""
    echo "[$TOTAL] Processing: $lambda_dir"
    echo "----------------------------------------"
    
    REQ_FILE="$lambda_dir/requirements.txt"
    
    # Check if requirements.txt is empty
    if [ ! -s "$REQ_FILE" ]; then
        echo "⚠️  requirements.txt is empty, skipping"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi
    
    # Show what will be installed
    echo "Dependencies to install:"
    cat "$REQ_FILE" | grep -v "^#" | grep -v "^$"
    echo ""
    
    # Create package directory
    PACKAGE_DIR="$lambda_dir/package"
    mkdir -p "$PACKAGE_DIR"
    
    # Install dependencies
    echo "Installing dependencies..."
    pip install -r "$REQ_FILE" -t "$PACKAGE_DIR" --upgrade --quiet
    
    if [ $? -eq 0 ]; then
        echo "✅ Successfully installed dependencies"
        SUCCESS=$((SUCCESS + 1))
        
        # Show installed size
        SIZE=$(du -sh "$PACKAGE_DIR" 2>/dev/null | cut -f1)
        echo "   Package size: $SIZE"
    else
        echo "❌ Failed to install dependencies"
    fi
done

echo ""
echo "========================================"
echo "Installation Summary"
echo "========================================"
echo ""
echo "Total Lambda functions: $TOTAL"
echo "Successfully installed: $SUCCESS"
echo "Skipped (empty): $SKIPPED"
echo "Failed: $((TOTAL - SUCCESS - SKIPPED))"
echo ""

if [ $SUCCESS -gt 0 ]; then
    echo "✅ Dependencies installed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Update your CDK stack to include the package directories"
    echo "2. Deploy: cdk deploy"
else
    echo "❌ No dependencies were installed"
    echo "Please check if requirements.txt files exist and contain packages"
fi

echo ""
