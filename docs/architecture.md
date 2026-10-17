# Architecture

Stealth Mesh is organized as a layered, simulation-first system. The application submits messages to transport; transport handles queues, acknowledgements, retries, and deduplication; core represents packets, nodes, topology, and events; routing selects paths; radio provides an interchangeable link interface; monitoring records behavior. Security protects message data and authenticates peers. Simulation and experiments exercise the same abstractions without physical radios. Firmware is a separate embedded target.

Dependencies should point inward toward domain abstractions. ML predictions are optional inputs to route metrics; baseline routing must remain usable without a model.

## Current prototype status

Core message, packet, node, topology, network, and domain-event models (`core/`) are implemented. The software radio layer (`radio/`) defines the `RadioInterface` protocol, `LoRaModulationConfig` validation, rolling `LinkQualityTracker` observations, and `RadioSimulator` for direct-hop loss, node availability, and latency using a configurable random seed (latency is a simulated measurement and does not delay execution or access physical hardware).

Routing (`routing/`) provides deterministic weighted Dijkstra path selection (`dijkstra.py`), consecutive-hop failure detection (`failure_detector.py`), link-cost adjustment with safe fallback (`route_metrics.py`), effective active topology filtering (`graph.py`), and adaptive failover (`route_manager.py`).

Machine learning (`ml/`) provides 7-feature link-quality extraction (`features.py`), group-isolated leakage-free dataset splitting (`dataset.py`), pure-Python standardized L2-regularized logistic regression training (`train.py`), `MLLinkQualityPredictor` with automatic fallback to `BaselineLinkEstimator` (`predict.py`), and held-out Brier/log-loss/accuracy evaluation (`evaluate.py`).

Transport (`transport/`) provides an in-memory FIFO queue and a synchronous delivery coordinator with bounded hop retries, duplicate suppression, and local acknowledgement tracking. It does not yet implement on-wire acknowledgement packets, timeout scheduling, or durable storage across restarts.

The simulation and experiment layer (`simulation/`, `experiments/`) provides `SimulationRunner`, reproducible packet-loss and relay node-failure scenarios, JSON summary export, and side-by-side baseline vs. ML-assisted routing comparison (`python3 -m experiments.compare_algorithms`). See [the roadmap](roadmap.md) for the verified checklist.
