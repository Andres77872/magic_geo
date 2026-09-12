# Complete historical water-chain fixtures

These are unchanged compressed outputs retained by the durable seasonal regression sweep. The manifest records the exact original configuration, source archive entry, compressed SHA256, decoded SHA256, cell count and all seven water-model identities. The loader verifies both hashes and the identity declarations before returning a world.

The native climate is the current seasonal energy model. The historical part is the Python aquifer → groundwater → channel → hydraulics → navigation → ports → corridors chain, whose original v1 equations and exact CLI diagnostics remain supported. Selecting `LegacyWorldConfig` would change a different model and is not a substitute for these fixtures.

Use these only for historical equation/error compatibility tests. Generic current-world tests continue to generate the current chain, or use an explicit verification runner that checks a retained world's configuration and replays the complete current tail. No normal test implicitly restores an ignored local cache.

The full records are intentionally retained: slicing a water subsystem or retagging parent metadata would not provide a valid full-CLI control. Tests that subsequently alter terrain, settlement scores or topology are explicitly downstream equation probes; they do not claim the modified input remains a valid native world.
