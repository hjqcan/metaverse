"""One authorized forestry action, original-object waiting and durable evidence.

Environmental growth is never a resident harvest. Every subsequent application
or generation requires a new explicit task; the selector is never invoked.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
import uuid

import command_preconditions as preconditions
import continuous_navigation as nav
from foundation_agent import valid_world_instance, WorldBindingError
from resident_entity_notes import equal, identifier
import resident_workshop as workshop

CAPABILITY = 'forestry-v1'
STARTUP = 'forestry-task-startup'
MAX_INTEGER = 2**53 - 1
PERMISSIONS = {
    'craft_forestry_tool': 'allowCraftForestryTool', 'reserve_forest': 'allowReserveForest',
    'cancel_forest_reservation': 'allowCancelForestReservation', 'collect_seed': 'allowCollectSeed',
    'plant_tree': 'allowPlantTree', 'harvest_tree': 'allowHarvestTree',
}
REMOTE_ACTIONS = {'reserve_forest', 'cancel_forest_reservation'}
POLICY = {'seedIntervalMs': 60000, 'nurseryCapacity': 4, 'preparationLeaseMs': 90000,
          'growthMs': 120000, 'harvestLeaseMs': 60000, 'woodPerTree': 3,
          'seedsPerHarvest': 1, 'groupLimit': 1, 'interactReach': 1.6}
PLOTS = {'forest-west-north': [7, 12], 'forest-west-south': [7, 16],
         'forest-east-north': [21, 7], 'forest-east-far': [29, 5]}
RECIPE = {'id': 'wooden_axe.v1', 'definitionId': 'wooden_axe', 'woodCost': 2,
          'requiresWorkbench': True}
RESERVATION_FIELDS = set('reservationId actorId operatorId commandId requestedAtMs queueOrder status plotId plantId reservedSeed grantedAtMs expiresAtMs'.split())
RESERVATION_IDENTITY = 'reservationId actorId operatorId commandId requestedAtMs queueOrder'.split()
PLANT_FIELDS = set('plantId plotId planterActorId operatorId reservationId commandId plantedAtMs maturesAtMs state standingWood stateVersion eventCursor matureEventCursor harvestActorId harvestCommandId harvestEventCursor'.split())
PLANT_IDENTITY = 'plantId plotId planterActorId operatorId reservationId commandId plantedAtMs maturesAtMs stateVersion eventCursor'.split()
DETAIL_FIELDS = set('capabilityVersion authorActorId operatorId commandId action position serviceMs stateVersion eventCursor completedAtUtc inventoryWoodBefore inventoryWood seedsBefore seeds nurseryStockBefore nurseryStock reservationBefore reservation plantBefore plant tool'.split())
BEFORE_FIELDS = set('version worldInstanceId actorId operatorId adoption target tool reservationIdentity plantIdentity action position inventoryWood seeds nurseryStock serviceMs stateVersion reservation plant toolIds reservationIds plantIds'.split())
QUERY_KINDS = {'observation', 'receipt', 'forestry_detail', 'forestry_event'}
MATERIAL_KEYS = ('wood', 'woodHarvested', 'seedsCollected', 'seedsPlanted', 'seedsHarvested')
LIMITS = {'commands': (1, 1000), 'queries': (1, 5000), 'wood': (0, 12), 'woodHarvested': (0, 12),
          'seedsCollected': (0, 4), 'seedsPlanted': (0, 4), 'seedsHarvested': (0, 4),
          'seconds': (1, 600), 'modelCalls': (0, 0)}


def integer(value):
    return type(value) is int and 0 <= value <= MAX_INTEGER


def wood(value):
    return type(value) is int and 0 <= value <= 12


def subset(value, fields):
    return None if value is None else {key: deepcopy(value[key]) for key in fields}


def action_valid(action):
    if (not isinstance(action, dict) or not isinstance(action.get('type'), str)
            or action['type'] not in PERMISSIONS or type(action.get('capabilityVersion')) is not int
            or action['capabilityVersion'] != 1):
        return False
    fields = {'craft_forestry_tool': {'entityId', 'recipeId'}, 'reserve_forest': set(),
              'cancel_forest_reservation': {'reservationId'}, 'collect_seed': {'sourceId', 'reservationId'},
              'plant_tree': {'plotId', 'reservationId'}, 'harvest_tree': {'plantId', 'reservationId', 'toolId'}}[action['type']]
    if set(action) != {'type', 'capabilityVersion', *fields}:
        return False
    return (all(identifier(action[key]) for key in fields if key != 'recipeId')
            and (action['type'] != 'craft_forestry_tool' or action['recipeId'] == 'wooden_axe.v1')
            and (action['type'] != 'collect_seed' or action['sourceId'] == 'nursery-west')
            and (action['type'] != 'plant_tree' or action['plotId'] in PLOTS))


def uses(spec):
    return (isinstance(spec, dict) and isinstance(spec.get('goals'), list)
            and any(isinstance(goal, dict) and 'forestry' in goal for goal in spec['goals']))


def normalize_spec(value):
    if (not isinstance(value, dict) or set(value) != {'missionId', 'objective', 'goals', 'allowBuild', 'budgets', *PERMISSIONS.values()}
            or not isinstance(value['missionId'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value['missionId'])
            or not isinstance(value['objective'], str) or not 1 <= len(value['objective']) <= 500
            or value['allowBuild'] is not False or not isinstance(value['goals'], list) or len(value['goals']) != 1):
        raise ValueError('Forestry requires one explicit fixed task and no implicit legacy authority')
    goal = value['goals'][0]
    if (not isinstance(goal, dict) or set(goal) != {'id', 'label', 'target', 'forestry'}
            or not identifier(goal['id']) or not isinstance(goal['label'], str) or not goal['label']):
        raise ValueError('Invalid forestry goal')
    item = goal['forestry']
    if (not isinstance(item, dict) or set(item) != {'worldInstanceId', 'actorId', 'action', 'waitForReady', 'returnToOrigin'}
            or not valid_world_instance(item['worldInstanceId']) or not identifier(item['actorId'])
            or any(type(item[key]) is not bool for key in ('waitForReady', 'returnToOrigin'))
            or not action_valid(item['action'])):
        raise ValueError('Forestry requires the original instance, actor, complete action and explicit waiting/return choices')
    action = item['action']
    if action['type'] in REMOTE_ACTIONS:
        if goal['target'] is not None:
            raise ValueError('Non-spatial forestry actions require target:null and do not imply movement')
    elif not nav.point(goal['target']) or any(n < 0 for n in goal['target']):
        raise ValueError('A spatial forestry action requires its exact original target')
    if (action['type'] == 'collect_seed' and not equal(goal['target'], [7, 6])
            or action['type'] == 'plant_tree' and not equal(goal['target'], PLOTS[action['plotId']])):
        raise ValueError('Forestry target coordinates disagree with the named fixed facility')
    if any(type(value[p]) is not bool or value[p] is not (p == PERMISSIONS[action['type']]) for p in PERMISSIONS.values()):
        raise ValueError('Only the permission for this one forestry action may be enabled')
    limits = value['budgets']
    if (not isinstance(limits, dict) or set(limits) != set(LIMITS)
            or any(type(limits[k]) is not int or not lo <= limits[k] <= hi for k, (lo, hi) in LIMITS.items())):
        raise ValueError('Invalid bounded forestry budgets; model calls must be zero')
    return deepcopy(value)


def valid_adoption(value):
    return (isinstance(value, dict) and set(value) == {'worldInstanceId', 'adoptedServiceMs', 'stateVersion', 'eventCursor', 'baseStorageVersion'}
            and valid_world_instance(value['worldInstanceId'])
            and all(integer(value[k]) for k in ('adoptedServiceMs', 'stateVersion', 'eventCursor', 'baseStorageVersion'))
            and value['eventCursor'] > 0 and value['baseStorageVersion'] == 13)


def valid_tool(tool):
    return (isinstance(tool, dict) and set(tool) == workshop.TOOL_FIELDS
            and all(identifier(tool[k]) for k in ('toolId', 'ownerActorId', 'workbenchId', 'commandId'))
            and tool['definitionId'] == 'wooden_axe' and type(tool['definitionVersion']) is int
            and tool['definitionVersion'] == 1 and type(tool['embodiedWood']) is int and tool['embodiedWood'] == 2
            and integer(tool['stateVersion']) and integer(tool['eventCursor']) and tool['eventCursor'] > 0)


def valid_reservation(r, *, active=False):
    if (not isinstance(r, dict) or set(r) != RESERVATION_FIELDS
            or not all(identifier(r[k]) for k in ('reservationId', 'actorId', 'operatorId', 'commandId'))
            or not all(integer(r[k]) for k in ('requestedAtMs', 'queueOrder', 'reservedSeed'))
            or r['queueOrder'] < 1 or r['reservedSeed'] > 1
            or r['status'] not in ('queued', 'preparing', 'growing', 'harvesting', 'completed', 'cancelled', 'expired')
            or active and r['status'] not in ('queued', 'preparing', 'growing', 'harvesting')
            or r['plotId'] is not None and r['plotId'] not in PLOTS
            or r['plantId'] is not None and not identifier(r['plantId'])
            or any(r[k] is not None and not integer(r[k]) for k in ('grantedAtMs', 'expiresAtMs'))):
        return False
    if r['grantedAtMs'] is not None and (r['plotId'] is None or r['grantedAtMs'] < r['requestedAtMs']):
        return False
    if r['expiresAtMs'] is not None and (r['grantedAtMs'] is None or r['expiresAtMs'] < r['grantedAtMs']):
        return False
    if r['status'] == 'queued':
        return all(r[k] is None for k in ('plotId', 'plantId', 'grantedAtMs', 'expiresAtMs')) and r['reservedSeed'] == 0
    if r['status'] == 'preparing':
        return (r['plotId'] in PLOTS and r['plantId'] is None and integer(r['grantedAtMs'])
                and r['expiresAtMs'] == r['grantedAtMs'] + 90000)
    if r['status'] in ('growing', 'harvesting'):
        return (r['plotId'] in PLOTS and identifier(r['plantId']) and integer(r['grantedAtMs'])
                and r['reservedSeed'] == 0
                and (r['expiresAtMs'] is None if r['status'] == 'growing' else integer(r['expiresAtMs'])))
    return r['reservedSeed'] == 0


def valid_plant(p):
    if (not isinstance(p, dict) or set(p) != PLANT_FIELDS or p['plotId'] not in PLOTS
            or not all(identifier(p[k]) for k in ('plantId', 'planterActorId', 'operatorId', 'reservationId', 'commandId'))
            or not all(integer(p[k]) for k in ('plantedAtMs', 'maturesAtMs', 'standingWood', 'stateVersion', 'eventCursor'))
            or p['eventCursor'] < 1 or p['maturesAtMs'] != p['plantedAtMs'] + 120000
            or p['state'] not in ('growing', 'mature', 'harvested')):
        return False
    if p['state'] == 'growing':
        return p['standingWood'] == 0 and all(p[k] is None for k in ('matureEventCursor', 'harvestActorId', 'harvestCommandId', 'harvestEventCursor'))
    if not integer(p['matureEventCursor']) or p['matureEventCursor'] <= p['eventCursor']:
        return False
    if p['state'] == 'mature':
        return p['standingWood'] == 3 and all(p[k] is None for k in ('harvestActorId', 'harvestCommandId', 'harvestEventCursor'))
    return (p['standingWood'] == 0 and identifier(p['harvestActorId']) and identifier(p['harvestCommandId'])
            and integer(p['harvestEventCursor']) and p['harvestEventCursor'] > p['matureEventCursor'])


def rectangle(position):
    x, z = position
    return [x - 1.5, z - 1.5, x + 1.5, z + 1.5]


def supported(observed):
    try:
        return _supported(observed)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def _supported(observed):
    if not workshop.supported(observed):
        return False
    cap = observed.get('forestry')
    if (not isinstance(cap, dict) or set(cap) != {'capability', 'version', 'adoption', 'policy', 'nursery', 'plots', 'plants', 'reservations', 'seeds', 'tools', 'recipes'}
            or cap['capability'] != CAPABILITY or type(cap['version']) is not int or cap['version'] != 1
            or not valid_adoption(cap['adoption']) or cap['adoption']['worldInstanceId'] != observed['world']['instanceId']
            or cap['adoption']['stateVersion'] > observed['stateVersion'] or cap['adoption']['eventCursor'] > observed['eventCursor']
            or not equal(cap['policy'], POLICY)
            or any(type(cap['policy'][k]) is not int for k in POLICY if k != 'interactReach')
            or not integer(cap['seeds']) or not equal(cap['recipes'], [RECIPE])
            or type(cap['recipes'][0]['woodCost']) is not int):
        return False
    nursery = cap['nursery']
    if (not isinstance(nursery, dict) or set(nursery) != set('sourceId position radius buildExclusion serviceMs nextProductionAtMs productionPeriod generatedSeeds stockSeeds reservedSeeds freeSeeds'.split())
            or nursery['sourceId'] != 'nursery-west' or not equal(nursery['position'], [7, 6])
            or type(nursery['radius']) not in (int, float) or nursery['radius'] != .3
            or not equal(nursery['buildExclusion'], rectangle([7, 6]))
            or not all(integer(nursery[k]) for k in ('serviceMs', 'nextProductionAtMs', 'productionPeriod', 'generatedSeeds', 'stockSeeds', 'reservedSeeds', 'freeSeeds'))
            or nursery['serviceMs'] < cap['adoption']['adoptedServiceMs']
            or nursery['nextProductionAtMs'] <= nursery['serviceMs']
            or not 0 <= nursery['reservedSeeds'] <= nursery['stockSeeds'] <= 4
            or nursery['freeSeeds'] != nursery['stockSeeds'] - nursery['reservedSeeds']):
        return False
    plots, plants, reservations, tools = (cap[k] for k in ('plots', 'plants', 'reservations', 'tools'))
    if (not isinstance(plots, list) or len(plots) != 4 or len({p['plotId'] for p in plots}) != 4
            or any(set(p) != {'plotId', 'position', 'radius', 'buildExclusion'} or p['plotId'] not in PLOTS
                   or not equal(p['position'], PLOTS[p['plotId']]) or type(p['radius']) not in (int, float) or p['radius'] != .45
                   or not equal(p['buildExclusion'], rectangle(p['position'])) for p in plots)
            or not isinstance(plants, list) or len(plants) > 4
            or not all(valid_plant(p) and p['state'] != 'harvested' and p['stateVersion'] <= observed['stateVersion']
                       and p['eventCursor'] <= observed['eventCursor'] and p['plantedAtMs'] <= nursery['serviceMs'] for p in plants)
            or len({p['plotId'] for p in plants}) != len(plants) or len({p['plantId'] for p in plants}) != len(plants)
            or not isinstance(reservations, list) or not all(valid_reservation(r, active=True) for r in reservations)
            or len({r['reservationId'] for r in reservations}) != len(reservations)
            or len({r['operatorId'] for r in reservations}) != len(reservations)
            or len({r['plotId'] for r in reservations if r['plotId'] is not None}) != sum(r['plotId'] is not None for r in reservations)
            or sum(r['reservedSeed'] for r in reservations) != nursery['reservedSeeds']
            or not isinstance(tools, list) or not all(valid_tool(t) and t['ownerActorId'] == observed['self']['actorId']
                and t['stateVersion'] <= observed['stateVersion'] and t['eventCursor'] <= observed['eventCursor'] for t in tools)
            or len({t['toolId'] for t in tools}) != len(tools)):
        return False
    for r in reservations:
        if r['status'] in ('growing', 'harvesting'):
            p = next((p for p in plants if p['plantId'] == r['plantId']), None)
            if p is None or p['plotId'] != r['plotId'] or (r['status'] == 'growing') != (p['state'] == 'growing'):
                return False
    obstacles = observed['terrain']['obstacles']
    expected = {'nursery-west': ('forestry_nursery', [7, 6], .3),
                **{p['plantId']: ('forestry_tree', PLOTS[p['plotId']], .45) for p in plants}}
    actual = [o for o in obstacles if o.get('kind') in ('forestry_nursery', 'forestry_tree')]
    return (len(actual) == len(expected) and len({o['id'] for o in actual}) == len(actual)
            and all(o['id'] in expected and equal([o['kind'], o['position'], o['radius']], list(expected[o['id']])) for o in actual))


def original_reservation(observed, action):
    return next((r for r in observed['forestry']['reservations'] if r['reservationId'] == action.get('reservationId')), None)


def original_plant(observed, action):
    return next((p for p in observed['forestry']['plants'] if p['plantId'] == action.get('plantId')), None)


def binding(observed, goal):
    if not supported(observed):
        raise ValueError('Forestry capability, policy, geometry or original workshop contract is unsupported')
    task, cap = goal['forestry'], observed['forestry']
    if task['worldInstanceId'] != observed['world']['instanceId'] or task['actorId'] != observed['self']['actorId']:
        raise WorldBindingError('Forestry task belongs to another original instance or resident')
    action = task['action']
    reservation = original_reservation(observed, action)
    plant = original_plant(observed, action)
    if 'reservationId' in action and (reservation is None or reservation['actorId'] != task['actorId']
            or reservation['operatorId'] != observed['identity']['operatorId']):
        raise ValueError('The original resident reservation is not available')
    if action['type'] == 'harvest_tree' and (plant is None or reservation['plantId'] != action['plantId']
            or not equal(PLOTS[plant['plotId']], goal['target'])):
        raise ValueError('The original plant and its assigned reservation are unavailable')
    target = None
    if action['type'] == 'craft_forestry_tool':
        target = next((e for e in observed['entities'] if e['entityId'] == action['entityId']), None)
        if not workshop.valid_entity(target, 'workbench') or not equal(target['position'], goal['target']):
            raise ValueError('The original public workbench is unavailable')
    elif action['type'] == 'collect_seed':
        target = subset(cap['nursery'], ('sourceId', 'position', 'radius', 'buildExclusion'))
    elif action['type'] in ('plant_tree', 'harvest_tree'):
        plot_id = action['plotId'] if action['type'] == 'plant_tree' else plant['plotId']
        target = next(p for p in cap['plots'] if p['plotId'] == plot_id)
        if reservation['plotId'] not in (None, plot_id):
            raise ValueError('The original reservation was assigned to a different explicit plot')
    tool = None
    if action['type'] == 'harvest_tree':
        tool = next((t for t in cap['tools'] if t['toolId'] == action['toolId']), None)
        if not valid_tool(tool) or tool['ownerActorId'] != task['actorId']:
            raise ValueError('The named original axe does not belong to this resident')
    return {'version': 1, 'worldInstanceId': task['worldInstanceId'], 'actorId': task['actorId'],
            'operatorId': observed['identity']['operatorId'], 'adoption': deepcopy(cap['adoption']),
            'target': deepcopy(target), 'tool': deepcopy(tool),
            'reservationIdentity': subset(reservation, RESERVATION_IDENTITY),
            'plantIdentity': subset(plant, PLANT_IDENTITY)}


def ready(observed, goal, original):
    """Keep immutable bindings while their public lifecycle is allowed to advance.

    Missing active rows do not disprove an old pending result. Planning handles
    that condition only after the original receipt has been resolved.
    """
    try:
        if (not supported(observed) or observed['world']['instanceId'] != original['worldInstanceId']
                or observed['self']['actorId'] != original['actorId']
                or observed['identity']['operatorId'] != original['operatorId']
                or not equal(observed['forestry']['adoption'], original['adoption'])):
            return False
        action, cap = goal['forestry']['action'], observed['forestry']
        if action['type'] == 'craft_forestry_tool':
            current = next((e for e in observed['entities'] if e['entityId'] == action['entityId']), None)
            if not equal(current, original['target']):
                return False
        if original['tool'] is not None:
            tool = next((t for t in cap['tools'] if t['toolId'] == original['tool']['toolId']), None)
            if not equal(tool, original['tool']):
                return False
        reservation, plant = original_reservation(observed, action), original_plant(observed, action)
        return ((reservation is None or equal(subset(reservation, RESERVATION_IDENTITY), original['reservationIdentity']))
                and (plant is None or equal(subset(plant, PLANT_IDENTITY), original['plantIdentity'])))
    except (KeyError, TypeError, ValueError):
        return False


def assignment(observed, action):
    r = original_reservation(observed, action)
    return None if r is None or r['plotId'] is None else subset(r, ('reservationId', 'plotId', 'grantedAtMs'))


def costs(action):
    result = dict.fromkeys(MATERIAL_KEYS, 0)
    key = {'craft_forestry_tool': 'wood', 'collect_seed': 'seedsCollected', 'plant_tree': 'seedsPlanted'}.get(action['type'])
    if key:
        result[key] = 2 if key == 'wood' else 1
    if action['type'] == 'harvest_tree':
        result.update(woodHarvested=3, seedsHarvested=1)
    return result


def before(observed, goal, original):
    if not ready(observed, goal, original):
        raise ValueError('Original forestry identity or capability changed before submission')
    action, cap = goal['forestry']['action'], observed['forestry']
    return {**deepcopy(original), 'action': deepcopy(action), 'position': deepcopy(observed['self']['position']),
            'inventoryWood': observed['self']['inventory']['wood'], 'seeds': cap['seeds'],
            'nurseryStock': cap['nursery']['stockSeeds'], 'serviceMs': cap['nursery']['serviceMs'],
            'stateVersion': observed['stateVersion'], 'reservation': deepcopy(original_reservation(observed, action)),
            'plant': deepcopy(original_plant(observed, action)), 'toolIds': [t['toolId'] for t in cap['tools']],
            'reservationIds': [r['reservationId'] for r in cap['reservations']], 'plantIds': [p['plantId'] for p in cap['plants']]}


def valid_before(value):
    try:
        return _valid_before(value)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def _valid_before(v):
    if (not isinstance(v, dict) or set(v) != BEFORE_FIELDS or type(v['version']) is not int or v['version'] != 1
            or not valid_world_instance(v['worldInstanceId']) or not all(identifier(v[k]) for k in ('actorId', 'operatorId'))
            or not valid_adoption(v['adoption']) or v['adoption']['worldInstanceId'] != v['worldInstanceId']
            or not action_valid(v['action']) or not nav.point(v['position']) or not wood(v['inventoryWood'])
            or not all(integer(v[k]) for k in ('seeds', 'nurseryStock', 'serviceMs', 'stateVersion'))
            or v['nurseryStock'] > 4 or v['serviceMs'] < v['adoption']['adoptedServiceMs']
            or v['stateVersion'] < v['adoption']['stateVersion']
            or any(not isinstance(v[k], list) or not all(identifier(i) for i in v[k]) or len(set(v[k])) != len(v[k])
                   for k in ('toolIds', 'reservationIds', 'plantIds'))):
        return False
    a, r, p, t = v['action'], v['reservation'], v['plant'], v['tool']
    kind = a['type']
    if 'reservationId' in a:
        if (not valid_reservation(r, active=True) or r['reservationId'] != a['reservationId']
                or r['actorId'] != v['actorId'] or r['operatorId'] != v['operatorId']
                or r['reservationId'] not in v['reservationIds']
                or not equal(subset(r, RESERVATION_IDENTITY), v['reservationIdentity'])):
            return False
    elif r is not None or v['reservationIdentity'] is not None:
        return False
    if kind == 'harvest_tree':
        if (not valid_plant(p) or p['state'] != 'mature' or p['plantId'] != a['plantId']
                or p['plantId'] not in v['plantIds'] or not equal(subset(p, PLANT_IDENTITY), v['plantIdentity'])
                or not valid_tool(t) or t['toolId'] != a['toolId'] or t['ownerActorId'] != v['actorId']
                or t['toolId'] not in v['toolIds'] or r['status'] != 'harvesting' or r['plantId'] != p['plantId']
                or r['plotId'] != p['plotId'] or v['inventoryWood'] > 9 or v['seeds'] >= MAX_INTEGER):
            return False
    elif p is not None or t is not None or v['plantIdentity'] is not None:
        return False
    if kind in REMOTE_ACTIONS:
        return v['target'] is None and (kind == 'reserve_forest' or r['status'] in ('queued', 'preparing'))
    target = v['target']
    if not isinstance(target, dict) or not nav.point(target.get('position')) or nav.distance(v['position'], target['position']) > 1.6 + 1e-8:
        return False
    if kind == 'craft_forestry_tool':
        return workshop.valid_entity(target, 'workbench') and target['entityId'] == a['entityId'] and v['inventoryWood'] >= 2
    if kind == 'collect_seed':
        return (equal(target, {'sourceId': 'nursery-west', 'position': [7, 6], 'radius': .3, 'buildExclusion': rectangle([7, 6])})
                and r['status'] == 'preparing' and r['reservedSeed'] == 1 and v['seeds'] < MAX_INTEGER)
    plot_id = a['plotId'] if kind == 'plant_tree' else p['plotId']
    return (equal(target, {'plotId': plot_id, 'position': PLOTS[plot_id], 'radius': .45, 'buildExclusion': rectangle(PLOTS[plot_id])})
            and r['plotId'] == plot_id
            and (kind == 'harvest_tree' or r['status'] == 'preparing' and v['seeds'] >= 1))


def valid_detail(d):
    try:
        return (isinstance(d, dict) and set(d) == DETAIL_FIELDS and type(d['capabilityVersion']) is int
                and d['capabilityVersion'] == 1 and all(identifier(d[k]) for k in ('authorActorId', 'operatorId', 'commandId'))
                and action_valid(d['action']) and nav.point(d['position'])
                and all(integer(d[k]) for k in ('serviceMs', 'stateVersion', 'eventCursor', 'seedsBefore', 'seeds', 'nurseryStockBefore', 'nurseryStock'))
                and d['eventCursor'] > 0 and d['nurseryStockBefore'] <= 4 and d['nurseryStock'] <= 4
                and wood(d['inventoryWoodBefore']) and wood(d['inventoryWood'])
                and all(d[k] is None or valid_reservation(d[k]) for k in ('reservationBefore', 'reservation'))
                and all(d[k] is None or valid_plant(d[k]) for k in ('plantBefore', 'plant'))
                and (d['tool'] is None or valid_tool(d['tool'])) and isinstance(d['completedAtUtc'], str)
                and datetime.fromisoformat(d['completedAtUtc'].replace('Z', '+00:00')).utcoffset() is not None)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def evidence(receipt, intent, snapshot, proof):
    try:
        return _evidence(receipt, intent, snapshot, proof)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _evidence(receipt, intent, s, proof):
    if (not valid_before(s) or not workshop.envelope(receipt, s) or not isinstance(proof, dict)
            or set(proof) != {'receiptInstanceId', 'detailInstanceId', 'eventInstanceId', 'detail', 'events'}
            or any(proof[k] != s['worldInstanceId'] for k in ('receiptInstanceId', 'detailInstanceId', 'eventInstanceId'))
            or intent.get('rulesVersion') != 'r10' or intent.get('preconditionMode') != preconditions.ACTOR_STATE
            or not preconditions.valid_execution(receipt, intent) or receipt.get('commandId') != intent.get('commandId')
            or not equal(intent.get('action'), s['action']) or not isinstance(receipt.get('result'), dict)
            or set(receipt['result']) != {'action', 'forestryAction'} or receipt['result']['action'] != s['action']['type']):
        return None
    d, detail, events = receipt['result']['forestryAction'], proof['detail'], proof['events']
    if (not valid_detail(d) or not workshop.envelope(detail, s) or not workshop.envelope(events, s)
            or not equal(detail.get('forestryAction'), d) or not equal(d['action'], s['action'])
            or d['authorActorId'] != s['actorId'] or d['operatorId'] != s['operatorId'] or d['commandId'] != intent['commandId']
            or not equal(d['position'], s['position']) or d['inventoryWoodBefore'] != s['inventoryWood'] or d['seedsBefore'] != s['seeds']
            or d['serviceMs'] < s['serviceMs'] or d['stateVersion'] != receipt['stateVersion'] or d['eventCursor'] != receipt['eventCursor']
            or receipt['execution']['appliedOnStateVersion'] < s['stateVersion']
            or any(e['stateVersion'] < d['stateVersion'] or e['eventCursor'] < d['eventCursor'] for e in (detail, events))
            or not isinstance(events.get('events'), list)):
        return None
    matches = [e for e in events['events'] if isinstance(e, dict) and e.get('seq') == d['eventCursor']]
    expected = {'seq': d['eventCursor'], 'stateVersion': d['stateVersion'], 'actorId': s['actorId'],
                'commandId': intent['commandId'], 'type': 'forestryActionCompleted', 'forestryAction': d}
    if len(matches) != 1 or not equal(matches[0], expected):
        return None
    a, kind = s['action'], s['action']['type']
    charge = costs(a)
    if (d['inventoryWood'] != s['inventoryWood'] - charge['wood'] + charge['woodHarvested']
            or d['seeds'] != s['seeds'] + charge['seedsCollected'] - charge['seedsPlanted'] + charge['seedsHarvested']
            or d['nurseryStock'] != d['nurseryStockBefore'] - charge['seedsCollected']):
        return None
    rb, ra, pb, pa, tool = (d[k] for k in ('reservationBefore', 'reservation', 'plantBefore', 'plant', 'tool'))
    if kind == 'craft_forestry_tool':
        if (any(x is not None for x in (rb, ra, pb, pa)) or not valid_tool(tool) or tool['toolId'] in s['toolIds']
                or tool['ownerActorId'] != s['actorId'] or tool['workbenchId'] != a['entityId']
                or tool['commandId'] != intent['commandId'] or tool['stateVersion'] != d['stateVersion'] or tool['eventCursor'] != d['eventCursor']):
            return None
    elif kind == 'reserve_forest':
        if (any(x is not None for x in (rb, pb, pa, tool)) or not valid_reservation(ra) or ra['status'] != 'queued'
                or ra['reservationId'] in s['reservationIds'] or ra['actorId'] != s['actorId'] or ra['operatorId'] != s['operatorId']
                or ra['commandId'] != intent['commandId'] or ra['requestedAtMs'] != d['serviceMs'] or ra['queueOrder'] != d['eventCursor']):
            return None
    else:
        if (not valid_reservation(rb) or not valid_reservation(ra)
                or not equal(subset(rb, RESERVATION_IDENTITY), s['reservationIdentity'])
                or not equal(subset(ra, RESERVATION_IDENTITY), s['reservationIdentity'])
                or rb['expiresAtMs'] is not None and d['serviceMs'] >= rb['expiresAtMs']):
            return None
        if kind == 'cancel_forest_reservation':
            if (rb['status'] not in ('queued', 'preparing') or ra['status'] != 'cancelled'
                    or s['reservation']['status'] == 'preparing' and not equal(rb, s['reservation'])
                    or any(not equal(ra[k], rb[k]) for k in RESERVATION_FIELDS - {'status', 'reservedSeed', 'expiresAtMs'})
                    or ra['expiresAtMs'] not in (None, rb['expiresAtMs']) or any(x is not None for x in (pb, pa, tool))):
                return None
        elif not equal(rb, s['reservation']):
            return None
        elif kind == 'collect_seed':
            after = {**rb, 'reservedSeed': 0}
            if not equal(ra, after) or any(x is not None for x in (pb, pa, tool)):
                return None
        elif kind == 'plant_tree':
            if (pb is not None or tool is not None or not valid_plant(pa) or pa['plantId'] in s['plantIds']
                    or pa['plotId'] != a['plotId'] or pa['planterActorId'] != s['actorId'] or pa['operatorId'] != s['operatorId']
                    or pa['reservationId'] != a['reservationId'] or pa['commandId'] != intent['commandId']
                    or pa['plantedAtMs'] != d['serviceMs'] or pa['stateVersion'] != d['stateVersion']
                    or pa['eventCursor'] != d['eventCursor'] or pa['state'] != 'growing'
                    or not equal(ra, {**rb, 'status': 'growing', 'plantId': pa['plantId'], 'reservedSeed': 0, 'expiresAtMs': None})):
                return None
        elif kind == 'harvest_tree':
            if (not equal(pb, s['plant']) or not equal(tool, s['tool']) or d['serviceMs'] < pb['maturesAtMs']
                    or not equal(pa, {**pb, 'state': 'harvested', 'standingWood': 0, 'harvestActorId': s['actorId'],
                                      'harvestCommandId': intent['commandId'], 'harvestEventCursor': d['eventCursor']})
                    or ra['status'] != 'completed' or ra['expiresAtMs'] not in (None, rb['expiresAtMs'])
                    or any(not equal(ra[k], rb[k]) for k in RESERVATION_FIELDS - {'status', 'reservedSeed', 'expiresAtMs'})):
                return None
    return {'worldInstanceId': s['worldInstanceId'], **deepcopy(d)}


def approach(observed, goal, original):
    action, start, target = goal['forestry']['action'], observed['self']['position'], goal['target']
    if action['type'] in REMOTE_ACTIONS:
        return []
    geometry = nav.navigation(observed)
    ray = nav.navigation(observed,
        interaction_target=action['entityId'] if action['type'] == 'craft_forestry_tool' else None,
        interaction_obstacle=('nursery-west' if action['type'] == 'collect_seed' else
                              action['plantId'] if action['type'] == 'harvest_tree' else None))
    def usable(position):
        return (geometry.walkable(position) and nav.distance(position, target) <= 1.6
                and ray.clear(position, target)
                and (action['type'] != 'plant_tree' or nav.distance(position, target) >= .45 + observed['movement']['radius'] + nav.MARGIN))
    if usable(start):
        return []
    angle = math.atan2(start[1] - target[1], start[0] - target[0])
    candidates = [[target[0] + radius * math.cos(a), target[1] + radius * math.sin(a)]
                  for radius in (1.5, 1.25, 1.2)
                  for a in (angle, *(i * math.tau / 24 for i in range(24)))]
    for candidate in sorted(candidates, key=lambda p: nav.distance(start, p)):
        if usable(candidate):
            route = geometry.route(start, candidate)
            if route is not None:
                return route
    return None


def plan(observed, goal, original):
    if not ready(observed, goal, original):
        return None, 'forestry_original_target_or_capability_changed'
    action, task, cap = goal['forestry']['action'], goal['forestry'], observed['forestry']
    kind, inventory = action['type'], observed['self']['inventory']['wood']
    r, p = original_reservation(observed, action), original_plant(observed, action)
    waiting = None
    if 'reservationId' in action:
        if r is None:
            return None, 'forestry_original_reservation_no_longer_active'
        if r['actorId'] != original['actorId'] or r['operatorId'] != original['operatorId']:
            return None, 'forestry_original_reservation_identity_changed'
        if kind == 'cancel_forest_reservation' and r['status'] not in ('queued', 'preparing'):
            return None, 'forestry_original_reservation_not_cancellable'
        if kind in ('collect_seed', 'plant_tree'):
            if r['status'] == 'queued':
                return None, 'wait:original_reservation' if task['waitForReady'] else 'forestry_wait_not_authorized'
            if r['status'] != 'preparing':
                return None, 'forestry_original_reservation_not_preparing'
        if kind == 'plant_tree' and r['plotId'] != action['plotId']:
            return None, 'forestry_original_reservation_assigned_other_plot'
    if kind == 'craft_forestry_tool' and inventory < 2:
        return None, 'forestry_insufficient_recipe_wood'
    if kind == 'collect_seed' and (r['reservedSeed'] != 1 or cap['seeds'] >= MAX_INTEGER):
        return None, 'forestry_original_seed_not_reserved_or_inventory_overflow'
    if kind == 'plant_tree':
        if cap['seeds'] < 1:
            return None, 'forestry_no_owned_seed'
        if any(p['plotId'] == action['plotId'] for p in cap['plants']):
            return None, 'forestry_original_plot_is_occupied'
        residents = observed.get('residents')
        if not isinstance(residents, list) or any(not isinstance(x, dict) or not nav.point(x.get('position')) for x in residents):
            return None, 'forestry_resident_geometry_unavailable'
        if any(x['actorId'] != original['actorId'] and nav.distance(x['position'], goal['target']) < .45 + observed['movement']['radius']
               for x in residents):
            return None, 'forestry_original_plot_has_resident'
    if kind == 'harvest_tree':
        if p is None or r['plantId'] != action['plantId'] or r['plotId'] != p['plotId']:
            return None, 'forestry_original_plant_no_longer_available'
        if inventory > 9 or cap['seeds'] >= MAX_INTEGER:
            return None, 'forestry_harvest_inventory_capacity'
        if p['state'] == 'growing' and r['status'] == 'growing':
            if not task['waitForReady']:
                return None, 'forestry_wait_not_authorized'
            waiting = 'wait:original_maturity'
        elif p['state'] != 'mature' or r['status'] != 'harvesting':
            return None, 'forestry_original_plant_not_harvestable'
    route = approach(observed, goal, original)
    if route is None:
        return None, 'forestry_operation_side_unreachable'
    if route:
        return {'type': 'walk', 'to': list(route[0])}, None
    return (None, waiting) if waiting else (deepcopy(action), None)


def _utc(epoch=None):
    return (datetime.now(timezone.utc) if epoch is None else datetime.fromtimestamp(epoch, timezone.utc)).isoformat()


def _report(state):
    return deepcopy({key: value for key, value in state.items() if key != '_state'})


def report_goal(goal, initial):
    value = deepcopy(goal)
    if value['target'] is None:
        value['target'] = deepcopy(initial['self']['position'])
    return value


def _world(observed):
    from resident_mission import _public
    value = _public(observed)['world']
    value.update(forestry=deepcopy(observed['forestry']), workshop=deepcopy(observed['workshop']),
                 observedStateVersion=observed['stateVersion'],
                 observedSelf={'actorId': observed['self']['actorId'], 'position': deepcopy(observed['self']['position']),
                               'inventoryWood': observed['self']['inventory']['wood'], 'seeds': observed['forestry']['seeds']})
    for key in ('resourceAudit', 'seedAudit'):
        if key in observed:
            value[key] = deepcopy(observed[key])
    return value


def _query_log(log, count):
    return (isinstance(log, list) and integer(count) and len(log) == count
            and all(isinstance(q, dict) and set(q) == {'index', 'kind'} and type(q['index']) is int
                    and q['index'] == i and q['kind'] in QUERY_KINDS for i, q in enumerate(log, 1)))


def _startup_valid(value, spec, endpoint):
    return (isinstance(value, dict) and set(value) == {'schemaVersion', 'kind', 'spec', 'endpoint', 'startedEpoch', 'used', 'queries'}
            and type(value['schemaVersion']) is int and value['schemaVersion'] == 1 and value['kind'] == STARTUP
            and equal(value['spec'], spec) and isinstance(value['endpoint'], dict)
            and set(value['endpoint']) == {'url', 'prefix'} and isinstance(value['endpoint']['url'], str)
            and value['endpoint']['prefix'] == endpoint['prefix']
            and nav.finite(value['startedEpoch']) and 0 < value['startedEpoch'] <= time.time()
            and isinstance(value['used'], dict) and set(value['used']) == {'queries', 'seconds'}
            and _query_log(value['queries'], value['used'].get('queries'))
            and value['used']['queries'] <= spec['budgets']['queries']
            and all(q['kind'] == 'observation' for q in value['queries'])
            and nav.finite(value['used']['seconds']) and value['used']['seconds'] >= 0)


def _new_state(observed, spec, startup, endpoint):
    goal, original = spec['goals'][0], binding(observed, spec['goals'][0])
    origin = deepcopy(observed['self']['position'])
    used = dict.fromkeys(spec['budgets'], 0)
    used.update(startup['used'])
    base = {**endpoint, 'worldId': observed['world']['id'], 'actorId': original['actorId'], 'rulesVersion': 'r10',
            'instanceId': original['worldInstanceId'], 'bindingVersion': 1,
            'preconditionBindingVersion': 1, 'preconditionMode': preconditions.ACTOR_STATE}
    assigned = assignment(observed, goal['forestry']['action'])
    return {'schemaVersion': 1, 'kind': 'resident-mission-report',
            'mission': {'id': spec['missionId'], 'objective': spec['objective'], 'actorId': original['actorId'],
                        'operatorId': original['operatorId'], 'worldId': base['worldId'], 'rulesVersion': 'r10',
                        'worldInstanceId': original['worldInstanceId'], 'preconditionMode': preconditions.ACTOR_STATE,
                        'arrivalTolerance': .06, 'forestryVersion': 1, 'origin': origin,
                        'goal': report_goal(goal, observed), 'allowBuild': False,
                        **{key: spec[key] for key in PERMISSIONS.values()}, 'status': 'running', 'reason': 'forestry_fixed_action',
                        'startedAtUtc': _utc(startup['startedEpoch']), 'updatedAtUtc': _utc()},
            'decision': {'goalId': goal['id'], 'reason': '任务明确指定单一动作；未调用选择器',
                         'provider': {'kind': 'fixed-reference', 'model': 'none', 'usage': {}}},
            'budget': {'limits': deepcopy(spec['budgets']), 'used': used},
            'facts': {'goalReached': False, 'returned': True, 'forestryCompleted': False, 'forestryAction': None,
                      'woodClaimed': 0, 'woodGathered': 0, 'woodTransferred': 0,
                      'woodHarvested': 0, 'seedsCollected': 0, 'seedsPlanted': 0, 'seedsHarvested': 0,
                      'createdEntityIds': [], 'createdToolIds': [], 'createdPlantIds': [], 'createdReservationIds': [],
                      'startStateVersion': observed['stateVersion'], 'endStateVersion': observed['stateVersion'], 'verifiedAtUtc': None},
            'world': _world(observed), 'steps': [],
            'feedback': {'summary': '明确林业动作尚未执行', 'issues': [], 'suggestions': []},
            '_state': {'forestryTrackingVersion': 1, 'spec': deepcopy(spec), 'binding': base, 'forestryBinding': original,
                       'initial': deepcopy(observed), 'latest': deepcopy(observed),
                       'assignment': assigned, 'assignmentObservation': deepcopy(observed) if assigned else None,
                       'startedEpoch': startup['startedEpoch'], 'queries': deepcopy(startup['queries']),
                       'actorStateVersion': observed['stateVersion'], 'confirmedPosition': origin,
                       'confirmedInventoryWood': observed['self']['inventory']['wood'], 'confirmedSeeds': observed['forestry']['seeds'],
                       'terminal': False, 'pending': None}}


def _walk_before_valid(value, original):
    if not isinstance(value, dict) or not integer(value.get('seeds')):
        return False
    return workshop._walk_before_valid({k: v for k, v in value.items() if k != 'seeds'}, original)


def _receipt_valid(receipt, intent, snapshot, instance, *, committed):
    return workshop._receipt_valid(receipt, intent, snapshot, instance, committed=committed)


def validate_saved(state, spec, endpoint):
    try:
        _validate_saved(state, spec, endpoint)
    except (KeyError, TypeError, AttributeError, IndexError):
        raise ValueError('Original forestry authority, budgets or facts are damaged') from None


def _validate_saved(state, spec, endpoint):
    saved, mission, facts, steps = state['_state'], state['mission'], state['facts'], state['steps']
    original, initial, latest, base = (saved[k] for k in ('forestryBinding', 'initial', 'latest', 'binding'))
    goal, frozen = spec['goals'][0], spec['goals'][0]['forestry']
    limits, used = state['budget']['limits'], state['budget']['used']
    if (type(state.get('schemaVersion')) is not int or state['schemaVersion'] != 1 or state.get('kind') != 'resident-mission-report'
            or type(saved.get('forestryTrackingVersion')) is not int or saved['forestryTrackingVersion'] != 1
            or not equal(saved['spec'], spec) or not equal(normalize_spec(saved['spec']), spec)
            or not equal(limits, spec['budgets']) or set(used) != set(limits)
            or any(not integer(used[k]) or used[k] > limits[k] for k in limits if k != 'seconds')
            or used['modelCalls'] != 0 or not nav.finite(used['seconds']) or used['seconds'] < 0
            or not nav.finite(saved['startedEpoch']) or not 0 < saved['startedEpoch'] <= time.time()
            or mission['startedAtUtc'] != _utc(saved['startedEpoch'])
            or not _query_log(saved['queries'], used['queries']) or used['queries'] < 1
            or not isinstance(steps, list) or used['commands'] != len(steps)
            or base['prefix'] != endpoint['prefix'] or not isinstance(base['url'], str)
            or base['worldId'] != initial['world']['id'] or base['actorId'] != frozen['actorId']
            or base['instanceId'] != frozen['worldInstanceId'] or base['rulesVersion'] != 'r10'
            or type(base.get('bindingVersion')) is not int or base['bindingVersion'] != 1
            or not supported(initial) or not supported(latest) or not equal(binding(initial, goal), original)
            or not ready(latest, goal, original) or latest['stateVersion'] < initial['stateVersion']
            or latest['forestry']['nursery']['serviceMs'] < initial['forestry']['nursery']['serviceMs']
            or not equal(state['world'], _world(latest))
            or mission['id'] != spec['missionId'] or mission['objective'] != spec['objective']
            or not equal(mission['goal'], report_goal(goal, initial)) or not equal(mission['origin'], initial['self']['position'])
            or mission.get('allowBuild') is not False or any(mission.get(k) is not spec[k] for k in PERMISSIONS.values())
            or mission['actorId'] != original['actorId'] or mission['operatorId'] != original['operatorId']
            or mission['worldInstanceId'] != original['worldInstanceId'] or mission['worldId'] != base['worldId']
            or mission['rulesVersion'] != 'r10' or mission.get('preconditionMode') != preconditions.ACTOR_STATE
            or type(mission.get('forestryVersion')) is not int or mission['forestryVersion'] != 1
            or not nav.finite(mission.get('arrivalTolerance')) or mission['arrivalTolerance'] != .06
            or mission['status'] not in ('running', 'paused', 'blocked', 'budget_exhausted', 'unknown', 'completed')
            or type(saved['terminal']) is not bool
            or not equal(state['decision'], {'goalId': goal['id'], 'reason': '任务明确指定单一动作；未调用选择器',
                       'provider': {'kind': 'fixed-reference', 'model': 'none', 'usage': {}}})):
        raise ValueError('Original forestry identity, authority, snapshots or budgets are damaged')
    assigned, assignment_observation = saved['assignment'], saved['assignmentObservation']
    if assigned is not None:
        if (not supported(assignment_observation) or not ready(assignment_observation, goal, original)
                or not initial['stateVersion'] <= assignment_observation['stateVersion'] <= latest['stateVersion']
                or not equal(assigned, assignment(assignment_observation, frozen['action']))
                or assignment(latest, frozen['action']) is not None and not equal(assigned, assignment(latest, frozen['action']))):
            raise ValueError('The original reservation assignment was replaced')
    elif assignment_observation is not None or assignment(initial, frozen['action']) is not None or assignment(latest, frozen['action']) is not None:
        raise ValueError('The original reservation assignment was lost')
    version, position = initial['stateVersion'], initial['self']['position']
    inventory, seeds = initial['self']['inventory']['wood'], initial['forestry']['seeds']
    charges = dict.fromkeys(MATERIAL_KEYS, 0)
    completed, command_ids = [], set()
    pending_count = rejected_count = 0
    end_version = max(initial['stateVersion'], latest['stateVersion'])
    for i, step in enumerate(steps, 1):
        request, snapshot = step['request'], step['before']
        action, kind = request['action'], request['action']['type']
        forestry = kind in PERMISSIONS
        if (type(step['index']) is not int or step['index'] != i or not identifier(step['commandId']) or step['commandId'] in command_ids
                or not isinstance(step['reason'], str) or set(request) != {'schemaVersion', 'rulesVersion', 'commandId', 'expectedStateVersion', 'preconditionMode', 'action'}
                or type(request['schemaVersion']) is not int or request['schemaVersion'] != 1 or request['rulesVersion'] != 'r10'
                or request['preconditionMode'] != preconditions.ACTOR_STATE or request['commandId'] != step['commandId']
                or not equal(step['action'], action) or type(request['expectedStateVersion']) is not int or request['expectedStateVersion'] != version
                or step['preconditionMode'] != preconditions.ACTOR_STATE or step['expectedStateVersion'] != version
                or step['status'] not in ('pending', 'unknown', 'committed', 'rejected')
                or not equal(snapshot['position'], position) or snapshot['inventoryWood'] != inventory or snapshot['seeds'] != seeds
                or snapshot['stateVersion'] < version
                or forestry and (not valid_before(snapshot) or not equal(action, frozen['action'])
                                  or any(not equal(snapshot[k], original[k]) for k in original))
                or not forestry and (set(action) != {'type', 'to'} or kind != 'walk' or not nav.point(action['to'])
                                     or not _walk_before_valid(snapshot, original))):
            raise ValueError('Original forestry step, action or before facts are damaged')
        if forestry and snapshot['reservation'] is not None and snapshot['reservation']['plotId'] is not None:
            if not equal(assigned, subset(snapshot['reservation'], ('reservationId', 'plotId', 'grantedAtMs'))):
                raise ValueError('A pending forestry action cannot switch reservation targets')
        command_ids.add(step['commandId'])
        charge = costs(action)
        if step['status'] in ('pending', 'unknown'):
            pending_count += 1
            expected = {'request': request, 'charges': charge, 'forestryBefore' if forestry else 'walkBefore': snapshot}
            if (i != len(steps) or not equal(saved['pending'], expected) or step['execution'] is not None
                    or step['receipt'] is not None or step['receiptInstanceId'] is not None
                    or step['forestryProof'] is not None or step['forestryEvidence'] is not None
                    or not equal(step['position'], position) or step['inventoryWood'] != inventory or step['seeds'] != seeds
                    or any(charges[k] + charge[k] > limits[k] for k in MATERIAL_KEYS)):
                raise ValueError('The original forestry pending request was changed or lost')
            continue
        receipt, committed = step['receipt'], step['status'] == 'committed'
        if (not _receipt_valid(receipt, request, snapshot, step['receiptInstanceId'], committed=committed)
                or not equal(step['execution'], receipt['execution']) or step['stateVersion'] != receipt['stateVersion']
                or committed and step.get('httpStatus') != 200
                or not committed and (type(step.get('httpStatus')) is not int or not 400 <= step['httpStatus'] < 500)):
            raise ValueError('The original forestry receipt or execution proof is damaged')
        end_version = max(end_version, receipt['stateVersion'])
        if not committed:
            rejected_count += 1
            if (i != len(steps) or step.get('errorCode') != receipt['error']['code'] or not equal(step['position'], position)
                    or step['inventoryWood'] != inventory or step['seeds'] != seeds
                    or step['forestryProof'] is not None or step['forestryEvidence'] is not None):
                raise ValueError('A rejected forestry action cannot acquire success facts')
            continue
        if forestry:
            record = evidence(receipt, request, snapshot, step['forestryProof'])
            if record is None or not equal(step['forestryEvidence'], record) or completed:
                raise ValueError('Original forestry receipt, detail and event no longer agree')
            completed.append(record)
            charges = {k: charges[k] + charge[k] for k in MATERIAL_KEYS}
            inventory, seeds = record['inventoryWood'], record['seeds']
        else:
            if (not nav.valid_walk_receipt(receipt, request, original['actorId'], snapshot)
                    or receipt['execution']['appliedOnStateVersion'] < snapshot['stateVersion']
                    or step.get('blocked') is not receipt['result']['blocked']):
                raise ValueError('Original forestry walking evidence is damaged')
            position = receipt['result']['position']
            if receipt['result']['blocked'] and (i != len(steps) or not saved['terminal']):
                raise ValueError('A blocked walk cannot silently continue')
        version = receipt['stateVersion']
        if not equal(step['position'], position) or step['inventoryWood'] != inventory or step['seeds'] != seeds:
            raise ValueError('Forestry step summary differs from its confirmed result')
    done, record = bool(completed), completed[0] if completed else None
    actual_position = latest['self']['position'] if latest['stateVersion'] >= version else position
    returned = nav.near(actual_position, mission['origin'])
    kind = frozen['action']['type']
    expected = {'goalReached': done, 'returned': returned, 'forestryCompleted': done, 'forestryAction': record,
                'woodClaimed': 0, 'woodGathered': 0, 'woodTransferred': 0,
                **{k: charges[k] for k in MATERIAL_KEYS if k != 'wood'}, 'createdEntityIds': [],
                'createdToolIds': [record['tool']['toolId']] if done and kind == 'craft_forestry_tool' else [],
                'createdPlantIds': [record['plant']['plantId']] if done and kind == 'plant_tree' else [],
                'createdReservationIds': [record['reservation']['reservationId']] if done and kind == 'reserve_forest' else [],
                'startStateVersion': initial['stateVersion'], 'endStateVersion': end_version}
    if (any(not equal(facts.get(k), v) for k, v in expected.items()) or any(used[k] != charges[k] for k in MATERIAL_KEYS)
            or (saved['pending'] is not None) != (pending_count == 1) or pending_count > 1
            or saved['actorStateVersion'] != version or not equal(saved['confirmedPosition'], position)
            or saved['confirmedInventoryWood'] != inventory or saved['confirmedSeeds'] != seeds
            or rejected_count and not saved['terminal']
            or mission['status'] == 'completed' and (not done or frozen['returnToOrigin'] and not returned or saved['pending'] is not None or not saved['terminal'])
            or saved['terminal'] and saved['pending'] is not None
            or done and (not isinstance(facts.get('verifiedAtUtc'), str)
                         or datetime.fromisoformat(facts['verifiedAtUtc'].replace('Z', '+00:00')).utcoffset() is None)
            or not done and facts.get('verifiedAtUtc') is not None):
        raise ValueError('Forestry completion, budget or pending summaries are inconsistent')
    if preconditions.saved_mode(state) != preconditions.ACTOR_STATE:
        raise ValueError('The original forestry task cannot change command mode')


class QueryBudget(RuntimeError):
    pass


def run_mission(client, spec, state_path, choose=None, *, max_steps=None):
    from resident_mission import _lock, _save
    spec = normalize_spec(spec)
    if max_steps is not None and (type(max_steps) is not int or not 0 <= max_steps <= 1000):
        raise ValueError('max_steps must be an integer from 0 to 1000')
    path = Path(state_path).resolve()
    endpoint = {'url': client.url.rstrip('/'), 'prefix': client.prefix}
    goal, frozen = spec['goals'][0], spec['goals'][0]['forestry']
    with _lock(path):
        raw = json.loads(path.read_text()) if path.exists() else None
        if raw is None:
            raw = {'schemaVersion': 1, 'kind': STARTUP, 'spec': deepcopy(spec), 'endpoint': endpoint,
                   'startedEpoch': time.time(), 'used': {'queries': 0, 'seconds': 0}, 'queries': []}
            _save(path, raw)
        if isinstance(raw, dict) and raw.get('kind') == STARTUP:
            if not _startup_valid(raw, spec, endpoint):
                raise ValueError('Original forestry startup or query budget is damaged')
            client.bind_instance(frozen['worldInstanceId'])
            if raw['used']['queries'] >= spec['budgets']['queries'] or time.time() - raw['startedEpoch'] >= spec['budgets']['seconds']:
                raise QueryBudget('Original forestry startup budget is exhausted')
            raw['used']['queries'] += 1
            raw['queries'].append({'index': raw['used']['queries'], 'kind': 'observation'})
            raw['used']['seconds'] = max(raw['used']['seconds'], time.time() - raw['startedEpoch'])
            _save(path, raw)
            observed = client.observe()
            if getattr(client, 'response_instance_id', None) != frozen['worldInstanceId']:
                raise WorldBindingError('Initial forestry response has no original instance proof')
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
        original = saved['forestryBinding']
        handled, fresh = 0, False

        def save():
            used['seconds'] = max(used['seconds'], time.time() - saved['startedEpoch'])
            _save(path, state)

        def expired():
            return max(used['seconds'], time.time() - saved['startedEpoch']) >= limits['seconds']

        def finish(status, reason, terminal=False):
            mission.update(status=status, reason=reason, updatedAtUtc=_utc())
            saved['terminal'] = bool(terminal)
            position = (saved['latest']['self']['position'] if saved['latest']['stateVersion'] >= saved['actorStateVersion']
                        else saved['confirmedPosition'])
            facts['returned'] = nav.near(position, mission['origin'])
            state['feedback'] = {
                'summary': ('原林业动作三方证据已确认；返程已确认' if frozen['returnToOrigin'] else
                            '原林业动作三方证据已确认；本任务未要求返程') if status == 'completed' else reason,
                'issues': [] if status in ('completed', 'paused') else [reason], 'suggestions': []}
            save()
            return _report(state)

        def query(call, kind):
            if used['queries'] >= limits['queries']:
                raise QueryBudget('Original forestry query budget is exhausted')
            used['queries'] += 1
            saved['queries'].append({'index': used['queries'], 'kind': kind})
            save()
            response = call()
            instance = getattr(client, 'response_instance_id', None)
            if instance != original['worldInstanceId']:
                raise WorldBindingError('Forestry query response does not prove the original instance')
            return response, instance

        def observe():
            observed, _ = query(client.observe, 'observation')
            if (not ready(observed, goal, original) or observed['stateVersion'] < saved['latest']['stateVersion']
                    or observed['forestry']['nursery']['serviceMs'] < saved['latest']['forestry']['nursery']['serviceMs']):
                raise WorldBindingError('Original forestry identity, capability, geometry or monotonic state changed')
            assigned = assignment(observed, frozen['action'])
            if assigned is not None:
                if saved['assignment'] is not None and not equal(assigned, saved['assignment']):
                    raise WorldBindingError('The original reservation was assigned to another target')
                if saved['assignment'] is None:
                    saved['assignment'] = deepcopy(assigned)
                    saved['assignmentObservation'] = deepcopy(observed)
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
                if facts['forestryCompleted'] and (not frozen['returnToOrigin'] or nav.near(saved['confirmedPosition'], mission['origin'])):
                    return finish('completed', 'forestry_action_and_return_verified' if frozen['returnToOrigin'] else 'forestry_action_verified', True)
                if max_steps is not None and handled >= max_steps:
                    return finish('paused', 'max_steps')
                save()
                if expired():
                    return finish('budget_exhausted', 'seconds')
                if used['commands'] >= limits['commands']:
                    return finish('budget_exhausted', 'commands')
                try:
                    observed = observe()
                except QueryBudget:
                    return finish('budget_exhausted', 'queries')
                except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                    return unknown('forestry_observation_unavailable:' + type(error).__name__)
                if (not equal(observed['self']['position'], saved['confirmedPosition'])
                        or observed['self']['inventory']['wood'] != saved['confirmedInventoryWood']
                        or observed['forestry']['seeds'] != saved['confirmedSeeds']):
                    return finish('blocked', 'forestry_actor_changed_outside_task', True)
                if facts['forestryCompleted']:
                    route = nav.navigation(observed).route(observed['self']['position'], mission['origin'])
                    if route is None:
                        return finish('blocked', 'forestry_return_unreachable')
                    if not route:
                        return finish('completed', 'forestry_action_and_return_verified', True)
                    action, issue = {'type': 'walk', 'to': list(route[0])}, None
                else:
                    action, issue = plan(observed, goal, original)
                if issue:
                    if issue.startswith('wait:') and frozen['waitForReady']:
                        mission.update(status='running', reason=issue)
                        save()
                        if expired():
                            return finish('budget_exhausted', 'seconds')
                        time.sleep(min(1.0, max(0, limits['seconds'] - (time.time() - saved['startedEpoch']))))
                        continue
                    return finish('blocked', issue, True)
                forestry = action['type'] in PERMISSIONS
                charge = costs(action)
                exceeded = next((k for k in MATERIAL_KEYS if used[k] + charge[k] > limits[k]), None)
                if exceeded:
                    return finish('budget_exhausted', exceeded)
                if not forestry:
                    start, target = observed['self']['position'], action['to']
                    distance = nav.distance(start, target)
                    step_length = min(distance, observed['movement']['maxStepDistance'])
                    action['to'] = [a + (b - a) * step_length / distance for a, b in zip(start, target)]
                    time.sleep(step_length / observed['movement']['speed'] + .005)
                save()
                if expired():
                    return finish('budget_exhausted', 'seconds')
                intent = {'schemaVersion': 1, 'rulesVersion': 'r10', 'commandId': uuid.uuid4().hex,
                          'preconditionMode': preconditions.ACTOR_STATE,
                          'expectedStateVersion': saved['actorStateVersion'], 'action': deepcopy(action)}
                snapshot = before(observed, goal, original) if forestry else {
                    'version': 1, **{k: original[k] for k in ('worldInstanceId', 'actorId', 'operatorId')},
                    'position': deepcopy(observed['self']['position']), 'inventoryWood': observed['self']['inventory']['wood'],
                    'seeds': observed['forestry']['seeds'], 'stateVersion': observed['stateVersion'],
                    'maxStepDistance': observed['movement']['maxStepDistance']}
                if forestry and not valid_before(snapshot):
                    return finish('blocked', 'forestry_before_facts_not_ready', True)
                pending = {'request': intent, 'charges': charge, 'forestryBefore' if forestry else 'walkBefore': snapshot}
                saved['pending'] = deepcopy(pending)
                used['commands'] += 1
                state['steps'].append({'index': used['commands'], 'commandId': intent['commandId'], 'action': deepcopy(action),
                    'reason': '执行明确授权的原林业动作' if forestry else '返回原起点' if facts['forestryCompleted'] else '前往原目标的可达操作侧',
                    'status': 'pending', 'stateVersion': observed['stateVersion'], 'position': deepcopy(snapshot['position']),
                    'inventoryWood': snapshot['inventoryWood'], 'seeds': snapshot['seeds'],
                    'preconditionMode': preconditions.ACTOR_STATE, 'expectedStateVersion': intent['expectedStateVersion'], 'execution': None,
                    'request': deepcopy(intent), 'before': deepcopy(snapshot), 'receipt': None, 'receiptInstanceId': None,
                    'forestryProof': None, 'forestryEvidence': None})
                mission.update(status='running', reason='forestry_command_pending')
                save()
                fresh = True
            intent = pending['request']
            action = intent['action']
            forestry = action['type'] in PERMISSIONS
            snapshot = pending['forestryBefore' if forestry else 'walkBefore']
            step = state['steps'][-1]
            try:
                if not fresh:
                    (status, receipt), receipt_instance = query(lambda: client.request('GET', client.prefix + '/commands/' + intent['commandId']), 'receipt')
                    absent = (status == 404 and workshop.envelope(receipt, original, error=True)
                              and receipt.get('commandId') == intent['commandId'] and isinstance(receipt.get('error'), dict)
                              and receipt['error'].get('code') == 'COMMAND_NOT_FOUND' and receipt['error'].get('mutated') is False)
                    if absent:
                        save()
                        if expired() or max_steps is not None and handled >= max_steps:
                            return finish('budget_exhausted' if expired() else 'paused', 'original_pending_not_sent')
                        observe()
                        save()
                        if expired():
                            return finish('budget_exhausted', 'seconds_pending_retained')
                        status, receipt = client.command(deepcopy(intent))
                        receipt_instance = getattr(client, 'response_instance_id', None)
                else:
                    save()
                    if expired():
                        return finish('budget_exhausted', 'seconds_pending_retained')
                    status, receipt = client.command(deepcopy(intent))
                    receipt_instance = getattr(client, 'response_instance_id', None)
                fresh = False
                committed = status == 200 and _receipt_valid(receipt, intent, snapshot, receipt_instance, committed=True)
                rejected = (type(status) is int and 400 <= status < 500 and status not in (401, 412, 428)
                            and _receipt_valid(receipt, intent, snapshot, receipt_instance, committed=False))
                if not committed and not rejected:
                    return unknown('forestry_original_receipt_unconfirmed')
                proof = record = None
                if committed and forestry:
                    cursor = receipt.get('eventCursor')
                    if not integer(cursor) or cursor < 1:
                        return unknown('forestry_original_event_cursor_invalid')
                    (detail_status, detail), detail_instance = query(lambda: client.request('GET', client.prefix +
                        '/forestry/actions/' + original['actorId'] + '/' + intent['commandId']), 'forestry_detail')
                    if detail_status != 200:
                        return unknown('forestry_original_detail_unavailable')
                    (event_status, events), event_instance = query(lambda: client.request('GET', client.prefix +
                        '/events?after=' + str(cursor - 1)), 'forestry_event')
                    if event_status != 200:
                        return unknown('forestry_original_event_unavailable')
                    proof = {'receiptInstanceId': receipt_instance, 'detailInstanceId': detail_instance,
                             'eventInstanceId': event_instance, 'detail': detail, 'events': events}
                    record = evidence(receipt, intent, snapshot, proof)
                    if record is None:
                        return unknown('forestry_original_three_records_disagree')
                if committed and not forestry and (not nav.valid_walk_receipt(receipt, intent, original['actorId'], snapshot)
                        or receipt['execution']['appliedOnStateVersion'] < snapshot['stateVersion']):
                    return unknown('forestry_walk_unconfirmed')
            except QueryBudget:
                return finish('budget_exhausted', 'queries_pending_retained')
            except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                return unknown('forestry_original_pending_retained:' + type(error).__name__)
            step.update(status='committed' if committed else 'rejected', stateVersion=receipt['stateVersion'], httpStatus=status,
                        execution=deepcopy(receipt['execution']), receipt=deepcopy(receipt), receiptInstanceId=receipt_instance,
                        forestryProof=deepcopy(proof), forestryEvidence=deepcopy(record))
            facts['endStateVersion'] = max(facts['endStateVersion'], receipt['stateVersion'])
            saved['binding'].update(endpoint)
            if committed:
                saved['actorStateVersion'] = receipt['stateVersion']
                if forestry:
                    facts.update(goalReached=True, forestryCompleted=True, forestryAction=deepcopy(record), verifiedAtUtc=_utc())
                    saved['confirmedInventoryWood'], saved['confirmedSeeds'] = record['inventoryWood'], record['seeds']
                    for key, value in pending['charges'].items():
                        used[key] += value
                        if key != 'wood':
                            facts[key] += value
                    if action['type'] == 'craft_forestry_tool': facts['createdToolIds'].append(record['tool']['toolId'])
                    if action['type'] == 'plant_tree': facts['createdPlantIds'].append(record['plant']['plantId'])
                    if action['type'] == 'reserve_forest': facts['createdReservationIds'].append(record['reservation']['reservationId'])
                else:
                    saved['confirmedPosition'] = deepcopy(receipt['result']['position'])
                    step['blocked'] = receipt['result']['blocked']
            else:
                step['errorCode'] = receipt['error']['code']
            step.update(position=deepcopy(saved['confirmedPosition']), inventoryWood=saved['confirmedInventoryWood'], seeds=saved['confirmedSeeds'])
            facts['returned'] = nav.near(saved['confirmedPosition'], mission['origin'])
            saved['pending'] = None
            handled += 1
            # Receipt, clearing pending and a terminal outcome share one write.
            if rejected:
                return finish('blocked', 'command_rejected:' + receipt['error']['code'], True)
            if not forestry and receipt['result']['blocked']:
                return finish('blocked', 'forestry_walk_collision_stopped', True)
            save()
