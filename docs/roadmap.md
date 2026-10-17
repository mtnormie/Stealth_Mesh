# Development Roadmap

This roadmap records behavior present in the repository, based on source inspection
and the verification commands noted below. A module or test filename by itself
does not count as an implemented feature.

## Implemented

- [x] Repository/module scaffold for app, core, routing, transport, radio,
  monitoring, simulation, ML, security, experiments, and firmware.
- [x] Project architecture, protocol intent, threat model, hardware notes, and
  experiment guidance are documented.
- [x] Core message, packet, node, topology, network, and domain-event models with
  validation.
- [x] Seeded radio simulation (`RadioSimulator`), `RadioInterface` protocol,
  `LoRaModulationConfig` validation, and rolling `LinkQualityTracker` observations;
  it does not perform physical radio communication.
- [x] Deterministic weighted Dijkstra path selection (`routing/dijkstra.py`),
  consecutive-hop `FailureDetector`, `compute_link_cost`, effective topology
  filtering (`routing/graph.py`), and adaptive `RouteManager` failover.
- [x] In-memory FIFO message queue, bounded hop retries, successful-delivery
  deduplication, and local acknowledgement/status tracking.
- [x] Aggregate delivery/attempt/latency metrics, network health diagnostics
  (`monitoring/diagnostics.py`), and ordered structured events.
- [x] Integrated simulation runner, named reproducible packet-loss and relay
  node-failure scenarios (`simulation/scenarios.py`), and JSON summary export.
- [x] ML link-quality feature extraction (`ml/features.py`), group-disjoint
  leakage-resistant dataset splits (`ml/dataset.py`), standardized L2 logistic
  regression training (`ml/train.py`), `MLLinkQualityPredictor` with fallback to
  `BaselineLinkEstimator` (`ml/predict.py`), held-out evaluation (`ml/evaluate.py`),
  and reproducible baseline vs. ML routing comparison (`experiments/compare_algorithms.py`).
- [x] AES-256-GCM authenticated encryption helper, random 256-bit group-key
  generation, and in-memory encrypted group messaging prototype.
- [x] Local web UI for creating groups, sending messages, QR-rendered
  single-use invitation tokens, and joining by token.
- [x] Automated unit tests across core, radio, routing, transport, failure scenarios,
  ML link-quality estimation, and security using Python's standard library test runner.

## Partially implemented

- [ ] Delivery is still a synchronous coordinator over an injected hop callback;
  wire-level ACK packets/timeouts, persistence, queue scheduling, and recovery after
  process restart are not implemented.
- [ ] Configuration YAML files (`config/*.yaml`, `experiments/*.yaml`) document
  reference parameters, though no external YAML parser dependency is required at runtime.
- [ ] Firmware source layout exists and hardware pinouts (`ESP32-C3 SuperMini` +
  `868 MHz LoRa`) are documented in `docs/hardware.md`, but physical firmware radio
  drivers remain unimplemented until hardware testing begins.

## Planned, prioritized

### 1. Core data models and radio simulation

- [x] Define validated message, packet, node, topology, network, and domain event models.
- [x] Simulate direct-link transmission with configurable latency, packet loss,
  node availability, and seeded outcomes.
- [x] Test model validation and radio success, loss, unavailable nodes, missing
  links, and invalid parameters.
- [ ] Add binary wire-format serialization when physical radio transport is integrated.

### 2. Deterministic baseline routing

- [x] Implement a weighted graph and Dijkstra route selection with stable tie
  handling, unreachable-destination behavior, and invalid-input checks.
- [x] Test routes, costs, disconnection, and invalid paths.
- [x] Integrate route calculation with live availability/failure detection (`RouteManager`, `FailureDetector`).

### 3. Reliable message delivery

- [x] Implement an in-memory bounded retry policy, FIFO queue, acknowledgement
  tracker, and duplicate suppression.
- [x] Expose delivery status and test retries, exhaustion, duplicate messages,
  and retrying after a failed attempt.
- [ ] Connect delivery directly to wire-level ACK packets, timeout handling,
  queue persistence, and asynchronous scheduling.

### 4. Monitoring and reproducible simulation

- [x] Implement metrics, structured events, network diagnostics, integrated scenario
  execution, and in-memory result output.
- [x] Add named packet-loss and node-failure experiments, plus JSON result export
  with documented parameters.

### 5. ML link-quality evaluation

- [x] Define feature/label schema and leakage-resistant group-isolated dataset splits.
- [x] Compare a simple baseline with an ML estimator; validate fallback behavior
  and report reproducible metrics (`experiments/compare_algorithms.py`).

### 6. Security

- [x] Select a maintained authenticated-encryption dependency and implement
  AES-256-GCM message protection for the local prototype.
- [ ] Define persistent key lifecycle, sender authentication, replay policy,
  and cross-device group membership/key provisioning.
- [x] Add security tests and document assumptions and limitations.

### 7. Application and hardware

- [x] Implement an initial local web interface for group messaging and QR invites.
- [ ] Connect the application service to routing/radio for actual multi-device
  delivery; add persistence and authenticated remote sessions.
- [ ] Implement and validate `ESP32-C3 SuperMini` + `868 MHz LoRa` firmware drivers
  after hardware assembly.

## Verification

- `python3 -m compileall -q app core radio routing transport monitoring simulation ml security experiments tests`
- `python3 -m unittest discover -s tests -v` (39 tests passed)
- `python3 -m experiments.compare_algorithms`
- `git diff --check`
