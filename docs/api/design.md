# Scanner sequences

`pulserver.design`: a pypulseqpp application exposed to the scanner UI. A plugin
file defines one {class}`~pulserver.design.ScannerSequence` subclass, whose `ui`
maps interpreter parameter names to arguments of the application's
`init_sequence`.

```{eval-rst}
.. currentmodule:: pulserver.design
```

## Sequence

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   ScannerSequence
   load_plugin
```

## UI entries

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   TimeParam
   FloatParam
   IntParam
   BoolParam
   StringListParam
   ConfigParam
   Description
```
