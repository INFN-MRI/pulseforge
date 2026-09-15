# MRD data

`pulserver.mrd`: acquisitions, header entries and images as a reconstruction
plugin reads them, and the facts a Pulseq sequence states about the readouts it
plays.

```{eval-rst}
.. currentmodule:: pulserver.mrd
```

## Acquisitions

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   AcquisitionBucket
   AcquisitionBucketStats
   AcquisitionFlag
   has_acquisition_flag
   acquisition_label
   acquisition_labels
```

## Header

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   EncodingSpace
   LOOP_COUNTERS
   MrdMetadata
   user_parameter
   max_stored_value
```

## Images

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   coil_combine
   center_crop
   as_numpy
```

## Sequence facts

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   read_chain
   SequenceDefinitions
   ReadoutTable
```
