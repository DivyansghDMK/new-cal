#!/bin/bash

# CardioX Launcher Script for macOS
# This script launches the CardioX application

echo "🚀 Starting CardioX..."
echo "📱 Application: CardioX.app"
echo "📁 Location: $(pwd)/dist/CardioX.app"
echo ""

# Check if the app exists
if [ ! -d "dist/CardioX.app" ]; then
    echo "❌ Error: CardioX.app not found!"
    echo "Please run 'pyinstaller CardioX.spec --clean' first to build the application."
    exit 1
fi

# Launch the application
echo "🎯 Launching CardioX..."
open "dist/CardioX.app"

echo "✅ CardioX launched successfully!"
echo "💡 Tip: You can also double-click CardioX.app in Finder to launch it."
