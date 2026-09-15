"""A reconstruction that raises on the first readout it is given."""

from pulserver.recon import ReconPlugin


class CrashRecon(ReconPlugin):
    def receive(self, acquisition, context):
        raise RuntimeError("this reconstruction always fails")

    def recon(self, branch, context):
        return None


PLUGIN = CrashRecon()
