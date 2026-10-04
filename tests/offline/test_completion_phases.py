from __future__ import annotations

import json
import unittest

from vn_labor_offline.legal_structure import parse_legal_document
from vn_labor_offline.source_resolver.discovery.searxng import SearxngDiscovery
from vn_labor_offline.source_resolver.providers.generic_official import canonicalize_url


class OfflineCompletionPhaseTests(unittest.TestCase):
    def test_official_url_canonicalization_preserves_identity_and_drops_tracking(self):
        value=canonicalize_url('HTTPS://VBPL.VN/TW/Pages/view.aspx?utm_source=x&ItemID=162453#top')
        self.assertEqual(value,'https://vbpl.vn/TW/Pages/view.aspx?ItemID=162453')

    def test_searxng_requires_opt_in_and_bounds_results(self):
        discovery=SearxngDiscovery('https://search.example.test')
        with self.assertRaisesRegex(RuntimeError,'NETWORK_DISABLED'):
            discovery.search('45/2019/QH14')
        payload={'results':[{'url':'https://vbpl.vn/a','title':'A'},
          {'url':'http://unsafe.test/b','title':'B'},{'url':'https://vbpl.vn/a','title':'duplicate'}]}
        discovery=SearxngDiscovery('https://search.example.test',transport=lambda *_:json.dumps(payload),max_results=2)
        self.assertEqual([row['url'] for row in discovery.search('45/2019/QH14')],['https://vbpl.vn/a'])

    def test_ocr_point_without_space_keeps_exact_span(self):
        doc={'document_id':'doc','effective_from':'2021-01-01'}
        text='Điều 113. Nghỉ hằng năm\n1. Số ngày nghỉ:\na)12 ngày làm việc\nđ)Nội dung điểm đ'
        rows=parse_legal_document(doc,text)
        points=[row for row in rows if row['level']=='POINT']
        self.assertEqual([row['number'] for row in points],['a','đ'])
        for row in points:
            self.assertEqual(text[row['char_start']:row['char_end']],row['text'])


if __name__=='__main__': unittest.main()
