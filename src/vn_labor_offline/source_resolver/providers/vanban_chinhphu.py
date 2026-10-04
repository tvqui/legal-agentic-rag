from .generic_official import GenericOfficialAdapter,canonicalize_url


class VanBanChinhPhuAdapter(GenericOfficialAdapter):
    def __init__(self):
        super().__init__("vanban_chinhphu")

    def candidate_urls(self,url:str)->list[str]:
        return [canonicalize_url(url)] if url else []
