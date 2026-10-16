# Development Roadmap

This roadmap records behavior present in the repository, based on source inspection
and the verification commands noted below. A module or test filename by itself
does not count as an implemented feature.

## Implemented

- [x] Repository/module scaffold for app, core, routing, transport, radio,
  monitoring, simulation, ML, security, experiments, and firmware.
- [x] Project architecture, protocol intent, threat model, hardware notes, and
  experiment guidance are documented.
- [x] Core message, packet, node, topology, and network models with validation.
- [x] Seeded radio simulation for direct links, modeled latency, packet loss,
  and node availability; it does not perform physical radio communication.
- [x] Deterministic weighted Dijkstra path selection with unreachable-path
  reporting and stable equal-cost tie handling.
- [x] In-memory FIFO message queue, bounded hop retries, successful-delivery
  deduplication, and local acknowledgement/status tracking.
- [x] Aggregate delivery/attempt/latency metrics and ordered structured events.
- [x] Integrated simulation runner combining Dijkstra routing, simulated radio,
  transport delivery, and per-message result records.
- [x] AES-256-GCM authenticated encryption helper, random 256-bit group-key
  generation, and in-memory encrypted group messaging prototype.
- [x] Local web UI for creating groups, sending messages, QR-rendered
  single-use invitation tokens, and joining by token.
- [x] Unit tests for the first model and simulator stage using Python's standard
  library test runner.

## Partially implemented

- [ ] Automated test layout now covers core models/packets/simulation, routing,
  transport, simulation runner, and security; ML test module remains empty.
- [ ] Delivery is still a synchronous coordinator over an injected hop callback;
  ACK packets/timeouts, persistence, queue scheduling, and recovery after process
  restart are not implemented.
- [ ] Configuration examples exist for network and simulation settings, but no
  Python runtime currently loads or validates them.
- [ ] Firmware source layout exists, but it has no selected target or functional
  radio implementation.

## Planned, prioritized

### 1. Core data models and radio simulation

- [x] Define validated message, packet, node, topology, and network models.
- [x] Simulate direct-link transmission with configurable latency, packet loss,
  node availability, and seeded outcomes.
- [x] Test model validation and radio success, loss, unavailable nodes, missing
  links, and invalid parameters.
- [ ] Add domain events and serialization/wire-format decisions when protocol
  implementation needs them.

### 2. Deterministic baseline routing

- [x] Implement a weighted graph and Dijkstra route selection with stable tie
  handling, unreachable-destination behavior, and invalid-input checks.
- [x] Test routes, costs, disconnection, and invalid paths.
- [ ] Integrate route calculation with live availability/failure detection.

### 3. Reliable message delivery

- [x] Implement an in-memory bounded retry policy, FIFO queue, acknowledgement
  tracker, and duplicate suppression.
- [x] Expose delivery status and test retries, exhaustion, duplicate messages,
  and retrying after a failed attempt.
- [ ] Connect delivery directly to routing/radio objects; add wire-level ACKs,
  timeout handling, queue limits/persistence, and asynchronous scheduling.

### 4. Monitoring and reproducible simulation

- [x] Implement metrics, structured events, integrated scenario execution, and
  in-memory result output.
- [ ] Add named/config-driven packet-loss and node-failure experiments, plus
  persistent result export with documented parameters.

### 5. ML link-quality evaluation

- [ ] Define feature/label schema and leakage-resistant dataset splits.
- [ ] Compare a simple baseline with an ML estimator; validate fallback behavior
  and report reproducible metrics.

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
- [ ] Select supported radio hardware only after software interfaces and tests are
  stable; validate firmware and regulatory constraints separately.

## Audit baseline (2026-10-14)

The audit notes below describe the repository at that date and are retained as
historical context; security and UI now have the limited prototype documented
above.

- Source inspection before implementation: most Python modules were placeholder
  docstrings; `app/main.py` raises `NotImplementedError`; experiment entry point
  is a placeholder. Core, radio, baseline routing, transport, and basic monitoring
  plus simulation execution are now implemented. ML, security, UI, named scenarios,
  and experiment comparison remain unimplemented.
- At audit start, existing `tests/test_*.py` files contained only explanatory
  docstrings. Core/simulator, packets, routing, delivery, simulation-runner, and
  security tests have since been added.
- `python -m pytest -q` could not run because pytest is not installed in the
  environment (`No module named pytest`). No tests are reported as passing.
- Current verification: `python3 -m compileall -q app core radio routing transport
  monitoring simulation security tests`, `python3 -m unittest discover -s tests -v`
  (29 tests passed), and `git diff --check`.
- Firmware files are placeholders and `platformio.ini` has no default target.
