"""Read a bounded RDF/XML vocabulary, without executing OWL or importing rules.

This is a structural audit and an explicit lexical crosswalk, not an OWL reasoner.
Unmapped concepts, sample ABox rules and issue-factor relations never become facts.
"""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET

RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDFS = 'http://www.w3.org/2000/01/rdf-schema#'
OWL = 'http://www.w3.org/2002/07/owl#'
SKOS = 'http://www.w3.org/2004/02/skos/core#'
BASE = 'https://example.org/legalgraphrag-vn/ontology#'
ABOUT, RESOURCE = f'{{{RDF}}}about', f'{{{RDF}}}resource'

# Coarse OFFLINE labels are deliberately kept. These mappings do not invent
# actor-specific subissues, mandatory questions or evidence-slot requirements.
ISSUE_CROSSWALK = {
    'LaborContract': ['CONTRACT_TYPE', 'CONTRACT_FORM', 'CONTRACT_RENEWAL',
        'CONTRACT_AMENDMENT', 'CONTRACT_AUTO_CONVERSION', 'PROBATION_DURATION',
        'PROBATION_PAY', 'PROBATION_END', 'EMPLOYMENT_TRANSFER'],
    'Termination': ['UNILATERAL_TERMINATION', 'UNLAWFUL_TERMINATION',
        'NOTICE_PERIOD', 'SEVERANCE_PAY', 'JOB_LOSS_ALLOWANCE'],
    'Discipline': ['DISCIPLINE_PROCEDURE', 'DISCIPLINE_TIME_LIMIT', 'DISMISSAL',
        'MATERIAL_LIABILITY'],
    'Wage': ['LATE_WAGE_PAYMENT', 'WAGE_ARREARS', 'WAGE_DEDUCTION',
        'MINIMUM_WAGE', 'BONUS', 'OVERTIME_PAY'],
    'WorkingTime': ['WORKING_HOURS', 'REST_TIME', 'ANNUAL_LEAVE', 'OVERTIME_LIMIT'],
    'SocialInsurance': ['SOCIAL_INSURANCE_CONTRIBUTION', 'SOCIAL_INSURANCE_BENEFIT'],
    'OccupationalSafety': ['WORK_ACCIDENT', 'OCCUPATIONAL_DISEASE', 'WORKPLACE_SAFETY'],
    'TradeUnion': ['REPRESENTATION'],
    'CollectiveRelations': ['COLLECTIVE_BARGAINING', 'COLLECTIVE_AGREEMENT', 'STRIKE'],
    'DisputeResolution': ['INDIVIDUAL_DISPUTE', 'COLLECTIVE_DISPUTE',
        'COURT_JURISDICTION', 'MEDIATION'],
    'TrainingCost': ['TRAINING_COST'],
    'MinorWorker': ['MINOR_WORKERS'],
    'FemaleWorker': ['MATERNITY_PROTECTION', 'WORKPLACE_HARASSMENT'],
    # PROTECTED_EMPLOYEE is intentionally not mapped: its broad aliases such as
    # "đang điều trị" do not by themselves identify a maternity/labour question.
}


def read_vocabulary(path: Path) -> tuple[dict, dict]:
    raw = path.read_bytes()
    if len(raw) > 4_000_000:
        raise ValueError('Ontology exceeds the 4 MB vocabulary limit')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('DTD/entities are not permitted in a vocabulary')
    root = ET.fromstring(raw)
    if root.tag != f'{{{RDF}}}RDF':
        raise ValueError('Expected RDF/XML root')
    entities = {}
    duplicates = []
    for entry in root:
        iri = entry.get(ABOUT)
        if not iri:
            continue  # anonymous restrictions are audited, never lexical entries
        if iri in entities:
            duplicates.append(iri)
        # RDF allows multiple descriptions of the same subject; merge triples.
        entities.setdefault(iri, []).extend(list(entry))
        if entry.tag != f'{{{RDF}}}Description':
            entities[iri].append(ET.Element(f'{{{RDF}}}type', {RESOURCE: entry.tag[1:].replace('}', '')}))
    counts = Counter()
    samples = []
    for iri, triples in entities.items():
        counts.update({x.get(RESOURCE, '').rsplit('#', 1)[-1]
                       for x in triples if x.tag == f'{{{RDF}}}type'})
        if any(x.tag == f'{{{BASE}}}sampleOnly' and (x.text or '').strip().lower() == 'true'
               for x in triples):
            samples.append(iri)
    references = {x.get(RESOURCE) for x in root.iter() if x.get(RESOURCE, '').startswith(BASE)}
    undefined = sorted(references - entities.keys())
    versions = sorted({x.text.strip() for x in root.iter()
                       if x.tag == f'{{{OWL}}}versionInfo' and x.text})
    version_iris = sorted({x.get(RESOURCE) for x in root.iter()
                           if x.tag == f'{{{OWL}}}versionIRI' and x.get(RESOURCE)})
    warnings = []
    if any('example.org' in iri for iri in entities):
        warnings.append('EXAMPLE_NAMESPACE_NOT_PROJECT_OWNED')
    if versions and version_iris:
        major = re.match(r'(\d+)\.', versions[0])
        if major and not any('/' + major[1] + '.' in iri for iri in version_iris):
            warnings.append('VERSION_IRI_MISMATCH')
    if undefined:
        warnings.append('UNDEFINED_LOCAL_REFERENCES')
    if samples:
        warnings.append('UNVERIFIED_SAMPLE_ABOX_EXCLUDED')
    return entities, {
        'schema_version': 1, 'sha256': hashlib.sha256(raw).hexdigest(),
        'subjects': len(entities), 'counts_by_type': dict(sorted(counts.items())),
        'version_info': versions, 'version_iris': version_iris,
        'repeated_subject_descriptions': sorted(set(duplicates)),
        'undefined_references': undefined, 'sample_entities_excluded': sorted(samples),
        'warning_codes': warnings, 'audit_scope': 'RDF_XML_STRUCTURE_ONLY_NO_OWL_REASONING',
        'legal_rules_imported': 0, 'authority_verified': False,
    }


def lexical_aliases(path: Path, expected_sha256: str) -> tuple[dict, dict]:
    entities, audit = read_vocabulary(path)
    if audit['sha256'] != expected_sha256:
        raise ValueError('Ontology SHA-256 mismatch; review the new vocabulary before use')
    if audit['undefined_references']:
        raise ValueError('Ontology contains undefined local references')
    aliases = {}
    for issue, suffixes in ISSUE_CROSSWALK.items():
        values = set()
        for suffix in suffixes:
            iri = BASE + 'ISSUE_' + suffix
            triples = entities.get(iri, [])
            if not any(x.tag == f'{{{RDF}}}type' and x.get(RESOURCE) == BASE + 'LegalIssue'
                       for x in triples):
                raise ValueError(f'Mapped ontology issue missing or mistyped: {iri}')
            for triple in triples:
                if triple.tag not in {f'{{{SKOS}}}altLabel', f'{{{SKOS}}}prefLabel'}:
                    continue
                if triple.get('{http://www.w3.org/XML/1998/namespace}lang') != 'vi':
                    continue
                value = ' '.join((triple.text or '').split())
                if 5 <= len(value) <= 160:
                    values.add(value)
        aliases[issue] = sorted(values)
    audit['mapped_issues'] = sum(len(v) for v in ISSUE_CROSSWALK.values())
    audit['aliases'] = sum(len(v) for v in aliases.values())
    audit['usage'] = 'LEXICAL_RETRIEVAL_HINTS_ONLY'
    return aliases, audit
