import flask
import json
import requests

from flask import Response

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
# TODO: HEALTH service not GET for validate!
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
            json_result['issue'].extend(result.get('issue', []))
        except requests.exceptions.ConnectionError as error:
            json_result['issue'].append(generate_connection_warning(error))
        except requests.exceptions.HTTPError as error:
            json_result['issue'].append(generate_http_warning(error))
    json_result['issue'].extend(warnings)
    return Response(json.dumps(json_result, indent=2), mimetype='application/json')


def preprocess_json(data):
    warnings = list()
    idx = 0
    should_validate = True
    try:
        data = json.loads(data)
        entries = data.get('entry')
        if entries is None or builtins.type(entries) is not list or len(entries) == 0:
            warnings.append(generate_empty_bundle_warning())
            should_validate = False
            return json.dumps(data, indent=4), warnings, should_validate
        for entry in data['entry']:
            profile_assignment_warnings = assign_profile_to_structure_definition_json(entry, idx)
            warnings.extend(profile_assignment_warnings)
            idx += 1
    except JSONDecodeError as e:
        warnings.append(generate_parsing_warning(e.msg))
        should_validate = False
    except ParsingKeyError as pke:
        warnings.append(generate_preprocessing_warning(pke))
        should_validate = False
    return json.dumps(data, indent=4), warnings, should_validate


def assign_profile_to_structure_definition_json(entry, idx):
    warnings = []
    try:
        instance = rec_get(entry, 'resource')
        resource_type = rec_get(instance, 'resourceType')
        print(f"\tProcessing instance of type {resource_type}: ", end='')
        if resource_type in resource_types:
            if resource_type == 'Observation':
                observation_warnings = assign_profile_to_observation_instance_json(instance, idx)
                warnings.extend(observation_warnings)
            else:
                assign_profile_to_instance_json(instance, resource_type)
        else:
            # Only process instances of relevant types
            print(f"Assigned no profile")
            pass
    except ParsingKeyError as pke:
        warnings.append(generate_preprocessing_warning(pke))
    return warnings


def assign_profile_to_instance_json(instance, resource_type):
    profile = validation_mapping[resource_type]
    instance['meta']['profile'] = [profile]
    print(f"Assigned profile {profile}")


def assign_profile_to_observation_instance_json(observation_instance, idx):
    observation_warnings = []
    code = None
    for coding in rec_get(observation_instance, 'code', 'coding'):
        if coding.get('system') == 'http://loinc.org':
            code = coding.get('code')
            break
    profile = validation_mapping.get('Observation').get(code)
    if profile is not None:
        observation_instance['meta']['profile'] = [profile]
        print(f"Assigned profile {profile}")
    else:
        print(f"Assigned no profile to instance of Observation")
        observation_warnings.append(generate_mapping_warning(idx=idx, code=code,
                                                             system='http://loinc.org',
                                                             profile=rec_get(observation_instance, 'meta', 'profile', 0)
                                                             ))
    return observation_warnings


preprocessing = {'application/json': preprocess_json}


def generate_mapping_warning(idx, code, system, profile):
    return {'severity': typed_issue_severity['mapping_issue'],
            'code': 'not-supported',
            'diagnostics': f'VALIDATION_PROFILE_MAPPING: Observation.code.coding:loinc: no matching profile for code '
                           f'{code} with system {system} and profile {profile}',
            'location': [f'Bundle.entry[{idx}].resource.ofType(Observation).code.coding[0]']}


def generate_parsing_warning(msg):
    # FHIR Marshal doesn't seem to return error location in case of a parsing error
    return {'severity': typed_issue_severity['parsing_issue'],
            'code': 'processing',
            'diagnostics': f'VALIDATION_PROFILE_MAPPING: Data could not be parsed: {msg}'}


def generate_preprocessing_warning(parsing_key_error):
    return {'severity': typed_issue_severity['parsing_issue'],
            'code': 'processing',
            'diagnostics': f'VALIDATION_PROFILE_MAPPING: Data could not be parsed: {parsing_key_error.msg}',
            'location': [parsing_key_error.str_loc]}


def generate_empty_bundle_warning():
    return {'severity': typed_issue_severity['empty_bundle_issue'],
            'code': 'processing',
            'diagnostics': f'VALIDATION_PROFILE_MAPPING: No entries in bundle. Thus no instances were validated.',
            'location': [f'Bundle.entry']}


def generate_connection_warning(conn_error):
    return {'severity': 'error',
            'code': 'timeout',
            'diagnostics': f"VALIDATION_PROFILE_MAPPING: {str(conn_error)}"}


def generate_http_warning(http_error):
    return {'severity': 'error',
            'code': 'processing',
            'diagnostics': f"VALIDATION_PROFILE_MAPPING: {str(http_error)}"}


def validate_with_marshal(data, content_type):
    response = requests.post(url=v_url, headers={'Content-Type': content_type}, data=data)
    if response.status_code != 200:
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        print(f"Data:\n{data}")
        raise requests.exceptions.HTTPError(f"Request failed with status code {response.status_code}:\n{response.text}")
    return response.json()
