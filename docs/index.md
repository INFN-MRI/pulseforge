# Pulserver

Pulserver plays Pulseq sequences on an MR scanner through the scanner's
interpreter and returns the reconstructed images to the console. It sits
between the scanner and two engines it does not reimplement: pypulseqpp designs
the sequence and bartorch reconstructs it. On the scanner host, pulserver turns
each prescription the operator edits into the protocol the sequence will play,
such as the shortest echo time or a bandwidth on the sampling raster, and writes
the design the scanner downloads. On the reconstruction computer, it receives
the raw data of every running series, attaches the trajectory and the
prescription, routes the series to a reconstruction and returns the images.

The {doc}`API reference <api/index>` documents the Python interface by topic.

```{toctree}
:hidden:

api/index
```
