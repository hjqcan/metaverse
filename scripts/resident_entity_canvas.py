"""Fixed platform paintings, proved by original receipt, immutable edit and event."""
from copy import deepcopy
from datetime import datetime

import continuous_navigation as nav
from command_preconditions import ACTOR_STATE, integer, point, valid_execution
from foundation_agent import valid_world_instance
from mosaic_patch import canonical_patch, COLORS
from resident_entity_notes import equal, identifier, TARGET_FIELDS, valid_queries

ACTION = 'paint_entity_canvas'
STARTUP = 'entity-canvas-startup'
CAPABILITY = 'entity-canvas-v1'
QUERY_KINDS = ('observation', 'receipt', 'entity_canvas_edit', 'entity_canvas_event')
EDIT_FIELDS = {'entityId', 'capabilityVersion', 'authorActorId', 'operatorId', 'commandId', 'baseRevision',
               'revision', 'patch', 'stateVersion', 'eventCursor', 'paintedAtUtc', 'position', 'inventoryWood'}
PALETTE = [dict(zip(('id', 'label', 'hex'), v)) for v in (
    ('blank', '空白', '#F4F0E6'), ('leaf', '叶绿', '#42745B'), ('river', '河蓝', '#477FA3'),
    ('sun', '日黄', '#E4B858'), ('rose', '花红', '#C86A70'), ('ink', '墨色', '#37444D'))]


def valid_goal(value):
    if (not isinstance(value, dict) or set(value) != {'entityId', 'expectedCanvasRevision', 'patch'}
            or not identifier(value['entityId']) or not integer(value['expectedCanvasRevision'])):
        return False
    try:
        canonical_patch(value['patch'])
        return True
    except (ValueError, TypeError, KeyError):
        return False


def action(goal):
    return {'type': ACTION, 'capabilityVersion': 1, **deepcopy(goal['entityCanvas'])}


def valid_target(target):
    return (isinstance(target, dict) and set(target) == TARGET_FIELDS and identifier(target['entityId'])
            and target['definitionId'] == 'platform' and type(target['definitionVersion']) is int
            and target['definitionVersion'] == 1 and target['rulesVersion'] == 'r10'
            and identifier(target['ownerActorId']) and point(target['position'])
            and type(target['embodiedWood']) is int and target['embodiedWood'] == 3)


def valid_adoption(value):
    return (isinstance(value, dict) and set(value) == {'worldInstanceId', 'stateVersion', 'eventCursor'}
            and valid_world_instance(value['worldInstanceId']) and integer(value['stateVersion'])
            and integer(value['eventCursor']) and value['eventCursor'] > 0)


def valid_edit(edit):
    if (not isinstance(edit, dict) or set(edit) != EDIT_FIELDS
            or not all(identifier(edit[k]) for k in ('entityId', 'authorActorId', 'operatorId', 'commandId'))
            or type(edit['capabilityVersion']) is not int or edit['capabilityVersion'] != 1
            or not all(integer(edit[k]) for k in ('baseRevision', 'revision', 'stateVersion', 'eventCursor', 'inventoryWood'))
            or edit['revision'] != edit['baseRevision'] + 1 or edit['eventCursor'] < 1
            or edit['inventoryWood'] > 12 or not point(edit['position']) or not isinstance(edit['paintedAtUtc'], str)):
        return False
    try:
        return (equal(canonical_patch(edit['patch']), edit['patch'])
                and datetime.fromisoformat(edit['paintedAtUtc'].replace('Z', '+00:00')).utcoffset() is not None)
    except (ValueError, TypeError, KeyError):
        return False


def supported(observed):
    cap = observed.get('entityCanvas')
    if (observed.get('rulesVersion') != 'r10'
            or observed.get('world', {}).get('scenarioId') != 'wilderness-material-access-v1'
            or not valid_world_instance(observed.get('world', {}).get('instanceId'))
            or not isinstance(cap, dict) or cap.get('capability') != CAPABILITY
            or any(type(cap.get(k)) is not int or cap[k] != v for k, v in
                   {'version': 1, 'width': 5, 'height': 5, 'maxPatchCells': 8}.items())
            or type(cap.get('reach')) not in (int, float) or cap['reach'] != 1.6
            or cap.get('paintRule') != 'unowned-or-author-v1' or not equal(cap.get('palette'), PALETTE)
            or not valid_target(cap.get('target')) or not valid_adoption(cap.get('adoption'))
            or cap['adoption']['worldInstanceId'] != observed['world']['instanceId']
            or not integer(cap.get('revision')) or not integer(cap.get('editCount')) or cap['revision'] != cap['editCount']
            or not isinstance(cap.get('cells'), list) or len(cap['cells']) != 25
            or not isinstance(cap.get('recentEdits'), list) or len(cap['recentEdits']) != min(cap['revision'], 50)):
        return False
    for i, cell in enumerate(cap['cells']):
        if (not isinstance(cell, dict) or set(cell) != {'x', 'y', 'color', 'authorActorId', 'commandId', 'stateVersion'}
                or type(cell['x']) is not int or type(cell['y']) is not int
                or (cell['x'], cell['y']) != (i % 5, i // 5) or cell['color'] not in COLORS):
            return False
        if cell['authorActorId'] is None:
            if cell['color'] != 'blank' or cell['commandId'] is not None or cell['stateVersion'] is not None:
                return False
        elif (not identifier(cell['authorActorId']) or not identifier(cell['commandId'])
              or not integer(cell['stateVersion']) or cell['stateVersion'] <= cap['adoption']['stateVersion']):
            return False
    edits = cap['recentEdits']
    return (all(valid_edit(e) and e['entityId'] == cap['target']['entityId'] for e in edits)
            and [e['revision'] for e in edits] == list(range(max(1, cap['revision'] - 49), cap['revision'] + 1)))


def validate_goal(observed, goal):
    if (not supported(observed) or goal['entityCanvas']['entityId'] != observed['entityCanvas']['target']['entityId']
            or not equal(goal['target'], observed['entityCanvas']['target']['position'])
            or not any(equal(e, observed['entityCanvas']['target']) for e in observed.get('entities', []))):
        raise ValueError('Entity canvas requires the adopted original platform')


def binding(observed):
    identity = observed.get('identity', {})
    if identity.get('actorId') != observed['self']['actorId'] or not identifier(identity.get('operatorId')):
        raise ValueError('Entity canvas requires an authenticated actor and operator')
    return {'version': 1, 'worldInstanceId': observed['world']['instanceId'], 'actorId': identity['actorId'],
            'operatorId': identity['operatorId'], 'target': deepcopy(observed['entityCanvas']['target']),
            'adoption': deepcopy(observed['entityCanvas']['adoption'])}


def ready(observed, original):
    return (supported(observed) and equal(observed['entityCanvas']['target'], original['target'])
            and equal(observed['entityCanvas']['adoption'], original['adoption'])
            and any(equal(e, original['target']) for e in observed.get('entities', []))
            and observed.get('identity', {}).get('actorId') == original['actorId']
            and observed.get('identity', {}).get('operatorId') == original['operatorId']
            and observed['world']['instanceId'] == original['worldInstanceId'])


def plan(observed, goal):
    empty = {'reason': None, 'cells': [], 'bridges': 0, 'wood': 0, 'commands': None, 'nextAction': None}
    try:
        validate_goal(observed, goal)
    except ValueError:
        return {**empty, 'reason': 'entity_canvas_unavailable'}
    route = nav.route_info(observed, goal['target'], False, False)
    if route['reason']:
        return route
    if nav.near(observed['self']['position'], goal['target']):
        return {**empty, 'commands': 1, 'nextAction': action(goal), 'nextReason': '在原平台提交明确授权的原地画草图'}
    return {**route, 'commands': route['commands'] + 1, 'nextReason': '前往地画绑定的原平台'}


def before(observed, original):
    if not ready(observed, original):
        raise ValueError('Original canvas capability or identity changed before submission')
    return {**deepcopy(original), 'position': deepcopy(observed['self']['position']),
            'inventoryWood': observed['self']['inventory']['wood']}


def valid_before(value):
    return (isinstance(value, dict) and set(value) == {'version', 'worldInstanceId', 'actorId', 'operatorId',
                                                     'target', 'adoption', 'position', 'inventoryWood'}
            and type(value['version']) is int and value['version'] == 1
            and valid_world_instance(value['worldInstanceId']) and identifier(value['actorId'])
            and identifier(value['operatorId']) and valid_target(value['target']) and valid_adoption(value['adoption'])
            and value['worldInstanceId'] == value['adoption']['worldInstanceId'] and point(value['position'])
            and nav.distance(value['position'], value['target']['position']) <= 1.6
            and integer(value['inventoryWood']) and value['inventoryWood'] <= 12)


def envelope(value, original):
    return (isinstance(value, dict) and type(value.get('schemaVersion')) is int and value['schemaVersion'] == 1
            and value.get('rulesVersion') == 'r10' and isinstance(value.get('identity'), dict)
            and value['identity'].get('actorId') == original['actorId']
            and value['identity'].get('operatorId') == original['operatorId']
            and integer(value.get('stateVersion')) and integer(value.get('eventCursor')) and not value.get('error'))


def evidence(receipt, intent, snapshot, read, event):
    if (not valid_before(snapshot) or not envelope(receipt, snapshot) or not envelope(read, snapshot)
            or intent.get('rulesVersion') != 'r10' or intent.get('preconditionMode') != ACTOR_STATE
            or not valid_execution(receipt, intent) or receipt.get('commandId') != intent.get('commandId')
            or not isinstance(receipt.get('result'), dict) or receipt['result'].get('action') != ACTION):
        return None
    edit = {k: v for k, v in receipt['result'].items() if k != 'action'}
    request = intent.get('action', {})
    goal = {k: v for k, v in request.items() if k not in ('type', 'capabilityVersion')}
    if (not valid_edit(edit) or set(request) != {'type', 'capabilityVersion', 'entityId', 'expectedCanvasRevision', 'patch'}
            or request.get('type') != ACTION or type(request.get('capabilityVersion')) is not int
            or request['capabilityVersion'] != 1 or not valid_goal(goal)
            or edit['entityId'] != snapshot['target']['entityId'] or edit['entityId'] != request['entityId']
            or edit['baseRevision'] != request['expectedCanvasRevision'] or not equal(edit['patch'], canonical_patch(request['patch']))
            or edit['authorActorId'] != snapshot['actorId'] or edit['operatorId'] != snapshot['operatorId']
            or edit['commandId'] != intent['commandId'] or not equal(edit['position'], snapshot['position'])
            or edit['inventoryWood'] != snapshot['inventoryWood'] or edit['eventCursor'] != receipt['eventCursor']
            or edit['stateVersion'] != receipt['stateVersion'] or not equal(read.get('edit'), edit)
            or read['stateVersion'] < edit['stateVersion'] or read['eventCursor'] < edit['eventCursor']
            or not equal(event, {**edit, 'type': 'entityCanvasPainted', 'seq': edit['eventCursor'], 'actorId': edit['authorActorId']})):
        return None
    return {'worldInstanceId': snapshot['worldInstanceId'], **deepcopy(edit)}


def validate_saved(state):
    """Check frozen task authority and accounting before any I/O or selection."""
    try:
        _validate_saved(state)
    except (KeyError, TypeError, IndexError, AttributeError):
        raise ValueError('Original entity canvas state is incomplete or damaged') from None


def _validate_saved(state):
    saved, mission, facts = state['_state'], state['mission'], state['facts']
    spec, pending = saved['spec'], saved.get('pending')
    if not any('entityCanvas' in g for g in spec['goals']):
        if ('entityCanvasBinding' in saved or 'entityCanvasProof' in saved or facts.get('entityCanvasPainted')
                or facts.get('entityCanvasEdit') is not None or pending and pending.get('request', {}).get('action', {}).get('type') == ACTION):
            raise ValueError('Entity canvas authority cannot be added to an old task')
        return
    original, base, initial = saved['entityCanvasBinding'], saved['binding'], saved['initial']
    goal, limits, used = mission['goal'], state['budget']['limits'], state['budget']['used']
    if (not isinstance(original, dict) or set(original) != {'version', 'worldInstanceId', 'actorId', 'operatorId', 'target', 'adoption'}
            or not valid_before({**original, 'position': original['target']['position'], 'inventoryWood': 0})
            or original['worldInstanceId'] != base.get('instanceId') or mission['worldInstanceId'] != base.get('instanceId')
            or original['actorId'] != base.get('actorId') or mission['actorId'] != base.get('actorId')
            or initial['self'].get('operatorId') != original['operatorId']
            or base.get('rulesVersion') != 'r10' or mission['rulesVersion'] != 'r10'
            or base.get('preconditionMode') != ACTOR_STATE or mission.get('preconditionMode') != ACTOR_STATE
            or mission.get('allowEntityCanvas') is not True or spec.get('allowEntityCanvas') is not True
            or any(mission.get(k, False) is not spec.get(k, False) for k in
                   ('allowBuild', 'allowGather', 'allowTransfer', 'allowMaterialAccess', 'allowEntityNotes'))
            or not equal(limits, spec['budgets']) or any(type(v) is not int for v in limits.values())
            or any(type(v) is not int for v in spec['budgets'].values()) or set(used) != set(limits)
            or any(not integer(used[k]) or used[k] > limits[k] for k in ('commands', 'wood', 'modelCalls', 'queries'))
            or used['wood'] != 0 or not nav.finite(used['seconds']) or used['seconds'] < 0
            or not nav.finite(saved['startedEpoch']) or saved['startedEpoch'] <= 0
            or used['commands'] != len(state['steps']) or not point(mission['origin'])
            or not valid_queries(saved.get('entityCanvasQueries'), used.get('queries'), kinds=QUERY_KINDS) or used['queries'] < 1
            or not equal(mission['origin'], initial['self']['position']) or initial['self']['actorId'] != original['actorId']
            or initial['world']['instanceId'] != original['worldInstanceId'] or not supported(initial)
            or not equal(initial['entityCanvas']['target'], original['target'])
            or not equal(initial['entityCanvas']['adoption'], original['adoption'])
            or goal is not None and (not equal(goal, spec['goals'][0]) or not valid_goal(goal.get('entityCanvas')))
            or type(facts.get('entityCanvasPainted')) is not bool):
        raise ValueError('Original entity canvas binding, authorization or budget is damaged')
    validate_goal(initial, spec['goals'][0])
    identifiers = []
    actor_version = initial['stateVersion']
    for index, step in enumerate(state['steps'], 1):
        if (not integer(step.get('index')) or step['index'] != index or not identifier(step.get('commandId'))
                or step.get('preconditionMode') != ACTOR_STATE or not integer(step.get('expectedStateVersion'))
                or step.get('status') not in ('committed', 'rejected', 'unknown', 'pending')
                or step.get('action', {}).get('type') not in ('walk', ACTION)):
            raise ValueError('Original entity canvas command accounting is damaged')
        if step['expectedStateVersion'] != actor_version:
            raise ValueError('Original entity canvas actor-state chain is damaged')
        if step['status'] == 'committed':
            if not integer(step.get('stateVersion')) or step['stateVersion'] <= actor_version:
                raise ValueError('Original entity canvas actor-state version is damaged')
            actor_version = step['stateVersion']
        identifiers.append(step['commandId'])
        if step['action']['type'] == ACTION and (goal is None or not equal(step['action'], action(goal))):
            raise ValueError('Original entity canvas patch or revision changed')
    if not integer(saved.get('entityCanvasActorStateVersion')) or saved['entityCanvasActorStateVersion'] != actor_version:
        raise ValueError('Original entity canvas actor-state anchor is damaged')
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Original entity canvas commands are duplicated')
    if goal is not None and (state['decision'] is None or state['decision'].get('goalId') != goal['id'] or used['modelCalls'] != 1):
        raise ValueError('Original entity canvas choice is damaged')
    if pending is not None:
        request, step = pending['request'], state['steps'][-1]
        if (request.get('rulesVersion') != 'r10' or type(request.get('schemaVersion')) is not int or request['schemaVersion'] != 1
                or request.get('commandId') != step['commandId'] or not equal(request.get('action'), step['action'])
                or request.get('preconditionMode') != ACTOR_STATE or request.get('expectedStateVersion') != step['expectedStateVersion']
                or type(pending.get('woodCost')) is not int or pending['woodCost'] != 0 or step['status'] not in ('pending', 'unknown')):
            raise ValueError('Original entity canvas pending command is damaged')
        if request['action']['type'] == ACTION:
            snapshot = pending['entityCanvasBefore']
            if (not valid_before(snapshot) or facts['entityCanvasPainted']
                    or any(not equal(snapshot.get(k), v) for k, v in original.items())
                    or not equal(snapshot['position'], step['position']) or snapshot['inventoryWood'] != step['inventoryWood']):
                raise ValueError('Original entity canvas before facts are damaged')
        elif (set(request['action']) != {'type', 'to'} or not point(request['action']['to'])
              or not equal(pending['walkBefore']['position'], step['position'])):
            raise ValueError('Original entity canvas approach is damaged')
    committed = [s for s in state['steps'] if s['action']['type'] == ACTION and s['status'] == 'committed']
    if facts['entityCanvasPainted']:
        proof = saved['entityCanvasProof']
        record = evidence(proof['receipt'], proof['request'], proof['before'], proof['readback'], proof['event'])
        if (record is None or not equal(record, facts['entityCanvasEdit']) or len(committed) != 1
                or not equal(committed[0].get('entityCanvasEvidence'), record) or committed[0]['commandId'] != record['commandId']
                or any(not equal(proof['before'].get(k), v) for k, v in original.items())
                or not equal(proof['request']['action'], action(goal))):
            raise ValueError('Original entity canvas completion evidence is damaged')
    elif facts.get('entityCanvasEdit') is not None or committed or saved.get('entityCanvasProof') is not None:
        raise ValueError('Unconfirmed entity canvas cannot carry completion facts')
