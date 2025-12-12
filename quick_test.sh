#!/bin/bash
# Quick test script for Miami-Dade Docket Monitor

echo "=================================="
echo "Miami-Dade Docket Monitor Test"
echo "=================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

if [ $? -ne 0 ]; then
    echo "❌ Error: Python 3 not found"
    exit 1
fi

echo ""
echo "Installing dependencies..."
pip install -q requests beautifulsoup4

echo ""
echo "Running single check (--once mode)..."
echo ""

python3 deuker-monitor.py -c config.json --once

echo ""
echo "=================================="
echo "Test complete!"
echo "To run continuous monitoring:"
echo "  python3 deuker-monitor.py -c config.json"
echo "=================================="
