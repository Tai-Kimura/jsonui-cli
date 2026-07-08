"""API mock support: generate mock definitions from OpenAPI and serve them locally.

Sub-modules:
- openapi:  dependency-free OpenAPI loader, $ref resolver, sample-value synthesis
- generate: scaffold tests/mocks/<tag>/<operationId>.mock.json + --check drift report
- server:   local mock server (routing, scenarios, admin API, control panel, run trigger)
"""
