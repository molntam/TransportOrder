class SpotfireProvider:
    id = "spotfire"
    label = "Spotfire"
    available = False
    description = "Reserved for the dedicated report. No browser automation is connected yet."

    @staticmethod
    def collect():
        raise NotImplementedError("Connect a dedicated Spotfire report through this provider.")
