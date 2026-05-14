# Cart-Node

Cart-Node is an edge-to-cloud, multi-agent e-commerce delivery platform relying on natural language processing, dynamic geographic routing, and secure, intercepted billing.

## Architecture

*   **Mobile Client (Edge):** Android Native (Kotlin, Jetpack Compose) / Kotlin Multiplatform. Utilizes Ktor Client for SSE/WebSocket streams.
*   **Agent Orchestration (Backend):** Python-based Google Agent Development Kit (ADK) managed via `uv`, with FastAPI.
*   **Identity & Authentication:** 100% custom, ground-up framework (JWT/Session based) strictly without third-party auth dependencies.

## Setup & Execution

### Backend
The backend is a Python FastAPI application managed by `uv`.
To run the server:
```bash
cd cart-node-backend
uv run uvicorn main:app --reload
```

### Android
The Android client is built with Kotlin and Jetpack Compose.
To build the app:
```bash
cd cart-node-android
./gradlew assembleDebug
```

## Testing

A unified test script is provided in the repository root to execute both backend and frontend tests.
```bash
./run_tests.sh
```
