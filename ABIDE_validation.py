import xml

import flask
import os
import json
import xmltodict
import requests
import glob
import variables
import builtins
import os

from json import JSONDecodeError
from rec_get import rec_get, ParsingKeyError

app = flask.Flask(__name__, static_folder='')
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
validation_mapping = json.load(open(os.path.join('maps', 'validation_mapping.json')))
resource_types = validation_mapping.keys()
v_url = os.getenv('VALIDATOR_URL')

# ======================================================================================================================
# Supposed to be accessible via list indices corresponding to log levels in variable file
issue_severity = ['information', 'warning', 'error', 'fatal']


def assign_severities():
    return {'mapping_issue': issue_severity[variables.mapping_issue],
            'parsing_issue': issue_severity[variables.parsing_issue],
            'empty_bundle_issue': issue_severity[variables.empty_bundle_issue]}


typed_issue_severity = assign_severities()


# ======================================================================================================================
# Endpoint
@app.route("/validate", methods=['GET', 'POST'])
def validate():
    if flask.request.method == 'GET':
        return ""
    data = flask.request.data
    content_type = flask.request.headers['Content-Type']
    print('Preprocessing data ...')
    # TODO: Check basic data validity
    processed_data, warnings, should_validate = preprocessing[content_type](data)
    print('Validating data ...')
    json_result = {'resourceType': 'OperationOutcome',
                   'issue': []}
    if should_validate:
        try:
            result = validate_with_marshal(processed_data, content_type)
            json_result['issue'].extend(json.loads(result.text).get('issue', []))
        except requests.exceptions.ConnectionError as e:
            json_result['issue'].append(generate_connection_warning(e))
    json_result['issue'].extend(warnings)
    return json.dumps(json_result, indent=2)


def preprocess_json(data):
    warnings = list()
    idx = 0
    # status indicates whether validation should occur (0 fine, otherwise not)
    should_validate = True
    try:
        data = json.loads(data)
        entries = data.get('entry')
        if entries is None or builtins.type(entries) is not list or len(entries) == 0:
            warnings.append(generate_empty_bundle_warning())
            should_validate = False
            return json.dumps(data, indent=4), warnings, should_validate
        for entry in data['entry']:
            try:
                instance = rec_get(entry, 'resource') # entry['resource']
                type = rec_get(instance, 'resourceType') # instance['resourceType']
                if type in resource_types:
                    if type == 'Observation':
                        code = rec_get(instance, 'code', 'coding', 0, 'code') # instance['code']['coding'][0]['code']
                        profile = validation_mapping.get('Observation').get(code)
                        if profile is not None:
                            instance['meta']['profile'] = [profile]
                        else:
                            warnings.append(generate_mapping_warning(idx=idx, code=code,
                                                                     system=rec_get(instance, 'code', 'coding', 0, 'system'),
                                                                     profile=rec_get(instance, 'meta', 'profile', 0)))
                    else:
                        entry['full_url'] = validation_mapping[type]
                else:
                    # Only process instances of relevant types
                    pass
            except ParsingKeyError as pke:
                warnings.append(generate_preprocessing_warning(pke))
            idx += 1
    except JSONDecodeError as e:
        warnings.append(generate_parsing_warning(e.msg))
        should_validate = False
    except ParsingKeyError as pke:
        warnings.append(generate_preprocessing_warning(pke))
        should_validate = False
    return json.dumps(data, indent=4), warnings, should_validate


def preprocess_xml(data):
    warnings = list()
    idx = 0
    try:
        data = xmltodict.parse(data)
        entries = data.get('Bundle').get('entry')
        if entries is None or builtins.type(entries) is not list or len(entries) == 0:
            warnings.append(generate_empty_bundle_warning())
            return xmltodict.unparse(data), warnings
        for entry in entries:
            try:
                if 'Condition' in entry:
                    entry['fullUrl']['@value'] = validation_mapping['Condition']
                elif 'Observation' in entry:
                    instance = rec_get(entry, 'Observation') # entry['Observation']
                    code = rec_get(instance, 'code', 'coding', 0, 'code', '@value') # instance['code']['coding'][0]['code']['@value']
                    profile = validation_mapping['Observation'][code]
                    if profile is not None:
                        instance['meta'] = [{'profile': {'@value': profile}}]
                    else:
                        warnings.append(generate_mapping_warning(idx=idx, code=code,
                                                                 system=rec_get(instance, 'code', 'coding', 0, 'system', '@value'),
                                                                 profile=rec_get(instance, 'meta', 'profile', 0, '@value')))
                elif 'Medication' in entry:
                    entry['full_url']['@value'] = validation_mapping['Medication']
                elif 'MedicationAdministration' in entry:
                    entry['full_url']['@value'] = validation_mapping['MedicationAdministration']
                elif 'MedicationStatement' in entry:
                    entry['full_url']['@value'] = validation_mapping['MedicationStatement']
                elif 'Procedure' in entry:
                    entry['full_url']['@value'] = validation_mapping['Procedure']
                else:
                    # Only process instances of relevant types
                    pass
            except ParsingKeyError as pke:
                warnings.append(generate_preprocessing_warning(pke))
            idx += 1
    except xml.parsers.expat.ExpatError as e:
        warnings.append(generate_parsing_warning(str(e)))
    except ParsingKeyError as pke:
        warnings.append(generate_preprocessing_warning(pke))
    return xmltodict.unparse(data), warnings


preprocessing = {'application/json': preprocess_json,
                 'application/xml': preprocess_xml}


def generate_mapping_warning(idx, code, system, profile):
    return {'severity': typed_issue_severity['mapping_issue'],
            'code': 'not-supported',
            'diagnostics': f'Observation.code.coding:loinc: no matching profile for code {code} with system {system} and profile {profile}',
            'location': [f'Bundle.entry[{idx}].resource.ofType(Observation).code.coding[0]']}


def generate_parsing_warning(msg):
    # FHIR Marshal doesn't seem to return error location in case of a parsing error
    return {'severity': typed_issue_severity['parsing_issue'],
            'code': 'processing',
            'diagnostics': f'Data could not be parsed: {msg}'}


def generate_preprocessing_warning(parsing_key_error):
    return {'severity': typed_issue_severity['parsing_issue'],
            'code': 'processing',
            'diagnostics': f'Data could not be parsed: {parsing_key_error.msg}',
            'location': [parsing_key_error.str_loc]}


def generate_empty_bundle_warning():
    return {'severity': typed_issue_severity['empty_bundle_issue'],
            'code': 'processing',
            'diagnostics': f'No entries in bundle. Thus no instances were validated.',
            'location': [f'Bundle.entry']}


def generate_connection_warning(conn_error):
    return {'severity': 'error',
            'code': 'timeout',
            'diagnostics': str(conn_error)}


def validate_with_marshal(data, content_type):
    response = requests.post(url=v_url + '/validate', headers={'Content-Type': content_type}, data=data)
    return response


def upload_validation_profiles():
    print(f'Uploading profiles to {variables.s_url} ...')
    for profile in glob.glob(os.path.join('profiles', '*', '*.xml'), recursive=True):
        data = open(profile).read()
        json_data = xmltodict.parse(data)
        url = variables.s_url + 'StructureDefinition/' + f'{json_data["StructureDefinition"]["id"]["@value"]}'
        response = requests.put(url=url, headers={'Content-Type': 'application/xml'}, data=data)
        print(f'Send profile {profile}: {response.status_code}')
    for profile in glob.glob(os.path.join('profiles', '*', '*.json'), recursive=True):
        data = open(profile).read()
        json_data = json.loads(data)
        try:
            url = variables.s_url + 'StructureDefinition/' + f'{json_data["id"]}'
        except KeyError:
            print(profile)
        response = requests.put(url=url, headers={'Content-Type': 'application/json'}, data=data)
        print(f'Send profile {profile}: {response.status_code}')


if __name__ == "__main__":
    # Upload validation profiles to server
    upload_validation_profiles()
    # app.run()
