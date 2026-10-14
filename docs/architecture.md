# Architecture

Stealth Mesh is organized as a layered, simulation-first system. The application submits messages to transport; transport handles queues, acknowledgements, retries, and deduplication; core represents packets, nodes, topology, and events; routing selects paths; radio provides an interchangeable link interface; monitoring records behavior. Security protects message data and authenticates peers. Simulation and experiments exercise the same abstractions without physical radios. Firmware is a separate embedded target.

Dependencies should point inward toward domain abstractions. ML predictions are optional inputs to route metrics; baseline routing must remain usable without a model.
