# Reconstruction plugins

`pulserver.recon`: what a reconstruction is written against. A plugin file
defines one {class}`~pulserver.recon.ReconPlugin` subclass and a module-level
`PLUGIN` instance; the same hooks run over a live MRD stream, over an MRD file
and over an assembled bucket.

```{eval-rst}
.. currentmodule:: pulserver.recon
```

## Plugin

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   ReconPlugin
   Gadget
   load_plugin
```

## Scan context

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   ReconContext
   ExamCache
```

## Buffers and results

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   ReconBuffer
   ReconData
   ReconResult
```
