# Host daemon

`pulserver.host`: design sessions for the PSD host processes of one scanner.
Run the daemon with
`python -m pulserver.host --base DIR --socket PATH --plugins DIR [--workers N]`.

```{eval-rst}
.. currentmodule:: pulserver.host
```

## Daemon and client

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   HostDaemon
   HostClient
   HostError
```

## Sessions

```{eval-rst}
.. autosummary::
   :toctree: ../generated
   :nosignatures:

   SessionKey
   SessionStore
   Session
   revision_hash
```
