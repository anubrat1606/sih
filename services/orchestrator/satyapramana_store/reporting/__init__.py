"""Reporting: Bid Autopsy and Compliance Repair (satyapramana.md section 11).

Both are deterministic and derived from the event log / rule pack -- neither
regenerates anything with a model. Framework-free like services/core on
purpose: every function here takes plain data (a rule pack, a list of verdict
rows, a registry) and returns plain data, so it is testable without a running
orchestrator and without a database.
"""
