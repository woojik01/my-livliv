# LivLiv Player 0.3.0 runtime

My LivLiv embeds the official browser Player distribution for its local preview tab.
The files in `dist/` are copied from the published npm package `@livliv-dev/player@0.3.0`.
The npm lockfile records the registry URL and integrity hash used to obtain that release.

This runtime includes only the browser entry point and its three imported JavaScript chunks.
Optional MediaPipe, Three.js, and VRM peer dependencies are not installed because the
LivLiv v4 2D character preview does not use those optional features.

The upstream package is licensed under Apache License 2.0. Its `LICENSE` and `NOTICE`
files are included beside this document. The upstream package's sample character assets
are not included.
