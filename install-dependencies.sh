#!/bin/bash

# Find all requirements.txt files and install dependencies
for req in $(find lambda -name "requirements.txt"); do
    dir=$(dirname "$req")
    echo "Installing dependencies for $dir"
    pip install -r "$req" -t "$dir" --upgrade
done

echo "✅ All dependencies installed"