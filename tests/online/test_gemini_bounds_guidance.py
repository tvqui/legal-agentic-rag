import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from vn_labor_online.providers import GeminiProvider,gemini_array_limits
from vn_labor_online.answer_review import review_error_code
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.models import ResearcherResult


class GeminiBoundsGuidanceTests(unittest.TestCase):
    def test_original_nested_array_caps_are_available_without_schema_mutation(self):
        schema=ResearcherResult.model_json_schema(); original=copy.deepcopy(schema)
        guidance=gemini_array_limits(schema)
        self.assertIn('result.retrieval_queries: at most 4 items',guidance)
        self.assertIn('result.answer_tasks: at most 12 items',guidance)
        self.assertIn('LaborOntologyFeatures.events: at most 12 items',guidance)
        self.assertEqual(schema,original)
        self.assertEqual(gemini_array_limits({'type':'object'}),'')

    def test_sdk_gets_guidance_and_overflow_still_fails_closed(self):
        try: from google import genai
        except ImportError: self.skipTest('Optional google-genai SDK is not installed')
        sdk=Mock(); sdk.__enter__=Mock(return_value=sdk); sdk.__exit__=Mock(return_value=False)
        sdk.models.generate_content.return_value=SimpleNamespace(text=json.dumps({'rows':['a','b']}),candidates=[])
        schema={'type':'object','properties':{'rows':{'type':'array','maxItems':1,'items':{'type':'string'}}},'required':['rows']}
        with patch('google.genai.Client',return_value=sdk),patch('vn_labor_online.providers.get_gemini_limiter') as gate:
            gate.return_value.acquire.return_value=0
            with self.assertRaises(StructuredOutputError) as caught:
                GeminiProvider('test','dummy').structured('system','private user text',schema)
        self.assertEqual(str(caught.exception),'GEMINI_SCHEMA_VALIDATION_FAILED')
        self.assertEqual(review_error_code(caught.exception),'GEMINI_SCHEMA_VALIDATION_FAILED_MAX_ITEMS')
        config=sdk.models.generate_content.call_args.kwargs['config']
        self.assertIn('result.rows: at most 1 items',config.system_instruction)
        self.assertNotIn('maxItems',config.response_json_schema['properties']['rows'])
        self.assertNotIn('private',review_error_code(caught.exception))

    def test_untrusted_diagnostic_attributes_are_never_published(self):
        error=StructuredOutputError('GEMINI_SCHEMA_VALIDATION_FAILED')
        error.validation_keyword='private token https://secret.example'
        self.assertEqual(review_error_code(error),'GEMINI_SCHEMA_VALIDATION_FAILED')


if __name__=='__main__': unittest.main()
