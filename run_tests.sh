#!/bin/bash
set -e

echo "Running Backend Tests..."
cd cart-node-backend
uv run pytest test_auth.py test_main.py test_tools.py
cd ..

echo "Running Android Tests..."
cd cart-node-android
./gradlew test
cd ..

echo "All tests passed successfully!"
