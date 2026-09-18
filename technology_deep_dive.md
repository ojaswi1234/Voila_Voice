Technology Deep‑Dive – Annotated Bullet Points

- **Go (golang)**
  - *Where used*: Core backend services – Backend, Device management, DeliveryDispatcher, WebSocketClient, SecurityAlert modules; also compiled CLI `voila.exe` for the Local Agent.
  - *How implemented*: Written as idiomatic Go packages, leveraging static typing and Go modules. Binary distributed as a single executable for cross‑platform deployment. Uses Go’s `crypto` package for PBKDF2 hashing, and custom circuit‑breaker implementation.
  - *Why chosen*: Low latency, high concurrency via goroutines, easy cross‑compilation to a single binary; static typing prevents runtime errors; Go’s ecosystem provides mature WebSocket libraries.

- **Gorilla WebSocket (github.com/gorilla/websocket)**
  - *Where used*: Real‑time transport layer in the backend, handling the `/ws` endpoint and upgrading HTTP connections.
  - *How implemented*: Instantiated via `upgrader.Upgrade` in Go server; configured with ping/pong timeouts, max message size, and per‑connection `WebSocketClient` structs that manage read/write loops.
  - *Why chosen*: RFC‑compliant, battle‑tested, simple API that integrates cleanly with Go’s HTTP server; offers built‑in support for compression and concurrency without extra boilerplate.

- **Firebase Cloud Messaging (FCM) – Go SDK**
  - *Where used*: Push notification fallback when WebSocket delivery fails or for async alerts (e.g., security alerts, task completion).
  - *How implemented*: Go SDK (`firebase.google.com/go/messaging`) called from the `Push Notification` module; constructs `Message` structs with target device tokens and payload, then invokes `client.Send`.
  - *Why chosen*: Off‑loads push infrastructure to Google, provides cross‑platform (iOS/Android) support, eliminates the need to manage APNs certificates; reliable scaling and built‑in analytics.

- **Go Crypto (crypto package) & PBKDF2**
  - *Where used*: Security module for hashing security phrases, generating authentication tokens, and implementing rate‑limiting counters.
  - *How implemented*: Utilizes `golang.org/x/crypto/pbkdf2` with a per‑device salt; hashes stored in a circular ring buffer for quick lookup; integrated with the circuit‑breaker pattern to throttle abusive requests.
  - *Why chosen*: Native Go implementation avoids pulling in heavyweight external libs; PBKDF2 is a well‑vetted KDF suitable for password‑like secrets; easy to audit.

- **Circuit‑Breaker & Rate‑Limiter (custom Go implementation)**
  - *Where used*: Guarding the DeliveryDispatcher and SecurityAlert pipelines.
  - *How implemented*: Maintains sliding‑window counters; trips breaker after a configurable error threshold; automatically resets after cooldown.
  - *Why chosen*: Prevents cascading failures under load or compromised devices; custom implementation gives fine‑grained control and eliminates external dependencies.

- **Flutter (Dart)**
  - *Where used*: Mobile front‑end (Android & iOS) UI – `main.dart`, UI widget tree, `visualizer.dart`, `connection_flowchart.dart`.
  - *How implemented*: Single codebase compiled to native ARM binaries via Flutter SDK; integrates with FCM using `firebase_messaging` plugin; establishes WebSocket connections via Dart `web_socket_channel`.
  - *Why chosen*: Unified UI across platforms, hot‑reload accelerates development, rich widget library for custom “sketch‑style” UI, direct Dart‑to‑Go interop via platform channels when needed.

- **Python (Doc Generation)**
  - *Where used*: Local Agent’s document generation pipeline – `document_tools.py`, `design_tokens.go`, `document_ir.go`.
  - *How implemented*: Python scripts orchestrate markdown → HTML → PDF conversion using `weasyprint` and PPTX generation via `python-pptx`. Templates are defined in Go design‑token files for consistent styling.
  - *Why chosen*: Python excels at rapid templating, has mature libraries for PDF/PPTX creation, and simplifies integration with existing Go token definitions.

- **WeasyPrint (Python library)**
  - *Where used*: Rendering markdown‑based reports into high‑fidelity PDF documents.
  - *How implemented*: Markdown is first converted to HTML (via `markdown2`), then fed to `weasyprint.HTML(string=html).write_pdf(output_path)`.
  - *Why chosen*: Produces CSS‑styled PDFs with minimal configuration; supports custom fonts and layout needed for the hand‑sketched blueprint aesthetic.

- **python‑pptx**
  - *Where used*: Generating slide decks (`.pptx`) from the same markdown templates used for PDFs.
  - *How implemented*: Script iterates over slide definitions, creates `Presentation` objects, adds text boxes, images, and charts via the library’s API.
  - *Why chosen*: Mature, pure‑Python API, easy to script bulk slide creation, aligns with the team’s “single source of truth” for documentation.

- **GitHub Actions (YAML)**
  - *Where used*: CI/CD pipelines for Go, Python, and Flutter components – files `ci-go.yml`, `ci-python.yml`, `ci-flutter.yml`, and `build‑apk.yml`.
  - *How implemented*: Each workflow defines job matrix for OS, runs linters (`golangci-lint`, `flake8`), executes unit tests, builds binaries (`go build`) and mobile artifacts (`flutter build apk`/`ipa`). Artifacts are uploaded to GitHub Releases.
  - *Why chosen*: Native to the repository hosting platform, secret‑free builds using GitHub OIDC, supports multi‑language matrix builds, provides built‑in artifact storage and release automation.

- **Node.js (npm) Script Helpers** – `setup_ngrok.js`
  - *Where used*: Development convenience script that starts an Ngrok tunnel for local testing of the backend endpoint.
  - *How implemented*: Uses the `ngrok` npm package, reads configuration from environment variables, and prints the public URL to console for devs.
  - *Why chosen*: Minimal setup, cross‑platform, leverages existing Node ecosystem; developers already have Node installed, making it an easy plug‑and‑play tool.

- **Design Tokens (Go & Python)** – `design_tokens.go`, `design_tokens.py`
  - *Where used*: Central repository for visual styles (colors, fonts, spacing) used across PDF, PPTX, and mobile UI.
  - *How implemented*: Defined as Go structs and exported as JSON; Python reads the JSON to apply consistent styling in doc generation.
  - *Why chosen*: Guarantees visual consistency across all artifact outputs; single source of truth reduces drift between UI and documentation.

- **Worker Pool (Go)** – `NewDeliveryDispatcher(maxWorkers, maxQueueSize)`
  - *Where used*: Backend's asynchronous job processing for voice command delivery.
  - *How implemented*: Spawns a fixed number of goroutine workers pulling from a buffered channel; back‑pressure applied via queue size limit.
  - *Why chosen*: Simple, performant concurrency model; avoids spawning unbounded goroutines which could exhaust resources.

- **Circular Ring Buffer (Go)** – `alertRingBuffer`
  - *Where used*: In‑memory store for recent security alerts broadcast to all connected mobiles.
  - *How implemented*: Fixed‑size slice with head/tail pointers; overwrites oldest entries when full.
  - *Why chosen*: Constant‑time insert/retrieval, low memory footprint, suitable for real‑time alert streaming.

- **Prometheus (optional, mentioned)**
  - *Where used*: Potential observability layer for metrics export.
  - *How implemented*: Exposes `/metrics` endpoint using `github.com/prometheus/client_golang`.
  - *Why chosen*: De‑facto standard for time‑series monitoring; integrates with Grafana dashboards.
