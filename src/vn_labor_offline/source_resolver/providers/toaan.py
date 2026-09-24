from .generic_official import GenericOfficialAdapter


class ToaanAdapter(GenericOfficialAdapter):
    def __init__(self):
        super().__init__("toaan")
