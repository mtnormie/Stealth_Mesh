# Architecture

Stealth Mesh is organized as a layered, simulation-first system. The application submits messages to transport; transport handles queues, acknowledgements, retries, and deduplication; core represents packets, nodes, topology, and events; routing selects paths; radio provides an interchangeable link interface; monitoring records behavior. Security protects message data and authenticates peers. Simulation and experiments exercise the same abstractions without physical radios. Firmware is a separate embedded target.

Dependencies should point inward toward domain abstractions. ML predictions are optional inputs to route metrics; baseline routing must remain usable without a model.

## Current prototype status

Core message, packet, node, topology, and network models are implemented. The
software radio simulator models direct-hop loss, node availability, and latency
using a configurable random seed; latency is a returned simulated measurement and
does not delay execution or access hardware. Routing currently provides weighted
Dijkstra path selection. Transport currently provides an in-memory queue and a
synchronous delivery coordinator with bounded hop retries and local acknowledgement
tracking. It does not yet implement on-wire acknowledgement packets, timeout or
durable-queue behavior. See [the roadmap](roadmap.md) for the verified checklist.

The simulation runner combines Dijkstra routing, the software radio, and
transport; it collects per-message outcomes, delivery ratio, attempts, modeled
latency, and ordered in-memory events. It has no configuration-file loader or
result-file exporter yet.
