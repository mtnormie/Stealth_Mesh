# Threat Model

Assets include message confidentiality, message integrity, node credentials, and availability of the mesh. Consider passive listeners, packet modification, replay, impersonation, node loss, and congestion. Authenticated encryption and replay protection address only some threats; they do not hide traffic patterns or guarantee availability. Key provisioning, revocation, and physical compromise remain open design concerns.
