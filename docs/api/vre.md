# Reconstruction proxy

`pulserver.vre`: the reconstruction computer's half of the orchestrator. It
serves the scanner's reconstruction client, attaches to every series what the
sequence that played it says about its readouts, and routes the series to a
worker process. Run it with
`python -m pulserver.vre --base DIR --port N --plugins DIR [--slots N] [--spares 1]`.

```{eval-rst}
.. currentmodule:: pulserver.vre
```

## Proxy

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   ReconProxy
```

## Revisions

The header of an incoming stream names the design it was played from in the
`pulserver_session` and `pulserver_revision` user parameters.

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   RevisionStore
   Revision
   SESSION_PARAMETER
   REVISION_PARAMETER
```

## Enrichment

A readout table maps onto MRD counters, flags, encoding spaces and
trajectories. Readouts are demodulated to the prescription centre the
`pulserver_fov_offset_mm` user parameter carries, in mm along the sequence's
gradient axes.

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   SequenceTable
   TableSpace
   enrich_header
   enrich_acquisition
   fov_offset_m
   FOV_OFFSET_PARAMETER
```
