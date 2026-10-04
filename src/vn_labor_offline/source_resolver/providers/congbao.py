from .generic_official import GenericOfficialAdapter,canonicalize_url


class CongBaoAdapter(GenericOfficialAdapter):
    def __init__(self):
        super().__init__("congbao")

    def candidate_urls(self,url:str)->list[str]:
        return [canonicalize_url(url)] if url else []
