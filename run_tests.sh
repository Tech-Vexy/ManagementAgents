#!/bin/bash
set -e

echo "Running Backend Tests..."
cd cart-node-backend
uv run pytest
cd ..

echo "Running Android Tests..."
cd cart-node-android
./gradlew test
cd ..

echo "All tests passed successfully!"
