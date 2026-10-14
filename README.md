# Stealth Mesh

**An Intelligent, Self-Organizing Wireless Mesh Network**

Stealth Mesh is a research project focused on developing an autonomous wireless Mesh network for short text messages and lightweight data exchange when conventional communication infrastructure is unavailable or unreliable.

The project explores machine learning (ML) for link-quality estimation, adaptive routing, reliable message delivery, fault tolerance, and communication resilience under changing network conditions.

The primary goal is to investigate whether combining ML-based link assessment with conventional routing algorithms can improve message delivery reliability and route recovery compared with a baseline implementation.

> **Research status:** Experimental project under development. Network performance, hardware compatibility, and resilience claims must be validated through reproducible simulations and controlled experiments.

## Key Features

- **Self-organizing Mesh networking** — models a network of interconnected nodes without requiring a permanently available central controller.
- **ML-based link-quality estimation** — investigates whether machine learning can predict link quality from observed network metrics.
- **Adaptive routing** — combines link-quality estimates with graph-based routing algorithms.
- **Fault tolerance** — evaluates route recovery after individual nodes or links become unavailable.
- **Reliable message delivery** — supports acknowledgements, bounded retransmissions, duplicate detection, and message queues.
- **End-to-end security** — designed to use established cryptographic libraries for message confidentiality and integrity.
- **Network monitoring** — collects delivery ratio, latency, retransmissions, route recovery time, and other experimental metrics.
- **Simulation-first development** — enables testing network behavior before deployment on physical hardware.

## Project Objectives

1. Design a modular architecture for an autonomous wireless Mesh network.
2. Implement a conventional routing baseline for comparison.
3. Develop and evaluate an ML model for link-quality estimation.
4. Investigate route recovery following node failures and intermittent connectivity.
5. Evaluate reliable message delivery under simulated packet loss and changing link conditions.
6. Compare ML-assisted routing against baseline routing using reproducible experiments.
7. Document hardware constraints, security assumptions, and limitations.

## Architecture Overview

The project is organized into several logical modules.

| Module | Responsibility |
|---|---|
| `core/` | Nodes, messages, packets, network topology, and events |
| `routing/` | Graph representation, baseline pathfinding, and route management |
| `ml/` | Dataset preparation, model training, prediction, and evaluation |
| `transport/` | Message queues, acknowledgements, retries, and duplicate detection |
| `security/` | Cryptographic integration, authentication, and integrity checks |
| `radio/` | Radio-interface abstraction and channel simulation |
| `monitoring/` | Metrics, diagnostics, and experiment logs |
| `simulation/` | Network simulation and failure scenarios |
| `experiments/` | Reproducible configurations and algorithm comparisons |
| `firmware/` | Experimental embedded implementation for supported microcontrollers |
| `app/` | User-facing interface and message-status presentation |
| `docs/` | Architecture, protocol, hardware, and research documentation |
| `tests/` | Automated tests for core functionality |

Some modules may remain planned until their implementation and testing are complete.

## How It Works

At a high level, the system follows this workflow:

1. A user creates a text message in the application.
2. The message is assigned a unique identifier and protected using the configured security mechanisms.
3. The transport layer places the message in a queue and requests transmission.
4. Network monitoring provides observations about available links.
5. The ML module estimates link quality when a trained and validated model is available.
6. The routing module evaluates available paths using link metrics and a conventional graph algorithm.
7. The selected next hop receives and forwards the packet according to the network protocol.
8. The destination validates the message and returns an acknowledgement.
9. The sender updates the delivery status only after receiving the appropriate confirmation.
10. If a node or link becomes unavailable, the routing module attempts to find another valid path. If no path exists, the message remains pending according to the queue policy.

The ML component assists decision-making; it does not replace protocol validation or guarantee an optimal route.

## Machine Learning Approach

The ML component is intended to estimate link quality or the likelihood of successful packet delivery.

Potential input features include:

- Recent packet delivery ratio
- Observed latency
- Retransmission count
- RSSI or SNR, when available
- Recent link availability
- Historical stability of a connection

Possible outputs include a link-quality score or an estimated probability of successful delivery.

The model should be compared against a non-ML baseline. A fallback routing algorithm should remain available when predictions are unavailable, uncertain, or invalid.

Model performance should be evaluated using held-out data to reduce the risk of overfitting.

## Communication Resilience

The project investigates resilience through:

- Alternative-path availability
- Detection of unavailable nodes
- Route recalculation
- Acknowledgements and bounded retransmissions
- Duplicate detection
- Queued messages during temporary disconnections
- Recovery after connectivity returns

These mechanisms can improve resilience to certain failures and packet losses. They cannot guarantee delivery when every available path is unavailable.

## Radio Technologies

The radio layer is designed to be modular so that network logic can be evaluated independently of a specific transceiver.

LoRa-capable hardware may be considered for low-rate, long-range experimental communication, subject to the capabilities of the selected module and applicable regulations.

Frequency hopping and other physical-layer techniques are potential research topics only where the hardware, protocol, and permitted operating conditions support them. Their effectiveness must be established experimentally; no technique should be assumed to guarantee immunity to intentional interference.

## Security and Privacy

The security architecture is intended to include:

- Established authenticated-encryption mechanisms
- Message integrity and sender authentication
- Appropriate key management
- Replay protection
- Minimization of unnecessary metadata and sensitive logs

Encryption protects message content but does not automatically conceal the existence, timing, or physical origin of a radio transmission. Intermediate relays do not guarantee that a network is undetectable.

The project therefore treats privacy, communication availability, and radio detectability as distinct research questions.

## Experiments and Evaluation

The initial evaluation should use a network simulator and reproducible scenarios.

| Scenario | Measurements |
|---|---|
| Normal network operation | Delivery ratio, latency, retransmissions |
| Random packet loss | Delivery success and overhead |
| Individual node failure | Route recovery time and message loss |
| Intermittent connectivity | Queue behavior and delivery after recovery |
| Changing link quality | Prediction accuracy and routing performance |
| Baseline vs. ML-assisted routing | Performance differences under identical conditions |

Recommended metrics include:

- Packet delivery ratio
- Median and 95th-percentile message latency
- Route recovery time
- Number of retransmissions
- Routing computation time
- CPU and memory usage
- Energy consumption, when measurable
- ML prediction quality on held-out data

Results should report the test conditions, sample sizes, variability, and limitations.

## Repository Structure

```text
Stealth-Mesh/
├── app/              # User interface and application services
├── config/           # Simulation, network, and logging settings
├── core/             # Nodes, messages, packets, topology, and events
├── docs/             # Architecture, protocol, threat, hardware, and experiment notes
├── experiments/      # Reproducible scenario configurations
├── firmware/         # Embedded firmware workspace
├── ml/               # Link-quality data, model, and evaluation modules
├── monitoring/       # Metrics, event logs, and diagnostics
├── radio/            # Radio abstraction and channel simulator
├── results/          # Generated experiment results
├── routing/          # Graph routing and route management
├── security/         # Encryption, authentication, keys, and integrity
├── simulation/       # Simulation runner and failure/loss scenarios
├── tests/            # Test module placeholders
├── transport/        # Delivery, acknowledgements, retries, and deduplication
├── LICENSE
├── README.md
├── requirements.txt
└── pyproject.toml
```

The modules are scaffolds: implementation and validation are still pending. See `docs/architecture.md` for responsibilities and dependency boundaries.

## Development Roadmap

- [ ] Define the message format and node model
- [ ] Implement the network graph and baseline routing
- [ ] Build a radio-channel simulator
- [ ] Implement acknowledgements and message queues
- [ ] Add node-failure and packet-loss scenarios
- [ ] Collect experimental datasets
- [ ] Train and evaluate the link-quality model
- [ ] Compare ML-assisted routing with the baseline
- [ ] Integrate established security mechanisms
- [ ] Evaluate a supported hardware prototype
- [ ] Document reproducible results and limitations

## Research Context

Stealth Mesh is being developed as a student research project. Its central research question is whether ML-assisted link-quality estimation can improve routing decisions and message delivery in a changing, partially disconnected wireless network.

The project prioritizes measurable results, reproducibility, modular design, and honest reporting of technical limitations.

## Disclaimer

This repository is an experimental research project, not a certified communication or safety-critical system. It does not guarantee uninterrupted connectivity, immunity to radio interference, or undetectability.

Physical radio experiments must comply with applicable spectrum regulations and equipment requirements.

## License

This project is licensed under the MIT License; see `LICENSE`.
