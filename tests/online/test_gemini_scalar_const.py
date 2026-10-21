import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from jsonschema import Draft202012Validator

from vn_labor_online.providers import GeminiProvider,gemini_transport_schema
from vn_labor_online.models import ResearcherResult
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.answer_review import review_error_code


class GeminiScalarConstTests(unittest.TestCase):
    def test_scalar_lowering_preserves_the_exact_accepted_set(self):
        for value,typ in [('NORMALIZED_QUERY','string'),(True,'boolean'),(3,'integer'),(None,'null')]:
            schema={'type':typ,'const':value}; original=copy.deepcopy(schema)
            wire=gemini_transport_schema(schema)
            self.assertEqual(wire['enum'],[value]); self.assertEqual(schema,original)
            for candidate in ('NORMALIZED_QUERY','CURRENT_QUERY',False,True,3,4,None):
                self.assertEqual(Draft202012Validator(schema).is_valid(candidate),Draft202012Validator(wire).is_valid(candidate))

    def test_actual_researcher_fact_field_and_named_const_property(self):
        schema=ResearcherResult.model_json_schema(); wire=gemini_transport_schema(schema)
        field=wire['$defs']['FactCandidate']['properties']['span_source']
        self.assertEqual(field['enum'],['NORMALIZED_QUERY'])
        self.assertEqual(schema['$defs']['FactCandidate']['properties']['span_source']['const'],'NORMALIZED_QUERY')
        named={'type':'object','properties':{'const':{'type':'string','const':'fixed'}}}
        self.assertEqual(gemini_transport_schema(named)['properties']['const']['enum'],['fixed'])

    def test_output_with_wrong_constant_is_not_repaired_to_the_default(self):
        try: from google import genai
        except ImportError: self.skipTest('Optional Google SDK is not installed')
        sdk=Mock(); sdk.__enter__=Mock(return_value=sdk); sdk.__exit__=Mock(return_value=False)
        sdk.models.generate_content.return_value=SimpleNamespace(text=json.dumps({'span_source':'CURRENT_QUERY'}),candidates=[])
        schema={'type':'object','properties':{'span_source':{'type':'string','const':'NORMALIZED_QUERY'}},'required':['span_source']}
        with patch('google.genai.Client',return_value=sdk),patch('vn_labor_online.providers.get_gemini_limiter') as gate:
            gate.return_value.acquire.return_value=0
            with self.assertRaises(StructuredOutputError) as error:
                GeminiProvider('test','dummy').structured('system','user',schema)
        self.assertEqual(review_error_code(error.exception),'GEMINI_SCHEMA_VALIDATION_FAILED_CONST')
        self.assertEqual(sdk.models.generate_content.call_args.kwargs['config'].response_json_schema['properties']['span_source']['enum'],['NORMALIZED_QUERY'])


if __name__=='__main__': unittest.main()
