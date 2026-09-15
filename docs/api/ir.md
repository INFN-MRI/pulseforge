# IR conversion

`pulserver.ir`: a Pulseq sequence and its `NextSequence` chain segmented into the
binary IR cache the scanner interpreter loads beside the sequence file.

The chain is read with `pypulseqpp.Sequence`, text or binary; the segmentation
— event deduplication, the repeating unit, the virtual segments and the
execution stream — runs in the compiled extension, and the cache is written by
the C library the interpreter reads it back with.

```{eval-rst}
.. currentmodule:: pulserver.ir
```

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   convert
   chain
   summary
   cache_path
```
