"""One explicitly authorized workshop action; immutable evidence, bounded recovery.

The selector is never called. A subsequent task must name the confirmed output
of its predecessor; neither recovery nor navigation chooses another facility.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
import uuid

import continuous_navigation as nav
import command_preconditions as preconditions
from foundation_agent import valid_world_instance, WorldBindingError
from resident_entity_notes import equal, identifier, TARGET_FIELDS

CAPABILITY = 'workshop-v1'
STARTUP = 'workshop-task-startup'
PERMISSIONS = {'build_workshop': 'allowWorkshopBuild', 'craft_tool': 'allowCraftTool',
               'deposit_wood': 'allowDepositWood', 'withdraw_wood': 'allowWithdrawWood'}
RECIPES = [
    {'id': 'workbench.v1', 'definitionId': 'workbench', 'woodCost': 3,
     'requiresWorkbench': False, 'requiresTool': False},
    {'id': 'wooden_mallet.v1', 'definitionId': 'wooden_mallet', 'woodCost': 1,
     'requiresWorkbench': True, 'requiresTool': False},
    {'id': 'wooden_chest.v1', 'definitionId': 'wooden_chest', 'woodCost': 3,
     'requiresWorkbench': False, 'requiresTool': True},
]
TOOL_FIELDS = {'toolId', 'definitionId', 'definitionVersion', 'ownerActorId', 'embodiedWood',
               'workbenchId', 'commandId', 'stateVersion', 'eventCursor'}
DETAIL_FIELDS = {'capabilityVersion', 'authorActorId', 'operatorId', 'commandId', 'action', 'entity', 'tool',
                 'quantity', 'inventoryWoodBefore', 'inventoryWood', 'storedWoodBefore', 'storedWood',
                 'position', 'stateVersion', 'eventCursor', 'completedAtUtc'}
BEFORE_FIELDS = {'version', 'worldInstanceId', 'actorId', 'operatorId', 'adoption', 'action',
                 'target', 'tool', 'position', 'inventoryWood', 'storedWood', 'stateVersion', 'entityIds', 'toolIds'}
QUERY_KINDS = {'observation', 'receipt', 'workshop_detail', 'workshop_event'}


def count(value, maximum=12):
    return type(value) is int and 0 <= value <= maximum


def action_valid(action):
    if (not isinstance(action, dict) or action.get('type') not in PERMISSIONS
            or type(action.get('capabilityVersion')) is not int or action['capabilityVersion'] != 1):
        return False
    kind = action['type']
    if kind == 'build_workshop':
        return (set(action) == {'type', 'capabilityVersion', 'recipeId', 'at', 'toolId'}
                and nav.point(action['at']) and all(v >= 0 for v in action['at'])
                and (action['recipeId'] == 'workbench.v1' and action['toolId'] is None
                     or action['recipeId'] == 'wooden_chest.v1' and identifier(action['toolId'])))
    if kind == 'craft_tool':
        return (set(action) == {'type', 'capabilityVersion', 'entityId', 'recipeId'}
                and identifier(action['entityId']) and action['recipeId'] == 'wooden_mallet.v1')
    return (set(action) == {'type', 'capabilityVersion', 'entityId', 'quantity'}
            and identifier(action['entityId']) and count(action['quantity']) and action['quantity'] > 0)


def uses(spec):
    return (isinstance(spec, dict) and isinstance(spec.get('goals'), list)
            and any(isinstance(goal, dict) and 'workshop' in goal for goal in spec['goals']))


def normalize_spec(value):
    required = {'missionId', 'objective', 'goals', 'allowBuild', 'budgets', *PERMISSIONS.values()}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('Workshop tasks require only their explicit fixed-task fields and four permissions')
    if (not isinstance(value['missionId'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value['missionId'])
            or not isinstance(value['objective'], str) or not 1 <= len(value['objective']) <= 500
            or value['allowBuild'] is not False or not isinstance(value['goals'], list) or len(value['goals']) != 1):
        raise ValueError('Workshop requires one fixed action, a valid purpose, and no legacy build authority')
    goal = value['goals'][0]
    if (not isinstance(goal, dict) or set(goal) != {'id', 'label', 'target', 'workshop'}
            or not identifier(goal['id']) or not isinstance(goal['label'], str) or not goal['label']
            or not nav.point(goal['target']) or any(v < 0 for v in goal['target'])):
        raise ValueError('Invalid workshop goal')
    item = goal['workshop']
    if (not isinstance(item, dict) or set(item) != {'worldInstanceId', 'actorId', 'action', 'returnToOrigin'}
            or not valid_world_instance(item['worldInstanceId']) or not identifier(item['actorId'])
            or type(item['returnToOrigin']) is not bool or not action_valid(item['action'])):
        raise ValueError('Workshop requires a fixed instance, actor, exact action and explicit return choice')
    action = item['action']
    if action['type'] == 'build_workshop' and not equal(goal['target'], action['at']):
        raise ValueError('Build coordinates disagree with the original target')
    for permission in PERMISSIONS.values():
        if type(value[permission]) is not bool or value[permission] is not (permission == PERMISSIONS[action['type']]):
            raise ValueError('Only the permission for this one workshop action may be enabled')
    limits = {'commands': (1, 1000), 'queries': (1, 5000), 'wood': (0, 12), 'woodMoved': (0, 12),
              'seconds': (1, 600), 'modelCalls': (0, 0)}
    budget = value['budgets']
    if (not isinstance(budget, dict) or set(budget) != set(limits)
            or any(type(budget[k]) is not int or not low <= budget[k] <= high for k, (low, high) in limits.items())):
        raise ValueError('Invalid bounded workshop budgets; fixed actions have zero model calls')
    return deepcopy(value)


def valid_entity(entity, definition=None):
    return (isinstance(entity, dict) and set(entity) == TARGET_FIELDS
            and identifier(entity['entityId']) and identifier(entity['ownerActorId'])
            and entity['definitionId'] in nav.FURNITURE
            and (definition is None or entity['definitionId'] == definition)
            and type(entity['definitionVersion']) is int and entity['definitionVersion'] == 1
            and entity['rulesVersion'] == 'r10' and nav.point(entity['position'])
            and type(entity['embodiedWood']) is int and entity['embodiedWood'] == 3)


def valid_tool(tool):
    return (isinstance(tool, dict) and set(tool) == TOOL_FIELDS
            and all(identifier(tool[k]) for k in ('toolId', 'ownerActorId', 'workbenchId', 'commandId'))
            and tool['definitionId'] == 'wooden_mallet'
            and type(tool['definitionVersion']) is int and tool['definitionVersion'] == 1
            and type(tool['embodiedWood']) is int and tool['embodiedWood'] == 1
            and preconditions.integer(tool['stateVersion']) and preconditions.integer(tool['eventCursor'])
            and tool['eventCursor'] > 0)


def valid_adoption(value):
    return (isinstance(value, dict) and set(value) == {'worldInstanceId', 'stateVersion', 'eventCursor'}
            and valid_world_instance(value['worldInstanceId']) and preconditions.integer(value['stateVersion'])
            and preconditions.integer(value['eventCursor']) and value['eventCursor'] > 0)


def supported(observed):
    try:
        return _supported(observed)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def _supported(observed):
    cap, identity = observed.get('workshop'), observed.get('identity', {})
    if (not nav.continuous(observed) or observed['rulesVersion'] != 'r10'
            or not valid_world_instance(observed['world'].get('instanceId'))
            or not preconditions.integer(observed.get('stateVersion'))
            or not preconditions.integer(observed.get('eventCursor'))
            or identity.get('actorId') != observed['self']['actorId'] or not identifier(identity.get('operatorId'))
            or not nav.point(observed['self']['position']) or not count(observed['self']['inventory']['wood'])
            or preconditions.select_mode(observed) != preconditions.ACTOR_STATE
            or not isinstance(cap, dict) or cap.get('capability') != CAPABILITY
            or any(type(cap.get(k)) is not int or cap[k] != v for k, v in
                   {'version': 1, 'inventoryCapacity': 12, 'chestCapacity': 12}.items())
            or any(not nav.finite(cap.get(k)) or cap[k] != v for k, v in {'buildReach': 3.2, 'interactReach': 1.6}.items())
            or cap.get('workbenchAccess') != 'public' or cap.get('chestAccess') != 'owner'
            or not valid_adoption(cap.get('adoption'))
            or cap['adoption']['worldInstanceId'] != observed['world']['instanceId']
            or cap['adoption']['stateVersion'] > observed['stateVersion']
            or cap['adoption']['eventCursor'] > observed['eventCursor']
            or not isinstance(cap.get('recipes'), list) or len(cap['recipes']) != 3
            or not equal(sorted(cap['recipes'], key=lambda r: r['id']), sorted(RECIPES, key=lambda r: r['id']))):
        return False
    nav.validate_observation(observed)
    entities = observed['entities']
    if (not all(identifier(e.get('entityId')) for e in entities)
            or len({e['entityId'] for e in entities}) != len(entities)
            or any(e['definitionId'] in nav.FURNITURE and not valid_entity(e) for e in entities)):
        return False
    benches = [e for e in entities if e['definitionId'] == 'workbench']
    if (not isinstance(cap.get('workbenches'), list)
            or not equal(sorted(cap['workbenches'], key=lambda e: e['entityId']), sorted(benches, key=lambda e: e['entityId']))):
        return False
    tools, chests, actor = cap.get('tools'), cap.get('chests'), observed['self']['actorId']
    if (not isinstance(tools, list) or not all(valid_tool(t) and t['ownerActorId'] == actor
            and t['workbenchId'] in {b['entityId'] for b in benches} and t['stateVersion'] <= observed['stateVersion']
            and t['eventCursor'] <= observed['eventCursor'] for t in tools)
            or len({t['toolId'] for t in tools}) != len(tools) or not isinstance(chests, list)
            or not all(isinstance(c, dict) and set(c) == {'entity', 'storedWood', 'capacity'}
                and valid_entity(c['entity'], 'wooden_chest') and c['entity']['ownerActorId'] == actor
                and count(c['storedWood']) and type(c['capacity']) is int and c['capacity'] == 12 for c in chests)):
        return False
    return equal(sorted([c['entity'] for c in chests], key=lambda e: e['entityId']),
                 sorted([e for e in entities if e['definitionId'] == 'wooden_chest' and e['ownerActorId'] == actor],
                        key=lambda e: e['entityId']))


def binding(observed, goal):
    if not supported(observed):
        raise ValueError('Workshop capability is missing, malformed or unsupported')
    spec, cap = goal['workshop'], observed['workshop']
    if observed['world']['instanceId'] != spec['worldInstanceId'] or observed['self']['actorId'] != spec['actorId']:
        raise WorldBindingError('Workshop task belongs to another original instance or resident')
    action = spec['action']
    target = None if action['type'] == 'build_workshop' else next(
        (e for e in observed['entities'] if e['entityId'] == action['entityId']), None)
    if action['type'] != 'build_workshop':
        definition = 'workbench' if action['type'] == 'craft_tool' else 'wooden_chest'
        if not valid_entity(target, definition) or not equal(target['position'], goal['target']):
            raise ValueError('Original workshop target or coordinates are unavailable')
        if definition == 'wooden_chest' and target['ownerActorId'] != spec['actorId']:
            raise ValueError('The specified chest belongs to another resident')
    tool = None
    if action['type'] == 'build_workshop' and action['recipeId'] == 'wooden_chest.v1':
        tool = next((t for t in cap['tools'] if t['toolId'] == action['toolId']), None)
        if not valid_tool(tool) or tool['ownerActorId'] != spec['actorId']:
            raise ValueError('The specified mallet is unavailable or belongs to another resident')
    return {'version': 1, 'worldInstanceId': spec['worldInstanceId'], 'actorId': spec['actorId'],
            'operatorId': observed['identity']['operatorId'], 'adoption': deepcopy(cap['adoption']),
            'target': deepcopy(target), 'tool': deepcopy(tool)}


def ready(observed, goal, original):
    try:
        return equal(binding(observed, goal), original)
    except (ValueError, WorldBindingError):
        return False


def action_cost(action):
    return 3 if action['type'] == 'build_workshop' else 1 if action['type'] == 'craft_tool' else 0


def movement_cost(action):
    return action['quantity'] if action['type'] in ('deposit_wood', 'withdraw_wood') else 0


def before(observed, goal, original):
    if not ready(observed, goal, original):
        raise ValueError('Original workshop binding changed before submission')
    action = goal['workshop']['action']
    stored = next((c['storedWood'] for c in observed['workshop']['chests']
                   if c['entity']['entityId'] == action.get('entityId')), None)
    return {**deepcopy(original), 'action': deepcopy(action), 'position': deepcopy(observed['self']['position']),
            'inventoryWood': observed['self']['inventory']['wood'], 'storedWood': stored,
            'stateVersion': observed['stateVersion'], 'entityIds': [e['entityId'] for e in observed['entities']],
            'toolIds': [t['toolId'] for t in observed['workshop']['tools']]}


def valid_before(value):
    if (not isinstance(value, dict) or set(value) != BEFORE_FIELDS
            or type(value['version']) is not int or value['version'] != 1
            or not valid_world_instance(value['worldInstanceId'])
            or not all(identifier(value[k]) for k in ('actorId', 'operatorId'))
            or not valid_adoption(value['adoption']) or value['adoption']['worldInstanceId'] != value['worldInstanceId']
            or not action_valid(value['action']) or not nav.point(value['position']) or not count(value['inventoryWood'])
            or not preconditions.integer(value['stateVersion']) or value['stateVersion'] < value['adoption']['stateVersion']
            or not isinstance(value['entityIds'], list) or not all(identifier(i) for i in value['entityIds'])
            or len(set(value['entityIds'])) != len(value['entityIds'])
            or not isinstance(value['toolIds'], list) or not all(identifier(i) for i in value['toolIds'])
            or len(set(value['toolIds'])) != len(value['toolIds'])):
        return False
    action, target, tool, actor = value['action'], value['target'], value['tool'], value['actorId']
    if action['type'] == 'build_workshop':
        return (target is None and value['storedWood'] is None
                and nav.distance(value['position'], action['at']) <= 3.2 + 1e-8
                and (action['recipeId'] == 'workbench.v1' and tool is None
                     or action['recipeId'] == 'wooden_chest.v1' and valid_tool(tool)
                     and tool['toolId'] == action['toolId'] and tool['ownerActorId'] == actor))
    return (valid_entity(target, 'workbench' if action['type'] == 'craft_tool' else 'wooden_chest')
            and target['entityId'] == action['entityId'] and target['entityId'] in value['entityIds']
            and nav.distance(value['position'], target['position']) <= 1.6 + 1e-8 and tool is None
            and (action['type'] == 'craft_tool' and value['storedWood'] is None
                 or action['type'] != 'craft_tool' and target['ownerActorId'] == actor and count(value['storedWood'])))


def envelope(value, original, *, error=False):
    return (isinstance(value, dict) and type(value.get('schemaVersion')) is int and value['schemaVersion'] == 1
            and value.get('rulesVersion') == 'r10' and isinstance(value.get('identity'), dict)
            and value['identity'].get('actorId') == original['actorId']
            and value['identity'].get('operatorId') == original['operatorId']
            and preconditions.integer(value.get('stateVersion')) and preconditions.integer(value.get('eventCursor'))
            and (error or value.get('error') is None))


def valid_detail(detail):
    if (not isinstance(detail, dict) or set(detail) != DETAIL_FIELDS
            or type(detail['capabilityVersion']) is not int or detail['capabilityVersion'] != 1
            or not all(identifier(detail[k]) for k in ('authorActorId', 'operatorId', 'commandId'))
            or not action_valid(detail['action']) or not valid_entity(detail['entity'])
            or not (detail['tool'] is None or valid_tool(detail['tool']))
            or not count(detail['quantity']) or detail['quantity'] < 1
            or not all(count(detail[k]) for k in ('inventoryWoodBefore', 'inventoryWood'))
            or not all(detail[k] is None or count(detail[k]) for k in ('storedWoodBefore', 'storedWood'))
            or not nav.point(detail['position']) or not preconditions.integer(detail['stateVersion'])
            or not preconditions.integer(detail['eventCursor']) or detail['eventCursor'] < 1
            or not isinstance(detail['completedAtUtc'], str)):
        return False
    try:
        return datetime.fromisoformat(detail['completedAtUtc'].replace('Z', '+00:00')).utcoffset() is not None
    except ValueError:
        return False


def evidence(receipt, intent, snapshot, proof):
    """All three original records, identity headers and exact inventory deltas agree."""
    if (not valid_before(snapshot) or not envelope(receipt, snapshot) or not isinstance(proof, dict)
            or set(proof) != {'receiptInstanceId', 'detailInstanceId', 'eventInstanceId', 'detail', 'events'}
            or any(proof[k] != snapshot['worldInstanceId'] for k in ('receiptInstanceId', 'detailInstanceId', 'eventInstanceId'))
            or intent.get('rulesVersion') != 'r10' or intent.get('preconditionMode') != preconditions.ACTOR_STATE
            or not preconditions.valid_execution(receipt, intent) or receipt.get('commandId') != intent.get('commandId')
            or not equal(intent.get('action'), snapshot['action']) or not isinstance(receipt.get('result'), dict)
            or set(receipt['result']) != {'action', 'workshopAction'} or receipt['result']['action'] != snapshot['action']['type']):
        return None
    record, read, events = receipt['result']['workshopAction'], proof['detail'], proof['events']
    if (not valid_detail(record) or not envelope(read, snapshot) or not envelope(events, snapshot)
            or not equal(read.get('workshopAction'), record) or not equal(record['action'], snapshot['action'])
            or record['authorActorId'] != snapshot['actorId'] or record['operatorId'] != snapshot['operatorId']
            or record['commandId'] != intent['commandId'] or not equal(record['position'], snapshot['position'])
            or record['inventoryWoodBefore'] != snapshot['inventoryWood']
            or record['stateVersion'] != receipt['stateVersion'] or record['eventCursor'] != receipt['eventCursor']
            or receipt['execution']['appliedOnStateVersion'] < snapshot['stateVersion']
            or any(e['stateVersion'] < record['stateVersion'] or e['eventCursor'] < record['eventCursor'] for e in (read, events))
            or not isinstance(events.get('events'), list)):
        return None
    matches = [e for e in events['events'] if isinstance(e, dict) and e.get('seq') == record['eventCursor']]
    expected_event = {'seq': record['eventCursor'], 'stateVersion': record['stateVersion'],
                      'actorId': snapshot['actorId'], 'commandId': intent['commandId'],
                      'type': 'workshopActionCompleted', 'workshopAction': record}
    if len(matches) != 1 or not equal(matches[0], expected_event):
        return None
    action, entity, tool = snapshot['action'], record['entity'], record['tool']
    kind, quantity = action['type'], record['quantity']
    expected_quantity = action_cost(action) or movement_cost(action)
    if quantity != expected_quantity:
        return None
    delta = quantity if kind == 'withdraw_wood' else -quantity
    if record['inventoryWood'] != snapshot['inventoryWood'] + delta:
        return None
    if kind == 'build_workshop':
        definition = 'workbench' if action['recipeId'] == 'workbench.v1' else 'wooden_chest'
        if (entity['definitionId'] != definition or entity['ownerActorId'] != snapshot['actorId']
                or entity['entityId'] in snapshot['entityIds'] or not equal(entity['position'], action['at'])
                or not equal(tool, snapshot['tool'])
                or not equal([record['storedWoodBefore'], record['storedWood']], [0, 0] if definition == 'wooden_chest' else [None, None])):
            return None
    elif not equal(entity, snapshot['target']):
        return None
    elif kind == 'craft_tool':
        if (not valid_tool(tool) or tool['ownerActorId'] != snapshot['actorId'] or tool['workbenchId'] != entity['entityId']
                or tool['toolId'] in snapshot['toolIds']
                or tool['commandId'] != intent['commandId'] or tool['stateVersion'] != record['stateVersion']
                or tool['eventCursor'] != record['eventCursor']
                or record['storedWoodBefore'] is not None or record['storedWood'] is not None):
            return None
    elif (tool is not None or record['storedWoodBefore'] != snapshot['storedWood']
          or record['storedWood'] != snapshot['storedWood'] - delta):
        return None
    return {'worldInstanceId': snapshot['worldInstanceId'], **deepcopy(record)}


def placement_issue(observed, action):
    definition = 'workbench' if action['recipeId'] == 'workbench.v1' else 'wooden_chest'
    hx, hz = nav.ENTITY_HALF_SIZE[definition]
    x, z = action['at']
    x0, z0, x1, z1 = observed['world']['bounds']
    if x-hx < x0 or z-hz < z0 or x+hx > x1 or z+hz > z1:
        return 'workshop_outside_world'
    exclusion = observed.get('materialAccess', {}).get('buildExclusion')
    if (not isinstance(exclusion, list) or len(exclusion) != 4 or not all(nav.finite(n) for n in exclusion)):
        return 'workshop_source_geometry_unavailable'
    left, top, right, bottom = exclusion
    if x+hx > left and x-hx < right and z+hz > top and z-hz < bottom:
        return 'workshop_material_source_reserved'
    river = observed['terrain']['river']
    heights = [z-hz, z+hz, *(p[1] for p in river['centerline'] if z-hz < p[1] < z+hz)]
    if any(x+hx > nav._river_x(river['centerline'], h)-river['halfWidth']
           and x-hx < nav._river_x(river['centerline'], h)+river['halfWidth'] for h in heights):
        return 'workshop_requires_land'
    rectangle = [x, z, hx, hz]
    if any(nav._point_rectangle(c[:2], rectangle) < c[2] for c in nav.navigation(observed).circles):
        return 'workshop_site_occupied'
    for entity in observed['entities']:
        ex, ez = nav.entity_half_size(entity)
        if abs(entity['position'][0]-x) < ex+hx and abs(entity['position'][1]-z) < ez+hz:
            return 'workshop_site_occupied'
    residents = observed.get('residents')
    if not isinstance(residents, list) or any(not isinstance(r, dict) or not nav.point(r.get('position')) for r in residents):
        return 'workshop_resident_positions_unavailable'
    if any(r['actorId'] != observed['self']['actorId']
           and nav._point_rectangle(r['position'], rectangle) < observed['movement']['radius'] for r in residents):
        return 'workshop_resident_at_site'
    return None


def approach(observed, goal, original):
    action, start = goal['workshop']['action'], observed['self']['position']
    target, geometry = goal['target'], nav.navigation(observed)
    building = action['type'] == 'build_workshop'
    reach = 3.2 if building else 1.6
    if building:
        definition = 'workbench' if action['recipeId'] == 'workbench.v1' else 'wooden_chest'
        rectangle = [*target, *nav.ENTITY_HALF_SIZE[definition]]
        usable = lambda p: (geometry.walkable(p) and nav.distance(p, target) <= reach
                            and nav._point_rectangle(p, rectangle) >= observed['movement']['radius'] + nav.MARGIN)
    else:
        ray = nav.navigation(observed, interaction_target=action['entityId'])
        usable = lambda p: geometry.walkable(p) and nav.distance(p, target) <= reach and ray.clear(p, target)
    if usable(start):
        return []
    angle = math.atan2(start[1]-target[1], start[0]-target[0])
    candidates = [[target[0]+radius*math.cos(a), target[1]+radius*math.sin(a)]
                  for radius in (reach-.1, reach-.35, min(1.2, reach-.1))
                  for a in (angle, *(i*math.tau/24 for i in range(24))) ]
    for candidate in sorted(candidates, key=lambda p: nav.distance(start, p)):
        if usable(candidate):
            path = geometry.route(start, candidate)
            if path is not None:
                return path
    return None


def plan(observed, goal, original):
    if not ready(observed, goal, original):
        return None, 'workshop_original_target_or_capability_changed'
    action, wood = goal['workshop']['action'], observed['self']['inventory']['wood']
    if action['type'] == 'build_workshop':
        issue = placement_issue(observed, action)
        if issue:
            return None, issue
    if wood < action_cost(action):
        return None, 'workshop_insufficient_material'
    if action['type'] in ('deposit_wood', 'withdraw_wood'):
        stored = next(c['storedWood'] for c in observed['workshop']['chests'] if c['entity']['entityId'] == action['entityId'])
        quantity = action['quantity']
        if action['type'] == 'deposit_wood' and (wood < quantity or stored+quantity > 12):
            return None, 'workshop_deposit_inventory_or_capacity'
        if action['type'] == 'withdraw_wood' and (stored < quantity or wood+quantity > 12):
            return None, 'workshop_withdraw_inventory_or_capacity'
    path = approach(observed, goal, original)
    if path is None:
        return None, 'workshop_operation_side_unreachable'
    return ({'type': 'walk', 'to': list(path[0])} if path else deepcopy(action)), None


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _report(state):
    return deepcopy({key: value for key, value in state.items() if key != '_state'})


def _world(observed):
    from resident_mission import _public
    value = _public(observed)['world']
    value['workshop'] = deepcopy(observed['workshop'])
    value['observedStateVersion'] = observed['stateVersion']
    value['observedSelf'] = {'actorId': observed['self']['actorId'],
                             'position': deepcopy(observed['self']['position']),
                             'inventoryWood': observed['self']['inventory']['wood']}
    return value


def _query_log(log, count_value):
    return (isinstance(log, list) and preconditions.integer(count_value) and len(log) == count_value
            and all(isinstance(q, dict) and set(q) == {'index', 'kind'}
                    and type(q['index']) is int and q['index'] == i and q['kind'] in QUERY_KINDS
                    for i, q in enumerate(log, 1)))


def _startup_valid(value, spec, endpoint):
    return (isinstance(value, dict) and set(value) == {'schemaVersion', 'kind', 'spec', 'endpoint', 'startedEpoch', 'used', 'queries'}
            and type(value['schemaVersion']) is int and value['schemaVersion'] == 1 and value['kind'] == STARTUP
            and equal(value['spec'], spec) and isinstance(value['endpoint'], dict)
            and set(value['endpoint']) == {'url', 'prefix'} and isinstance(value['endpoint']['url'], str)
            and value['endpoint']['prefix'] == endpoint['prefix']
            and nav.finite(value['startedEpoch']) and value['startedEpoch'] > 0
            and isinstance(value['used'], dict) and set(value['used']) == {'queries', 'seconds'}
            and _query_log(value['queries'], value['used'].get('queries'))
            and value['used']['queries'] <= spec['budgets']['queries']
            and all(q['kind'] == 'observation' for q in value['queries'])
            and nav.finite(value['used']['seconds']) and value['used']['seconds'] >= 0)


def _new_state(observed, spec, startup, endpoint):
    goal = spec['goals'][0]
    original = binding(observed, goal)
    origin = deepcopy(observed['self']['position'])
    used = {key: 0 for key in spec['budgets']}
    used.update(startup['used'])
    base = {**endpoint, 'worldId': observed['world']['id'], 'actorId': original['actorId'],
            'rulesVersion': 'r10', 'instanceId': original['worldInstanceId'], 'bindingVersion': 1,
            'preconditionBindingVersion': 1, 'preconditionMode': preconditions.ACTOR_STATE}
    return {'schemaVersion': 1, 'kind': 'resident-mission-report',
            'mission': {'id': spec['missionId'], 'objective': spec['objective'], 'actorId': original['actorId'],
                        'operatorId': original['operatorId'], 'worldId': base['worldId'], 'rulesVersion': 'r10',
                        'worldInstanceId': original['worldInstanceId'], 'preconditionMode': preconditions.ACTOR_STATE,
                        'arrivalTolerance': nav.ARRIVAL_TOLERANCE, 'workshopVersion': 1, 'origin': origin,
                        'goal': deepcopy(goal), 'allowBuild': False,
                        **{key: spec[key] for key in PERMISSIONS.values()},
                        'status': 'running', 'reason': 'workshop_fixed_action', 'startedAtUtc': _utc(), 'updatedAtUtc': _utc()},
            'decision': {'goalId': goal['id'], 'reason': '任务明确指定单一动作；未调用选择器',
                         'provider': {'kind': 'fixed-reference', 'model': 'none', 'usage': {}}},
            'budget': {'limits': deepcopy(spec['budgets']), 'used': used},
            'facts': {'goalReached': False, 'returned': True, 'workshopCompleted': False, 'workshopAction': None,
                      'woodClaimed': 0, 'woodGathered': 0, 'woodTransferred': 0, 'woodDeposited': 0, 'woodWithdrawn': 0,
                      'createdEntityIds': [], 'createdToolIds': [], 'startStateVersion': observed['stateVersion'],
                      'endStateVersion': observed['stateVersion'], 'verifiedAtUtc': None},
            'world': _world(observed), 'steps': [],
            'feedback': {'summary': '明确工作台动作尚未执行', 'issues': [], 'suggestions': []},
            '_state': {'workshopTrackingVersion': 1, 'spec': deepcopy(spec), 'binding': base,
                       'workshopBinding': original, 'initial': deepcopy(observed), 'latest': deepcopy(observed),
                       'startedEpoch': startup['startedEpoch'], 'queries': deepcopy(startup['queries']),
                       'actorStateVersion': observed['stateVersion'], 'confirmedPosition': origin,
                       'confirmedInventoryWood': observed['self']['inventory']['wood'], 'terminal': False,
                       'pending': None}}


def _walk_before_valid(value, original):
    return (isinstance(value, dict) and set(value) == {'version', 'worldInstanceId', 'actorId', 'operatorId',
                                                     'position', 'inventoryWood', 'stateVersion', 'maxStepDistance'}
            and type(value['version']) is int and value['version'] == 1
            and all(value[k] == original[k] for k in ('worldInstanceId', 'actorId', 'operatorId'))
            and nav.point(value['position']) and count(value['inventoryWood'])
            and preconditions.integer(value['stateVersion'])
            and nav.finite(value['maxStepDistance']) and 0 < value['maxStepDistance'] <= .6)


def _receipt_valid(receipt, intent, snapshot, instance, *, committed):
    if (instance != snapshot['worldInstanceId'] or not envelope(receipt, snapshot, error=not committed)
            or receipt.get('commandId') != intent['commandId']
            or not preconditions.valid_execution(receipt, intent, committed=committed)):
        return False
    if committed:
        return isinstance(receipt.get('result'), dict) and receipt['result'].get('action') == intent['action']['type']
    error = receipt.get('error')
    return (isinstance(error, dict) and error.get('mutated') is False and isinstance(error.get('code'), str)
            and error['code'] not in ('INVALID_REQUEST', 'IDEMPOTENCY_CONFLICT', 'CLIENT_CAPABILITY_REQUIRED',
                                     'INVALID_WORLD_INSTANCE', 'WORLD_INSTANCE_REQUIRED', 'WORLD_INSTANCE_MISMATCH',
                                     'WORLD_INSTANCE_UNAVAILABLE'))


def validate_saved(state, spec, endpoint):
    """Reject damaged authority, budgets and all terminal claims before any I/O."""
    try:
        _validate_saved(state, spec, endpoint)
    except (KeyError, TypeError, AttributeError, IndexError):
        raise ValueError('Original workshop task is incomplete or damaged') from None


def _validate_saved(state, spec, endpoint):
    saved, mission, facts, steps = state['_state'], state['mission'], state['facts'], state['steps']
    base, original, initial, latest = saved['binding'], saved['workshopBinding'], saved['initial'], saved['latest']
    limits, used = state['budget']['limits'], state['budget']['used']
    goal, frozen = spec['goals'][0], spec['goals'][0]['workshop']
    if (type(state.get('schemaVersion')) is not int or state['schemaVersion'] != 1 or state.get('kind') != 'resident-mission-report'
            or type(saved.get('workshopTrackingVersion')) is not int or saved['workshopTrackingVersion'] != 1
            or not equal(saved['spec'], spec) or not equal(normalize_spec(saved['spec']), spec)
            or not equal(limits, spec['budgets']) or set(used) != set(limits)
            or any(not preconditions.integer(used[k]) or used[k] > limits[k] for k in limits if k != 'seconds')
            or used['modelCalls'] != 0 or not nav.finite(used['seconds']) or used['seconds'] < 0
            or not nav.finite(saved['startedEpoch']) or saved['startedEpoch'] <= 0
            or not _query_log(saved['queries'], used['queries']) or used['queries'] < 1
            or not isinstance(steps, list) or used['commands'] != len(steps)
            or base['prefix'] != endpoint['prefix'] or not isinstance(base['url'], str)
            or base['worldId'] != initial['world']['id'] or base['actorId'] != frozen['actorId']
            or base['instanceId'] != frozen['worldInstanceId'] or base['rulesVersion'] != 'r10'
            or type(base.get('bindingVersion')) is not int or base['bindingVersion'] != 1
            or not supported(initial) or not supported(latest) or not equal(binding(initial, goal), original)
            or not ready(latest, goal, original) or latest['stateVersion'] < initial['stateVersion']
            or not equal(state['world'], _world(latest))
            or mission['id'] != spec['missionId'] or mission['objective'] != spec['objective']
            or not equal(mission['goal'], goal) or not equal(mission['origin'], initial['self']['position'])
            or mission.get('allowBuild') is not False or any(mission.get(k) is not spec[k] for k in PERMISSIONS.values())
            or mission['actorId'] != original['actorId'] or mission['operatorId'] != original['operatorId']
            or mission['worldInstanceId'] != original['worldInstanceId'] or mission['worldId'] != base['worldId']
            or mission['rulesVersion'] != 'r10' or mission.get('preconditionMode') != preconditions.ACTOR_STATE
            or type(mission.get('workshopVersion')) is not int or mission['workshopVersion'] != 1
            or not nav.finite(mission.get('arrivalTolerance')) or mission['arrivalTolerance'] != .06
            or mission['status'] not in ('running', 'paused', 'blocked', 'budget_exhausted', 'unknown', 'completed')
            or type(saved['terminal']) is not bool
            or not equal(state['decision'], {'goalId': goal['id'], 'reason': '任务明确指定单一动作；未调用选择器',
                       'provider': {'kind': 'fixed-reference', 'model': 'none', 'usage': {}}})):
        raise ValueError('Original workshop identity, authority, snapshots or budgets are damaged')
    version = initial['stateVersion']
    position = initial['self']['position']
    inventory = initial['self']['inventory']['wood']
    spent = moved = deposited = withdrawn = 0
    entities, tools, completed = [], [], []
    pending_count, rejected_count, command_ids = 0, 0, set()
    end_version = max(initial['stateVersion'], latest['stateVersion'])
    for i, step in enumerate(steps, 1):
        request, snapshot = step['request'], step['before']
        action = request['action']
        workshop = action.get('type') in PERMISSIONS
        if (type(step['index']) is not int or step['index'] != i or not identifier(step['commandId'])
                or step['commandId'] in command_ids or not isinstance(step['reason'], str)
                or set(request) != {'schemaVersion', 'rulesVersion', 'commandId', 'expectedStateVersion', 'preconditionMode', 'action'}
                or type(request['schemaVersion']) is not int or request['schemaVersion'] != 1
                or request['rulesVersion'] != 'r10' or request['preconditionMode'] != preconditions.ACTOR_STATE
                or request['commandId'] != step['commandId'] or not equal(step['action'], action)
                or type(request['expectedStateVersion']) is not int or request['expectedStateVersion'] != version
                or step['preconditionMode'] != preconditions.ACTOR_STATE or step['expectedStateVersion'] != version
                or step['status'] not in ('pending', 'unknown', 'committed', 'rejected')
                or not equal(snapshot['position'], position) or snapshot['inventoryWood'] != inventory
                or snapshot['stateVersion'] < version
                or workshop and (not valid_before(snapshot) or not equal(action, frozen['action'])
                    or any(not equal(snapshot[k], original[k]) for k in original))
                or not workshop and (set(action) != {'type', 'to'} or action['type'] != 'walk' or not nav.point(action['to'])
                                     or not _walk_before_valid(snapshot, original))):
            raise ValueError('Original workshop step, frozen action or before facts are damaged')
        command_ids.add(step['commandId'])
        if step['status'] in ('pending', 'unknown'):
            pending_count += 1
            expected = {'request': request, 'woodCost': action_cost(action) if workshop else 0,
                        'woodMoved': movement_cost(action) if workshop else 0,
                        'workshopBefore' if workshop else 'walkBefore': snapshot}
            if (i != len(steps) or not equal(saved['pending'], expected) or step['execution'] is not None
                    or step['receipt'] is not None or step['receiptInstanceId'] is not None
                    or step['workshopProof'] is not None or step['workshopEvidence'] is not None
                    or not equal(step['position'], position) or step['inventoryWood'] != inventory
                    or spent+expected['woodCost'] > limits['wood'] or moved+expected['woodMoved'] > limits['woodMoved']):
                raise ValueError('Original pending workshop request was changed or lost')
            continue
        committed = step['status'] == 'committed'
        receipt = step['receipt']
        if (not _receipt_valid(receipt, request, snapshot, step['receiptInstanceId'], committed=committed)
                or not equal(step['execution'], receipt['execution']) or step['stateVersion'] != receipt['stateVersion']
                or (committed and step.get('httpStatus') != 200)
                or not committed and (type(step.get('httpStatus')) is not int or not 400 <= step['httpStatus'] < 500)):
            raise ValueError('Original workshop receipt or execution proof is damaged')
        end_version = max(end_version, receipt['stateVersion'])
        if not committed:
            rejected_count += 1
            if (i != len(steps) or step.get('errorCode') != receipt['error']['code']
                    or not equal(step['position'], position) or step['inventoryWood'] != inventory
                    or step['workshopProof'] is not None or step['workshopEvidence'] is not None):
                raise ValueError('A rejected original action cannot acquire success facts or successors')
            continue
        if workshop:
            record = evidence(receipt, request, snapshot, step['workshopProof'])
            if record is None or not equal(step['workshopEvidence'], record) or completed:
                raise ValueError('Original workshop receipt, detail and event no longer agree')
            completed.append(record)
            spent += action_cost(action)
            moved += movement_cost(action)
            inventory = record['inventoryWood']
            if action['type'] == 'build_workshop': entities.append(record['entity']['entityId'])
            if action['type'] == 'craft_tool': tools.append(record['tool']['toolId'])
            if action['type'] == 'deposit_wood': deposited += record['quantity']
            if action['type'] == 'withdraw_wood': withdrawn += record['quantity']
        else:
            if (not nav.valid_walk_receipt(receipt, request, original['actorId'], snapshot)
                    or step['workshopProof'] is not None or step['workshopEvidence'] is not None
                    or step.get('blocked') is not receipt['result']['blocked']
                    or receipt['execution']['appliedOnStateVersion'] < snapshot['stateVersion']):
                raise ValueError('Original workshop walking evidence is damaged')
            position = receipt['result']['position']
            if receipt['result']['blocked'] and (i != len(steps) or not saved['terminal']):
                raise ValueError('A blocked walk cannot silently continue')
        version = receipt['stateVersion']
        if not equal(step['position'], position) or step['inventoryWood'] != inventory:
            raise ValueError('Workshop step summary differs from its original confirmed result')
    done = bool(completed)
    observed_position = latest['self']['position'] if latest['stateVersion'] >= version else position
    returned = nav.near(observed_position, mission['origin'])
    expected_facts = {'goalReached': done, 'returned': returned, 'workshopCompleted': done,
                      'workshopAction': completed[0] if done else None, 'woodClaimed': 0, 'woodGathered': 0,
                      'woodTransferred': 0, 'woodDeposited': deposited, 'woodWithdrawn': withdrawn,
                      'createdEntityIds': entities, 'createdToolIds': tools,
                      'startStateVersion': initial['stateVersion'], 'endStateVersion': end_version}
    if (any(not equal(facts.get(k), v) for k, v in expected_facts.items())
            or used['wood'] != spent or used['woodMoved'] != moved
            or (saved['pending'] is not None) != (pending_count == 1) or pending_count > 1
            or saved['actorStateVersion'] != version or not equal(saved['confirmedPosition'], position)
            or saved['confirmedInventoryWood'] != inventory
            or rejected_count and not saved['terminal']
            or mission['status'] == 'completed' and (not done or frozen['returnToOrigin'] and not returned
                                                   or saved['pending'] is not None or not saved['terminal'])
            or saved['terminal'] and saved['pending'] is not None
            or done and (not isinstance(facts.get('verifiedAtUtc'), str)
                         or datetime.fromisoformat(facts['verifiedAtUtc'].replace('Z', '+00:00')).utcoffset() is None)
            or not done and facts.get('verifiedAtUtc') is not None):
        raise ValueError('Workshop completion, budget or pending summaries are inconsistent')
    if preconditions.saved_mode(state) != preconditions.ACTOR_STATE:
        raise ValueError('Original workshop task cannot change its command mode')


class QueryBudget(RuntimeError):
    pass


def run_mission(client, spec, state_path, choose=None, *, max_steps=None):
    """Run one fixed action; the optional selector is intentionally never called."""
    from resident_mission import _lock, _save
    spec = normalize_spec(spec)
    if max_steps is not None and (type(max_steps) is not int or not 0 <= max_steps <= 1000):
        raise ValueError('max_steps must be an integer from 0 to 1000')
    path = Path(state_path).resolve()
    endpoint = {'url': client.url.rstrip('/'), 'prefix': client.prefix}
    goal, frozen = spec['goals'][0], spec['goals'][0]['workshop']
    with _lock(path):
        state = None
        raw = json.loads(path.read_text()) if path.exists() else None
        if raw is None:
            raw = {'schemaVersion': 1, 'kind': STARTUP, 'spec': deepcopy(spec), 'endpoint': endpoint,
                   'startedEpoch': time.time(), 'used': {'queries': 0, 'seconds': 0}, 'queries': []}
            _save(path, raw)
        if isinstance(raw, dict) and raw.get('kind') == STARTUP:
            if not _startup_valid(raw, spec, endpoint):
                raise ValueError('Original workshop startup or query budget is damaged')
            client.bind_instance(frozen['worldInstanceId'])
            if raw['used']['queries'] >= spec['budgets']['queries'] or time.time()-raw['startedEpoch'] >= spec['budgets']['seconds']:
                raise QueryBudget('Original workshop startup budget is exhausted')
            raw['used']['queries'] += 1
            raw['queries'].append({'index': raw['used']['queries'], 'kind': 'observation'})
            raw['used']['seconds'] = max(raw['used']['seconds'], time.time()-raw['startedEpoch'])
            _save(path, raw)
            observed = client.observe()
            if getattr(client, 'response_instance_id', None) != frozen['worldInstanceId']:
                raise WorldBindingError('Initial workshop response has no original instance proof')
            state = _new_state(observed, spec, raw, endpoint)
            _save(path, state)
        else:
            state = raw
            validate_saved(state, spec, endpoint)
            if state['_state']['terminal'] or state['mission']['status'] == 'completed':
                return _report(state)
            client.bind_instance(frozen['worldInstanceId'])
        saved, mission, facts = state['_state'], state['mission'], state['facts']
        used, limits = state['budget']['used'], state['budget']['limits']
        original = saved['workshopBinding']
        handled, fresh = 0, False

        def save():
            used['seconds'] = max(used['seconds'], time.time()-saved['startedEpoch'])
            _save(path, state)

        def finish(status, reason, terminal=False):
            mission.update(status=status, reason=reason, updatedAtUtc=_utc())
            saved['terminal'] = bool(terminal)
            actual_position = (saved['latest']['self']['position']
                if saved['latest']['stateVersion'] >= saved['actorStateVersion'] else saved['confirmedPosition'])
            facts['returned'] = nav.near(actual_position, mission['origin'])
            state['feedback'] = {'summary': ('原动作三方证据已确认；返程已确认' if frozen['returnToOrigin']
                                              else '原动作三方证据已确认；本任务未要求返程') if status == 'completed' else reason,
                                 'issues': [] if status in ('completed', 'paused') else [reason], 'suggestions': []}
            save()
            return _report(state)

        def query(call, kind):
            if used['queries'] >= limits['queries']:
                raise QueryBudget('Original workshop query budget is exhausted')
            used['queries'] += 1
            saved['queries'].append({'index': used['queries'], 'kind': kind})
            save()
            response = call()
            instance = getattr(client, 'response_instance_id', None)
            if instance != original['worldInstanceId']:
                raise WorldBindingError('Workshop query response does not prove the original instance')
            return response, instance

        def observe():
            observed, _ = query(client.observe, 'observation')
            if not ready(observed, goal, original) or observed['stateVersion'] < saved['latest']['stateVersion']:
                raise WorldBindingError('Original workshop identity, target, capability or monotonic state changed')
            saved['latest'] = deepcopy(observed)
            saved['binding'].update(endpoint)
            state['world'] = _world(observed)
            facts['endStateVersion'] = max(facts['endStateVersion'], observed['stateVersion'])
            save()
            return observed

        def unknown(reason):
            if saved['pending'] is not None:
                state['steps'][-1]['status'] = 'unknown'
            return finish('unknown', reason)

        while True:
            pending = saved['pending']
            if pending is None:
                if facts['workshopCompleted'] and (not frozen['returnToOrigin'] or nav.near(saved['confirmedPosition'], mission['origin'])):
                    return finish('completed', 'workshop_action_and_return_verified' if frozen['returnToOrigin'] else 'workshop_action_verified', True)
                if max_steps is not None and handled >= max_steps:
                    return finish('paused', 'max_steps')
                save()
                if used['seconds'] >= limits['seconds']:
                    return finish('budget_exhausted', 'seconds')
                if used['commands'] >= limits['commands']:
                    return finish('budget_exhausted', 'commands')
                try:
                    observed = observe()
                except QueryBudget:
                    return finish('budget_exhausted', 'queries')
                except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                    return unknown('workshop_observation_unavailable:' + type(error).__name__)
                if (not equal(observed['self']['position'], saved['confirmedPosition'])
                        or observed['self']['inventory']['wood'] != saved['confirmedInventoryWood']):
                    return finish('blocked', 'workshop_actor_changed_outside_task', True)
                if facts['workshopCompleted']:
                    route = nav.navigation(observed).route(observed['self']['position'], mission['origin'])
                    if route is None:
                        return finish('blocked', 'workshop_return_unreachable')
                    if not route:
                        return finish('completed', 'workshop_action_and_return_verified', True)
                    action, issue = {'type': 'walk', 'to': list(route[0])}, None
                else:
                    action, issue = plan(observed, goal, original)
                if issue:
                    return finish('blocked', issue)
                workshop = action['type'] in PERMISSIONS
                cost = action_cost(action) if workshop else 0
                moved = movement_cost(action) if workshop else 0
                if used['wood']+cost > limits['wood'] or used['woodMoved']+moved > limits['woodMoved']:
                    return finish('budget_exhausted', 'wood' if used['wood']+cost > limits['wood'] else 'woodMoved')
                if not workshop:
                    start, target = observed['self']['position'], action['to']
                    distance = nav.distance(start, target)
                    step = min(distance, observed['movement']['maxStepDistance'])
                    action['to'] = [a+(b-a)*step/distance for a, b in zip(start, target)]
                    time.sleep(step/observed['movement']['speed'] + .005)
                    save()
                    if used['seconds'] >= limits['seconds']:
                        return finish('budget_exhausted', 'seconds')
                # Observation and route planning can consume the remaining time.
                save()
                if used['seconds'] >= limits['seconds']:
                    return finish('budget_exhausted', 'seconds')
                intent = {'schemaVersion': 1, 'rulesVersion': 'r10', 'commandId': uuid.uuid4().hex,
                          'preconditionMode': preconditions.ACTOR_STATE,
                          'expectedStateVersion': saved['actorStateVersion'], 'action': deepcopy(action)}
                snapshot = before(observed, goal, original) if workshop else {
                    'version': 1, **{k: original[k] for k in ('worldInstanceId', 'actorId', 'operatorId')},
                    'position': deepcopy(observed['self']['position']), 'inventoryWood': observed['self']['inventory']['wood'],
                    'stateVersion': observed['stateVersion'], 'maxStepDistance': observed['movement']['maxStepDistance']}
                pending = {'request': intent, 'woodCost': cost, 'woodMoved': moved,
                           'workshopBefore' if workshop else 'walkBefore': snapshot}
                saved['pending'] = deepcopy(pending)
                used['commands'] += 1
                state['steps'].append({'index': used['commands'], 'commandId': intent['commandId'], 'action': deepcopy(action),
                    'reason': '执行明确授权的原工作台动作' if workshop else '返回原起点' if facts['workshopCompleted'] else '前往原目标的可达操作侧',
                    'status': 'pending', 'stateVersion': observed['stateVersion'], 'position': deepcopy(snapshot['position']),
                    'inventoryWood': snapshot['inventoryWood'], 'preconditionMode': preconditions.ACTOR_STATE,
                    'expectedStateVersion': intent['expectedStateVersion'], 'execution': None,
                    'request': deepcopy(intent), 'before': deepcopy(snapshot), 'receipt': None, 'receiptInstanceId': None,
                    'workshopProof': None, 'workshopEvidence': None})
                mission.update(status='running', reason='workshop_command_pending')
                save()  # Every original ID and exact before fact exists before POST.
                fresh = True
            intent = pending['request']
            action = intent['action']
            workshop = action['type'] in PERMISSIONS
            snapshot = pending['workshopBefore' if workshop else 'walkBefore']
            step = state['steps'][-1]
            try:
                if not fresh:
                    (status, receipt), receipt_instance = query(
                        lambda: client.request('GET', client.prefix+'/commands/'+intent['commandId']), 'receipt')
                    absent = (status == 404 and envelope(receipt, original, error=True)
                              and receipt.get('commandId') == intent['commandId']
                              and isinstance(receipt.get('error'), dict) and receipt['error'].get('code') == 'COMMAND_NOT_FOUND'
                              and receipt['error'].get('mutated') is False)
                    if absent:
                        save()
                        if used['seconds'] >= limits['seconds'] or max_steps is not None and handled >= max_steps:
                            return finish('budget_exhausted' if used['seconds'] >= limits['seconds'] else 'paused', 'original_pending_not_sent')
                        observe()  # Only the original supported capability may resend the original request.
                        save()
                        if max(used['seconds'], time.time()-saved['startedEpoch']) >= limits['seconds']:
                            return finish('budget_exhausted', 'seconds_pending_retained')
                        status, receipt = client.command(deepcopy(intent))
                        receipt_instance = getattr(client, 'response_instance_id', None)
                else:
                    save()
                    if max(used['seconds'], time.time()-saved['startedEpoch']) >= limits['seconds']:
                        return finish('budget_exhausted', 'seconds_pending_retained')
                    status, receipt = client.command(deepcopy(intent))
                    receipt_instance = getattr(client, 'response_instance_id', None)
                fresh = False
                committed = status == 200 and _receipt_valid(receipt, intent, snapshot, receipt_instance, committed=True)
                rejected = (type(status) is int and 400 <= status < 500 and status not in (401, 412, 428)
                            and _receipt_valid(receipt, intent, snapshot, receipt_instance, committed=False))
                if not committed and not rejected:
                    return unknown('workshop_original_receipt_unconfirmed')
                proof = record = None
                if committed and workshop:
                    cursor = receipt.get('eventCursor')
                    if not preconditions.integer(cursor) or cursor < 1:
                        return unknown('workshop_original_event_cursor_invalid')
                    (detail_status, detail), detail_instance = query(lambda: client.request('GET', client.prefix+
                        '/workshop/actions/'+original['actorId']+'/'+intent['commandId']), 'workshop_detail')
                    if detail_status != 200:
                        return unknown('workshop_original_detail_unavailable')
                    (event_status, events), event_instance = query(lambda: client.request('GET', client.prefix+
                        '/events?after='+str(cursor-1)), 'workshop_event')
                    if event_status != 200:
                        return unknown('workshop_original_event_unavailable')
                    proof = {'receiptInstanceId': receipt_instance, 'detailInstanceId': detail_instance,
                             'eventInstanceId': event_instance, 'detail': detail, 'events': events}
                    record = evidence(receipt, intent, snapshot, proof)
                    if record is None:
                        return unknown('workshop_original_three_records_disagree')
                if committed and not workshop and (not nav.valid_walk_receipt(receipt, intent, original['actorId'], snapshot)
                        or receipt['execution']['appliedOnStateVersion'] < snapshot['stateVersion']):
                    return unknown('workshop_walk_unconfirmed')
            except QueryBudget:
                return finish('budget_exhausted', 'queries_pending_retained')
            except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                return unknown('workshop_original_pending_retained:' + type(error).__name__)
            step.update(status='committed' if committed else 'rejected', stateVersion=receipt['stateVersion'],
                        httpStatus=status, execution=deepcopy(receipt['execution']), receipt=deepcopy(receipt),
                        receiptInstanceId=receipt_instance, workshopProof=deepcopy(proof), workshopEvidence=deepcopy(record))
            facts['endStateVersion'] = max(facts['endStateVersion'], receipt['stateVersion'])
            saved['binding'].update(endpoint)
            if committed:
                saved['actorStateVersion'] = receipt['stateVersion']
                if workshop:
                    facts.update(goalReached=True, workshopCompleted=True, workshopAction=deepcopy(record), verifiedAtUtc=_utc())
                    saved['confirmedInventoryWood'] = record['inventoryWood']
                    used['wood'] += pending['woodCost']
                    used['woodMoved'] += pending['woodMoved']
                    if action['type'] == 'build_workshop': facts['createdEntityIds'].append(record['entity']['entityId'])
                    if action['type'] == 'craft_tool': facts['createdToolIds'].append(record['tool']['toolId'])
                    if action['type'] == 'deposit_wood': facts['woodDeposited'] += record['quantity']
                    if action['type'] == 'withdraw_wood': facts['woodWithdrawn'] += record['quantity']
                else:
                    saved['confirmedPosition'] = deepcopy(receipt['result']['position'])
                    step['blocked'] = receipt['result']['blocked']
            else:
                step['errorCode'] = receipt['error']['code']
            step.update(position=deepcopy(saved['confirmedPosition']), inventoryWood=saved['confirmedInventoryWood'])
            facts['returned'] = nav.near(saved['confirmedPosition'], mission['origin'])
            saved['pending'] = None
            handled += 1
            if rejected:
                return finish('blocked', 'command_rejected:'+receipt['error']['code'], True)
            if not workshop and receipt['result']['blocked']:
                return finish('blocked', 'workshop_walk_collision_stopped', True)
            # A terminal receipt and its terminal flag are saved together by
            # finish above; no crash may expose a non-terminal rejected step.
            save()
