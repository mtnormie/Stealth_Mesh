# AGENTS.md — Stealth Mesh

## 1. Project Context

Stealth Mesh is a research and engineering project focused on an autonomous, self-organizing wireless Mesh network for short text messages and lightweight data exchange when centralized infrastructure is unavailable or unreliable.

The project is intended for educational research, civilian emergency communications, disaster resilience, and controlled network simulations.

The long-term goal is to develop a working software prototype, evaluate its algorithms, and later integrate compatible radio hardware.

## 2. Core Requirements

- Build the software incrementally and keep it runnable.
- Clearly distinguish implemented features from planned features.
- Do not pretend that simulated radio communication is real hardware communication.
- Prefer modular, testable, maintainable code.
- Use type hints, docstrings, and meaningful variable names.
- Handle invalid inputs, node failures, timeouts, and missing configuration.
- Do not add unnecessary dependencies.
- Never hardcode secrets, encryption keys, or credentials.
- Update documentation when architecture or behavior changes.
- Do not rewrite unrelated code without a reason.

## 3. Architecture

Keep these components separate:

- `app/`: user interface and application entry point.
- `core/`: nodes, messages, packets, network topology, and events.
- `routing/`: network graph, routing algorithms, route management, and failure detection.
- `ml/`: feature extraction, dataset preparation, model training, inference, and evaluation.
- `transport/`: queues, acknowledgements, retries, deduplication, and delivery status.
- `security/`: authentication, encryption, integrity, and key-management interfaces.
- `radio/`: radio abstraction, link-quality measurements, and simulated radio transport.
- `monitoring/`: metrics, diagnostics, and structured event logging.
- `simulation/`: reproducible network experiments and result collection.
- `firmware/`: future embedded firmware and hardware integration.
- `tests/`: automated tests.
- `docs/`: architecture, protocol, threat model, experiments, and roadmap.

Adapt this structure to the existing repository instead of duplicating files or creating a second architecture.

## 4. Development Priorities

Implement in this order:

1. Inspect the repository and document its current state.
2. Define message, packet, node, and network data models.
3. Build a radio simulator with configurable latency, packet loss, and node availability.
4. Implement baseline graph-based routing, initially using Dijkstra's algorithm.
5. Implement message queues, acknowledgements, retries, deduplication, and delivery status.
6. Add network monitoring and reproducible simulations.
7. Implement and evaluate an ML-based link-quality estimator against a non-ML baseline.
8. Add and test the security layer using established cryptographic libraries and protocols.
9. Create a usable application interface.
10. Integrate physical radio hardware only after the software interfaces and tests are stable.

Do not implement everything in one enormous change. Work in small, testable increments.

## 5. Routing and Machine Learning

- Maintain a deterministic baseline routing algorithm.
- Define ML inputs, target labels, and evaluation metrics explicitly.
- Avoid data leakage between training and evaluation datasets.
- Compare ML predictions with a simple baseline.
- Evaluate delivery rate, latency, packet loss, route recovery time, and computational cost.
- Include a fallback when the ML model is unavailable, untrained, or produces invalid output.
- Never let ML predictions alone determine whether a packet is delivered successfully.

## 6. Reliability and Security

- Use authenticated encryption through established, maintained libraries.
- Include message integrity, sender authentication, replay protection, and appropriate key-management interfaces.
- Do not invent a custom cryptographic algorithm.
- Treat routing metadata and radio transmission metadata as separate privacy concerns from message contents.
- Document security assumptions, limitations, and failure modes.
- Do not claim that encryption, routing, or relays guarantee invisibility or protection against every form of interference.
- Focus resilience testing on controlled simulations and lawful civilian emergency-communication scenarios.

## 7. Testing

For every meaningful change:

- Add or update unit tests.
- Run the relevant automated tests.
- Check edge cases and error handling.
- Keep experiments reproducible with documented parameters and random seeds where applicable.
- Record what was tested and any remaining limitations.

Never report a test as passed unless it was actually executed and passed.

## 8. How to Work on Tasks

Before editing:

1. Read this file and the relevant project documentation.
2. Inspect the actual repository structure and existing implementation.
3. Identify the smallest useful implementation step.
4. Explain the proposed changes briefly.

After editing:

1. Run relevant tests and static checks when available.
2. Summarize files changed and behavior implemented.
3. List commands used and their actual results.
4. Identify unfinished work and the next recommended step.
5. Update the roadmap and documentation when appropriate.

Do not silently replace working implementations or invent requirements that conflict with the repository.

## 9. Definition of Done

A feature is complete only when:

- Its behavior is implemented, not merely described.
- Relevant tests exist and pass.
- Errors and edge cases are handled.
- Documentation reflects the actual implementation.
- Limitations and unimplemented dependencies are clearly stated.