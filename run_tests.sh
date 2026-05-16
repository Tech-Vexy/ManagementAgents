#!/bin/bash
set -e

echo "Running Backend Tests..."
cd cart-node-backend
uv run pytest
cd ..

echo "Running Flutter Tests..."
cd cart_node_flutter
flutter test
cd ..

echo "All tests passed successfully!"
