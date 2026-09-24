from .generic_official import GenericOfficialAdapter


class ILOAdapter(GenericOfficialAdapter):
    def __init__(self):
        super().__init__("ilo")
