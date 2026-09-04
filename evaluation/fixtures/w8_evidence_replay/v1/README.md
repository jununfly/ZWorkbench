# W8 H5 Evidence/replay fixture v1

This fixture is product-execution evidence for the owner-backed replay seam.
It contains no credentials, network implementation, Provider client, tool
runner, or external side effect. The runner creates a case-local
`CompositionOwner` database and binds the cassette to the actual owner event
digest before exercising the product service.

The cassette is sealed and its file digest is part of the replay identity.
Changing any byte, omitting a required identity, or using an unknown owner
schema must produce `unknown`/`safe_stop`. `live_replay` is always denied by
default.
