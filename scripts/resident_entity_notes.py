"""Explicit immutable bridge notes; receipts, readback and events jointly prove them."""
from copy import deepcopy
from datetime import datetime
import re

import continuous_navigation as nav
from command_preconditions import ACTOR_STATE, integer, point, valid_execution
from foundation_agent import valid_world_instance
from postcard_text import valid_postcard_text

ACTION = 'append_entity_note'
CAPABILITY = 'entity-notes-v1'
STARTUP = 'entity-note-startup'
NOTE_FIELDS = {'noteId', 'entityId', 'authorActorId', 'operatorId', 'commandId', 'text', 'replyToNoteId',
               'capabilityVersion', 'stateVersion', 'eventCursor', 'sharedAtUtc', 'position', 'inventoryWood'}
TARGET_FIELDS = {'entityId', 'definitionId', 'definitionVersion', 'rulesVersion', 'ownerActorId', 'position', 'embodiedWood'}


class StartupBudget(RuntimeError):
    """An unbound task exhausted its original budget without inventing an identity."""


def new_startup(spec, endpoint, now):
    return {'schemaVersion': 1, 'kind': STARTUP, 'spec': deepcopy(spec), 'endpoint': deepcopy(endpoint),
            'startedEpoch': now, 'used': {'queries': 0, 'seconds': 0}, 'queries': []}


def valid_queries(log, count):
    return (isinstance(log, list) and integer(count) and len(log) == count
            and all(isinstance(q, dict) and set(q) == {'index', 'kind'} and type(q['index']) is int
                    and q['index'] == i and q['kind'] in ('observation', 'receipt', 'entity_note_event')
                    for i, q in enumerate(log, 1)))


def validate_startup(value, spec, endpoint):
    if (not isinstance(value, dict) or set(value) != {'schemaVersion', 'kind', 'spec', 'endpoint', 'startedEpoch', 'used', 'queries'}
            or type(value['schemaVersion']) is not int or value['schemaVersion'] != 1 or value['kind'] != STARTUP
            or not equal(value['spec'], spec) or not equal(value['endpoint'], endpoint)
            or not nav.finite(value['startedEpoch']) or value['startedEpoch'] <= 0
            or not isinstance(value['used'], dict) or set(value['used']) != {'queries', 'seconds'}
            or not valid_queries(value['queries'], value['used'].get('queries'))
            or value['used']['queries'] > spec['budgets']['queries']
            or not nav.finite(value['used'].get('seconds')) or value['used']['seconds'] < 0
            or any(q['kind'] != 'observation' for q in value['queries'])):
        raise ValueError('Original entity note startup binding or budget is damaged')


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) is not None


def note_id(value):
    return isinstance(value, str) and re.fullmatch(r'n[0-9a-f]{32}', value) is not None


def equal(left, right):
    """Preserve JSON types, including the distinction between counts and booleans."""
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(equal(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    if type(left) in (int, float) and type(right) in (int, float):
        return nav.finite(left) and nav.finite(right) and left == right
    return type(left) is type(right) and left == right


def valid_goal(value):
    return (isinstance(value, dict) and set(value) == {'entityId', 'text', 'replyToNoteId'}
            and identifier(value['entityId']) and valid_postcard_text(value['text'])
            and (value['replyToNoteId'] is None or note_id(value['replyToNoteId'])))


def valid_target(target):
    return (isinstance(target, dict) and set(target) == TARGET_FIELDS and identifier(target['entityId'])
            and target['definitionId'] == 'bridge' and type(target['definitionVersion']) is int
            and target['definitionVersion'] == 1 and target['rulesVersion'] == 'r10'
            and identifier(target['ownerActorId']) and point(target['position'])
            and type(target['embodiedWood']) is int and target['embodiedWood'] == 6)


def valid_note(note):
    if (not isinstance(note, dict) or set(note) != NOTE_FIELDS or not note_id(note['noteId'])
            or not all(identifier(note[k]) for k in ('entityId', 'authorActorId', 'operatorId', 'commandId'))
            or not valid_postcard_text(note['text']) or not (note['replyToNoteId'] is None or note_id(note['replyToNoteId']))
            or type(note['capabilityVersion']) is not int or note['capabilityVersion'] != 1
            or not integer(note['stateVersion']) or not integer(note['eventCursor']) or note['eventCursor'] < 1
            or not point(note['position']) or not integer(note['inventoryWood']) or note['inventoryWood'] > 12
            or not isinstance(note['sharedAtUtc'], str)):
        return False
    try:
        return datetime.fromisoformat(note['sharedAtUtc'].replace('Z', '+00:00')).utcoffset() is not None
    except ValueError:
        return False


def supported(observed):
    cap = observed.get('entityNotes')
    if (observed.get('rulesVersion') != 'r10'
            or observed.get('world', {}).get('scenarioId') != 'wilderness-material-access-v1'
            or not valid_world_instance(observed.get('world', {}).get('instanceId'))
            or not isinstance(cap, dict) or cap.get('capability') != CAPABILITY
            or any(type(cap.get(k)) is not int or cap[k] != v for k, v in
                   {'version': 1, 'maxTextScalars': 160, 'maxPerOperator': 2, 'maxTotal': 6}.items())
            or type(cap.get('reach')) not in (int, float) or cap['reach'] != 1.6
            or not valid_target(cap.get('target')) or not integer(cap.get('selfCount')) or cap['selfCount'] > 2
            or not integer(cap.get('totalCount')) or cap['totalCount'] > 6
            or not isinstance(cap.get('notes'), list) or cap['totalCount'] != len(cap['notes'])):
        return False
    notes = cap['notes']
    return (all(valid_note(n) and n['entityId'] == cap['target']['entityId'] for n in notes)
            and len({n['noteId'] for n in notes}) == len(notes)
            and [n['eventCursor'] for n in notes] == sorted({n['eventCursor'] for n in notes})
            and all(n['replyToNoteId'] is None or any(r['noteId'] == n['replyToNoteId'] and r['eventCursor'] < n['eventCursor']
                                                   for r in notes) for n in notes))


def reference(observed, goal):
    key = goal['entityNote']['replyToNoteId']
    return next((deepcopy(n) for n in observed['entityNotes']['notes'] if n['noteId'] == key), None)


def validate_goal(observed, goal):
    if (not supported(observed) or goal['entityNote']['entityId'] != observed['entityNotes']['target']['entityId']
            or not equal(goal['target'], observed['entityNotes']['target']['position'])
            or goal['entityNote']['replyToNoteId'] is not None and reference(observed, goal) is None):
        raise ValueError('Entity note requires the adopted original bridge and a readable original reference')


def binding(observed):
    identity = observed.get('identity', {})
    if identity.get('actorId') != observed['self']['actorId'] or not identifier(identity.get('operatorId')):
        raise ValueError('Entity note requires an authenticated original actor and operator')
    return {'version': 1, 'worldInstanceId': observed['world']['instanceId'], 'actorId': identity['actorId'],
            'operatorId': identity['operatorId'], 'target': deepcopy(observed['entityNotes']['target'])}


def ready(observed, goal, original, initial):
    if not supported(observed) or not equal(observed['entityNotes']['target'], original['target']):
        return False
    identity = observed.get('identity', {})
    if identity.get('actorId') != original['actorId'] or identity.get('operatorId') != original['operatorId']:
        return False
    return (observed['world']['instanceId'] == original['worldInstanceId']
            and (goal['entityNote']['replyToNoteId'] is None or reference(observed, goal) is not None
                 and equal(reference(observed, goal), reference(initial, goal))))


def plan(observed, goal):
    empty = {'reason': None, 'cells': [], 'bridges': 0, 'wood': 0, 'commands': None, 'nextAction': None}
    if not supported(observed):
        return {**empty, 'reason': 'entity_notes_unavailable'}
    try:
        validate_goal(observed, goal)
    except ValueError:
        return {**empty, 'reason': 'entity_note_target_or_reference_unavailable'}
    cap = observed['entityNotes']
    if cap['selfCount'] >= 2 or cap['totalCount'] >= 6:
        return {**empty, 'reason': 'entity_note_limit_reached'}
    route = nav.route_info(observed, goal['target'], False, False)
    if route['reason']:
        return route
    if nav.near(observed['self']['position'], goal['target']):
        return {**empty, 'commands': 1, 'nextAction': {'type': ACTION, **deepcopy(goal['entityNote'])},
                'nextReason': '在原桥发表任务授权的原文和引用'}
    return {**route, 'commands': route['commands'] + 1, 'nextReason': '前往共同手记登记的原桥'}


def before(observed, goal, original, initial):
    if not ready(observed, goal, original, initial):
        raise ValueError('Entity note capability or identity changed before submission')
    return {**deepcopy(original), 'position': deepcopy(observed['self']['position']),
            'inventoryWood': observed['self']['inventory']['wood'], 'reference': reference(observed, goal)}


def valid_before(value):
    return (isinstance(value, dict) and set(value) == {'version', 'worldInstanceId', 'actorId', 'operatorId',
                                                     'target', 'position', 'inventoryWood', 'reference'}
            and type(value['version']) is int and value['version'] == 1
            and valid_world_instance(value['worldInstanceId']) and identifier(value['actorId'])
            and identifier(value['operatorId']) and valid_target(value['target']) and point(value['position'])
            and nav.distance(value['position'], value['target']['position']) <= 1.6
            and integer(value['inventoryWood']) and value['inventoryWood'] <= 12
            and (value['reference'] is None or valid_note(value['reference'])
                 and value['reference']['entityId'] == value['target']['entityId']))


def readback(observed, original, note):
    if (not supported(observed) or observed['world']['instanceId'] != original['worldInstanceId']
            or not equal(observed['entityNotes']['target'], original['target'])
            or not any(equal(e, original['target']) for e in observed.get('entities', []))
            or observed.get('identity', {}).get('actorId') != original['actorId']
            or observed.get('identity', {}).get('operatorId') != original['operatorId']
            or observed['self']['actorId'] != original['actorId'] or observed['stateVersion'] < note.get('stateVersion', 0)
            or original['reference'] is not None and not any(equal(n, original['reference']) for n in observed['entityNotes']['notes'])):
        return None
    matches = [n for n in observed['entityNotes']['notes'] if n['noteId'] == note.get('noteId')]
    if len(matches) != 1:
        return None
    return {'worldInstanceId': observed['world']['instanceId'], 'target': deepcopy(observed['entityNotes']['target']),
            'note': deepcopy(matches[0])}


def evidence(receipt, intent, snapshot, read, event):
    if (not valid_before(snapshot) or not isinstance(receipt, dict) or not isinstance(read, dict)
            or type(receipt.get('schemaVersion')) is not int or receipt['schemaVersion'] != 1
            or receipt.get('rulesVersion') != 'r10' or intent.get('rulesVersion') != 'r10'
            or intent.get('preconditionMode') != ACTOR_STATE or not valid_execution(receipt, intent)
            or receipt.get('commandId') != intent.get('commandId') or not isinstance(receipt.get('identity'), dict)
            or receipt['identity'].get('actorId') != snapshot['actorId']
            or receipt['identity'].get('operatorId') != snapshot['operatorId']
            or not isinstance(receipt.get('result'), dict) or receipt['result'].get('action') != ACTION):
        return None
    note = {k: v for k, v in receipt['result'].items() if k != 'action'}
    action = intent.get('action', {})
    if (not valid_note(note) or set(action) != {'type', 'entityId', 'text', 'replyToNoteId'}
            or action.get('type') != ACTION or not valid_goal({k: v for k, v in action.items() if k != 'type'})
            or note['entityId'] != snapshot['target']['entityId']
            or any(note[k] != action[k] for k in ('entityId', 'text', 'replyToNoteId'))
            or note['authorActorId'] != snapshot['actorId'] or note['operatorId'] != snapshot['operatorId']
            or note['commandId'] != intent['commandId'] or not equal(note['position'], snapshot['position'])
            or note['inventoryWood'] != snapshot['inventoryWood']
            or not integer(receipt.get('eventCursor')) or note['eventCursor'] != receipt['eventCursor']
            or note['stateVersion'] != receipt['stateVersion']
            or not equal(read, {'worldInstanceId': snapshot['worldInstanceId'], 'target': snapshot['target'], 'note': note})
            or not isinstance(event, dict) or not valid_note({k: event.get(k) for k in NOTE_FIELDS})
            or not integer(event.get('seq'))
            or not equal(event, {**note, 'type': 'entityNoteAppended', 'seq': note['eventCursor'], 'actorId': note['authorActorId']})
            or (action['replyToNoteId'] is None) != (snapshot['reference'] is None)
            or snapshot['reference'] is not None and action['replyToNoteId'] != snapshot['reference']['noteId']):
        return None
    return {'worldInstanceId': snapshot['worldInstanceId'], **deepcopy(note)}


def validate_saved(state):
    """Validate the complete note task before network or chooser calls, even on replay."""
    try:
        _validate_saved(state)
    except (KeyError, TypeError, IndexError, AttributeError):
        raise ValueError('Original entity note state is incomplete or damaged') from None


def _validate_saved(state):
    saved, mission, facts = state['_state'], state['mission'], state['facts']
    spec = saved['spec']
    uses = any('entityNote' in g for g in spec['goals'])
    pending = saved.get('pending')
    if not uses:
        if ('entityNotesBinding' in saved or 'entityNoteProof' in saved or facts.get('entityNoteShared')
                or facts.get('entityNote') is not None or pending and pending.get('request', {}).get('action', {}).get('type') == ACTION):
            raise ValueError('Entity note authority cannot be added to an old task')
        return
    original, base, initial = saved['entityNotesBinding'], saved['binding'], saved['initial']
    goal, limits, used = mission['goal'], state['budget']['limits'], state['budget']['used']
    if (not isinstance(original, dict) or set(original) != {'version', 'worldInstanceId', 'actorId', 'operatorId', 'target'}
            or type(original['version']) is not int or original['version'] != 1
            or not valid_world_instance(original['worldInstanceId']) or not identifier(original['actorId'])
            or not identifier(original['operatorId']) or not valid_target(original['target'])
            or original['worldInstanceId'] != base.get('instanceId') or mission['worldInstanceId'] != base.get('instanceId')
            or original['actorId'] != base.get('actorId') or mission['actorId'] != base.get('actorId')
            or initial['self'].get('operatorId') != original['operatorId']
            or base.get('rulesVersion') != 'r10' or mission['rulesVersion'] != 'r10'
            or base.get('preconditionMode') != ACTOR_STATE or mission.get('preconditionMode') != ACTOR_STATE
            or mission.get('allowEntityNotes') is not True or spec.get('allowEntityNotes') is not True
            or any(mission.get(k, False) is not spec.get(k, False) for k in
                   ('allowBuild', 'allowGather', 'allowTransfer', 'allowMaterialAccess'))
            or not equal(limits, spec['budgets']) or any(type(v) is not int for v in limits.values()) or set(used) != set(limits)
            or any(not integer(used[k]) or used[k] > limits[k] for k in ('commands', 'wood', 'modelCalls', 'queries'))
            or used['wood'] != 0 or not nav.finite(used['seconds']) or used['seconds'] < 0
            or not nav.finite(saved['startedEpoch']) or saved['startedEpoch'] <= 0
            or used['commands'] != len(state['steps']) or not point(mission['origin'])
            or not valid_queries(saved.get('entityNoteQueries'), used.get('queries')) or used['queries'] < 1
            or not equal(mission['origin'], initial['self']['position'])
            or initial['self']['actorId'] != original['actorId'] or initial['world']['instanceId'] != original['worldInstanceId']
            or not supported(initial) or not equal(initial['entityNotes']['target'], original['target'])
            or goal is not None and (goal not in spec['goals'] or not valid_goal(goal.get('entityNote')))
            or type(facts.get('entityNoteShared')) is not bool):
        raise ValueError('Original entity note binding, authorization or budget is damaged')
    for candidate in spec['goals']:
        validate_goal(initial, candidate)
    identifiers = []
    for index, step in enumerate(state['steps'], 1):
        if (not integer(step.get('index')) or step['index'] != index or not identifier(step.get('commandId'))
                or step.get('preconditionMode') != ACTOR_STATE or not integer(step.get('expectedStateVersion'))
                or step.get('status') not in ('committed', 'rejected', 'unknown', 'pending')
                or step.get('action', {}).get('type') not in ('walk', ACTION)):
            raise ValueError('Original entity note command accounting is damaged')
        identifiers.append(step['commandId'])
        if step['action']['type'] == ACTION and (goal is None or not equal(step['action'], {'type': ACTION, **goal['entityNote']})):
            raise ValueError('Original entity note text or reference changed')
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Original entity note commands are duplicated')
    if goal is not None and (state['decision'] is None or state['decision'].get('goalId') != goal['id'] or used['modelCalls'] != 1):
        raise ValueError('Original entity note choice is damaged')
    if pending is not None:
        request, step = pending['request'], state['steps'][-1]
        if (request.get('rulesVersion') != 'r10' or type(request.get('schemaVersion')) is not int or request['schemaVersion'] != 1
                or request.get('commandId') != step['commandId'] or not equal(request.get('action'), step['action'])
                or request.get('preconditionMode') != ACTOR_STATE or request.get('expectedStateVersion') != step['expectedStateVersion']
                or type(pending.get('woodCost')) is not int or pending['woodCost'] != 0
                or step['status'] not in ('pending', 'unknown')):
            raise ValueError('Original entity note pending command is damaged')
        if request['action']['type'] == ACTION:
            before = pending['entityNoteBefore']
            if (not valid_before(before) or facts['entityNoteShared']
                    or any(not equal(before.get(k), v) for k, v in original.items())
                    or not equal(before['position'], step['position']) or before['inventoryWood'] != step['inventoryWood']
                    or not equal(before['reference'], reference(initial, goal))):
                raise ValueError('Original entity note before facts are damaged')
        elif (set(request['action']) != {'type', 'to'} or not point(request['action']['to'])
              or not equal(pending['walkBefore']['position'], step['position'])):
            raise ValueError('Original entity note approach is damaged')
    committed = [s for s in state['steps'] if s['action']['type'] == ACTION and s['status'] == 'committed']
    if facts['entityNoteShared']:
        proof = saved['entityNoteProof']
        record = evidence(proof['receipt'], proof['request'], proof['before'], proof['readback'], proof['event'])
        if (record is None or not equal(record, facts['entityNote']) or len(committed) != 1
                or not equal(committed[0].get('entityNoteEvidence'), record)
                or committed[0]['commandId'] != record['commandId']
                or any(not equal(proof['before'].get(k), v) for k, v in original.items())
                or not equal(proof['request']['action'], {'type': ACTION, **goal['entityNote']})
                or not equal(proof['before']['reference'], reference(initial, goal))):
            raise ValueError('Original entity note completion evidence is damaged')
    elif facts.get('entityNote') is not None or committed or saved.get('entityNoteProof') is not None:
        raise ValueError('Unconfirmed entity note cannot carry completion facts')
