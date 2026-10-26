"""One explicitly authorized r10 reservation; original events and receipts are facts.

The goal's materialAccess is {sourceId: wood-source-east, quantity: 3}, paired
with platform.v1. It never adopts another task's reservation or renews a lease.
"""
from copy import deepcopy
import re

import continuous_navigation as nav
import resident_construction as construction
from command_preconditions import ACTOR_STATE, integer, point, valid_execution
from foundation_agent import valid_world_instance
from resident_entity_notes import equal, valid_queries

SOURCE = 'wood-source-east'
STARTUP = 'material-access-startup'
POLICY = 'continuous-service-time-v1'
POLICY_FIELDS = {'id', 'version', 'adoptedAtServiceMs', 'adoptedAtStateVersion', 'adoptedAtEventCursor',
                 'generatedWoodAtAdoption', 'productionPeriodAtAdoption'}
ACTIONS = ('reserve_material', 'harvest_material')
ROSTER = {'a1': 'local-operator', 'a1_alias': 'local-operator',
          'a2': 'declared-late', 'a3': 'declared-third'}


class QueryBudget(Exception):
    """A persisted read budget is exhausted; keep any original pending request."""


def valid_goal(value):
    return (isinstance(value, dict) and set(value) == {'sourceId', 'quantity'}
            and value['sourceId'] == SOURCE and type(value['quantity']) is int and value['quantity'] == 3)


def supported(observed):
    try:
        return _supported(observed)
    except (KeyError, TypeError, AttributeError, ValueError):
        return False


def _supported(observed):
    source = observed.get('materialAccess')
    return (observed.get('rulesVersion') == 'r10'
            and observed.get('world', {}).get('scenarioId') == 'wilderness-material-access-v1'
            and isinstance(source, dict) and type(source.get('version')) is int and source['version'] in (1, 2)
            and source.get('sourceId') == SOURCE and source.get('position') == [28, 10]
            and source.get('buildExclusion') == [27, 9, 29, 11]
            and all(type(source.get(k)) is int and source[k] == v for k, v in
                    {'reservationQuantity': 3, 'leaseMs': 60000, 'productionIntervalMs': 10000,
                     'capacity': 6}.items())
            and type(source.get('active')) is bool and integer(source.get('serviceMs'))
            and source.get('controlBasis') == 'declared-local-fixture'
            and isinstance(source.get('controlRoster'), list)
            and len(source['controlRoster']) == len(ROSTER)
            and all(isinstance(r, dict) and set(r) == {'actorId', 'operatorId'} for r in source['controlRoster'])
            and {r['actorId']: r['operatorId'] for r in source['controlRoster']} == ROSTER
            and observed.get('self', {}).get('actorId') in ROSTER
            and isinstance(source.get('recentReservations'), list)
            and valid_policy(observed))


def valid_policy(observed):
    source = observed['materialAccess']
    if (not integer(source.get('generatedWood')) or source['generatedWood'] > 2**63 - 13
            or not integer(source.get('stockWood')) or source['stockWood'] > min(6, source['generatedWood'])):
        return False
    if source['version'] == 1:
        return (type(source.get('inputBudget')) is int and source['inputBudget'] == 12
                and source['generatedWood'] <= 12 and source.get('productionPolicy') is None)
    policy = source.get('productionPolicy')
    if (source.get('active') is not True or 'inputBudget' not in source or source['inputBudget'] is not None
            or not valid_world_instance(observed.get('world', {}).get('instanceId'))
            or not isinstance(policy, dict) or set(policy) != POLICY_FIELDS
            or policy.get('id') != POLICY or type(policy.get('version')) is not int or policy['version'] != 1
            or any(not integer(policy[k]) or policy[k] > 2**63 - 1 for k in POLICY_FIELDS - {'id', 'version'})
            or not integer(observed.get('stateVersion')) or not 0 < policy['adoptedAtStateVersion'] <= observed['stateVersion']
            or policy['adoptedAtEventCursor'] != policy['adoptedAtStateVersion'] + 1
            or policy['generatedWoodAtAdoption'] > min(12, source['generatedWood'])
            or not integer(source.get('enabledAtServiceMs')) or not integer(source.get('nextProductionAtMs'))
            or not source['enabledAtServiceMs'] <= policy['adoptedAtServiceMs'] <= source['serviceMs']
            or source['nextProductionAtMs'] <= source['serviceMs']
            or (source['nextProductionAtMs'] - source['enabledAtServiceMs']) % 10000 != 0
            or policy['productionPeriodAtAdoption'] != (policy['adoptedAtServiceMs'] - source['enabledAtServiceMs']) // 10000
            or policy['generatedWoodAtAdoption'] > 3 * policy['productionPeriodAtAdoption']):
        return False
    return True


def accept_observation(observed, saved=None):
    """Allow explicit v1 -> v2 adoption, never change an already observed policy."""
    if (not supported(observed) or observed.get('identity', {}).get('actorId') != observed['self']['actorId']
            or observed.get('identity', {}).get('operatorId') != ROSTER[observed['self']['actorId']]):
        raise RuntimeError('Material capability, policy or identity is unavailable')
    policy = observed['materialAccess'].get('productionPolicy')
    if saved is not None:
        previous = saved.get('materialProductionPolicy', saved['initial'].get('materialAccess', {}).get('productionPolicy'))
        if previous is not None and not equal(previous, policy):
            raise RuntimeError('Original continuous material policy changed')
        saved['materialProductionPolicy'] = deepcopy(policy)


def valid_reservation(value, actor):
    return (isinstance(value, dict) and isinstance(value.get('reservationId'), str)
            and re.fullmatch(r'm[0-9a-f]{32}', value['reservationId']) is not None
            and value.get('actorId') == actor and value.get('operatorId') == ROSTER.get(actor)
            and value.get('sourceId') == SOURCE and isinstance(value.get('requestCommandId'), str)
            and bool(value['requestCommandId']) and integer(value.get('queueSequence')) and value['queueSequence'] > 0
            and integer(value.get('requestedAtMs')) and integer(value.get('stateVersion'))
            and integer(value.get('eventCursor')) and value['eventCursor'] > 0)


def reservation_now(observed, original):
    source = observed['materialAccess']
    candidates = [source.get('currentReservation'), *source['recentReservations']]
    for current in candidates:
        if isinstance(current, dict) and current.get('reservationId') == original['reservationId']:
            if any(current.get(k) != original[k] for k in
                   ('actorId', 'operatorId', 'requestCommandId', 'queueSequence', 'requestedAtMs')):
                return None
            return current
    return None


def plan(observed, goal, facts=None):
    facts = facts or {}
    empty = {'reason': None, 'cells': [], 'bridges': 0, 'wood': 3, 'commands': None, 'nextAction': None}
    if not supported(observed):
        return {**empty, 'reason': 'material_access_unavailable'}
    source = observed['materialAccess']
    if not source['active']:
        return {**empty, 'reason': 'material_source_inactive'}
    issue = construction.placement_issue(observed, goal)
    if issue:
        return {**empty, 'reason': issue}
    harvested = facts.get('materialWoodHarvested', 0)
    if harvested == 3:
        return construction.plan(observed, goal, False)
    original = facts.get('materialReservation')
    if original is None and source.get('currentReservation') is not None:
        return {**empty, 'reason': 'material_reservation_already_exists'}
    if observed['self']['inventory']['wood'] + 3 - harvested > 12:
        return {**empty, 'reason': 'material_inventory_capacity'}
    route = nav.route_info(observed, source['position'], False, False)
    if route['reason']:
        return {**empty, 'reason': 'material_source_unreachable'}
    forecast = deepcopy(observed)
    forecast['self']['position'] = deepcopy(source['position'])
    forecast['self']['inventory']['wood'] += 3 - harvested
    after = construction.plan(forecast, goal, False)
    if after['reason']:
        return {**empty, 'reason': after['reason']}
    empty['commands'] = route['commands'] + after['commands'] + 4 - harvested
    if original is None:
        return {**empty, 'nextAction': {'type': 'reserve_material', 'sourceId': SOURCE},
                'nextReason': '申请本任务明确授权的一份材料资格'}
    current = reservation_now(observed, original)
    if current is None:
        return {**empty, 'reason': 'material_reservation_unavailable'}
    if current.get('status') in ('expired', 'cancelled', 'completed'):
        return {**empty, 'reason': 'material_reservation_' + current['status']}
    if (not integer(current.get('remaining')) or current['remaining'] != 3 - harvested
            or current.get('status') not in ('queued', 'active')):
        return {**empty, 'reason': 'material_reservation_changed'}
    if current['status'] == 'queued':
        return {**empty, 'waiting': True}
    granted, expiry = current.get('grantedAtMs'), current.get('expiresAtMs')
    if not integer(granted) or not integer(expiry) or expiry - granted != 60000:
        return {**empty, 'reason': 'material_reservation_changed'}
    if source['serviceMs'] >= expiry:
        return {**empty, 'reason': 'material_reservation_expired'}
    start = observed['self']['position']
    if (nav.distance(start, source['position']) <= observed['movement']['gatherReach']
            and nav.navigation(observed).clear(start, source['position'])):
        return {**empty, 'nextAction': {'type': 'harvest_material', 'reservationId': original['reservationId']},
                'nextReason': '按原预约逐次领取授权木材'}
    return {**empty, 'nextAction': route['nextAction'], 'nextReason': '前往原预约采集区'}


def before(observed, original=None):
    return {'sourceId': SOURCE, 'actorId': observed['self']['actorId'],
            'operatorId': ROSTER[observed['self']['actorId']],
            'position': deepcopy(observed['self']['position']), 'sourcePosition': [28, 10],
            'inventoryWood': observed['self']['inventory']['wood'],
            'reservation': deepcopy(reservation_now(observed, original)) if original else None}


def valid_before(value, action):
    if (not isinstance(value, dict) or value.get('sourceId') != SOURCE
            or value.get('actorId') not in ROSTER or value.get('operatorId') != ROSTER[value['actorId']]
            or not point(value.get('position')) or value.get('sourcePosition') != [28, 10]
            or not integer(value.get('inventoryWood')) or value['inventoryWood'] > 12):
        return False
    if action == 'reserve_material':
        return value.get('reservation') is None
    reservation = value.get('reservation')
    return (action == 'harvest_material' and isinstance(reservation, dict)
            and reservation.get('actorId') == value['actorId'] and reservation.get('operatorId') == value['operatorId']
            and reservation.get('status') == 'active' and integer(reservation.get('remaining'))
            and 1 <= reservation['remaining'] <= 3 and value['inventoryWood'] < 12
            and nav.distance(value['position'], value['sourcePosition']) <= 1.6)


def evidence(receipt, intent, actor, before, instance, event=None):
    action, result = intent['action'], receipt.get('result')
    if (not valid_before(before, action['type']) or before['actorId'] != actor or not isinstance(result, dict)
            or intent.get('rulesVersion') != 'r10' or intent.get('preconditionMode') != ACTOR_STATE
            or receipt.get('rulesVersion') != 'r10' or type(receipt.get('schemaVersion')) is not int
            or receipt['schemaVersion'] != 1 or receipt.get('commandId') != intent['commandId']
            or not isinstance(receipt.get('identity'), dict) or receipt['identity'].get('actorId') != actor
            or receipt['identity'].get('operatorId') != before['operatorId'] or not valid_execution(receipt, intent)
            or not integer(receipt.get('eventCursor')) or receipt['eventCursor'] <= 0
            or result.get('action') != action['type'] or result.get('sourceId') != SOURCE):
        return None
    common = {'worldInstanceId': instance, 'actorId': actor, 'operatorId': before['operatorId'],
              'sourceId': SOURCE, 'stateVersion': receipt['stateVersion'], 'eventCursor': receipt.get('eventCursor')}
    if action['type'] == 'reserve_material':
        record = {**common, **{k: result.get(k) for k in ('reservationId', 'queueSequence', 'requestedAtMs')},
                  'requestCommandId': intent['commandId']}
        if (action != {'type': 'reserve_material', 'sourceId': SOURCE} or result.get('status') != 'queued'
                or not valid_reservation(record, actor) or not isinstance(event, dict)):
            return None
        expected = {'type': 'materialReserved', 'seq': receipt['eventCursor'], 'stateVersion': receipt['stateVersion'],
                    'commandId': intent['commandId'], 'actorId': actor, 'operatorId': before['operatorId'],
                    'sourceId': SOURCE, 'reservationId': record['reservationId'],
                    'queueSequence': record['queueSequence'], 'serviceMs': record['requestedAtMs']}
        return record if all(event.get(k) == v and type(event.get(k)) is type(v) for k, v in expected.items()) else None
    reservation = before['reservation']
    expected = {'reservationId': action.get('reservationId'), 'quantity': 1,
                'remainingBefore': reservation['remaining'], 'remaining': reservation['remaining'] - 1,
                'inventoryWoodBefore': before['inventoryWood'], 'inventoryWood': before['inventoryWood'] + 1,
                'position': before['sourcePosition']}
    if (action.get('reservationId') != reservation['reservationId']
            or not all(result.get(k) == v and type(result.get(k)) is type(v) for k, v in expected.items())):
        return None
    return {**common, **deepcopy(expected), 'commandId': intent['commandId']}


def validate_saved(state):
    try:
        _validate_saved(state)
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ValueError('Original material state is incomplete or damaged') from None


def _validate_saved(state):
    spec, mission, facts = state['_state']['spec'], state['mission'], state['facts']
    uses = any('materialAccess' in g for g in spec['goals'])
    pending = state['_state'].get('pending')
    is_material = pending is not None and pending.get('request', {}).get('action', {}).get('type') in ACTIONS
    if not uses:
        if is_material or facts.get('materialReservation') is not None:
            raise ValueError('Material access cannot be added to an old task')
        return
    goal, binding = mission.get('goal'), state['_state']['binding']
    used, limits = state['budget']['used'], state['budget']['limits']
    initial = state['_state']['initial']
    if (spec.get('allowMaterialAccess') is not True or mission.get('allowMaterialAccess') is not True
            or any(mission.get(k, False) is not spec.get(k, False) for k in ('allowBuild', 'allowGather', 'allowTransfer', 'allowEntityNotes'))
            or binding.get('rulesVersion') != 'r10' or mission.get('rulesVersion') != 'r10'
            or mission.get('preconditionMode') != ACTOR_STATE or mission.get('actorId') != binding.get('actorId')
            or mission.get('worldInstanceId') != binding.get('instanceId')
            or not equal(limits, spec['budgets']) or set(used) != set(limits)
            or any(type(v) is not int for v in [*limits.values(), *spec['budgets'].values()])
            or any(not integer(used[k]) or used[k] > limits[k] for k in ('queries', 'commands', 'wood', 'modelCalls'))
            or used['queries'] < 1 or not nav.finite(used['seconds']) or used['seconds'] < 0
            or used['commands'] != len(state['steps'])
            or not nav.finite(state['_state']['startedEpoch']) or state['_state']['startedEpoch'] <= 0
            or not valid_world_instance(binding.get('instanceId')) or not supported(initial)
            or initial['self']['actorId'] != mission['actorId'] or initial['world']['instanceId'] != binding['instanceId']
            or goal is not None and (goal not in spec['goals'] or not valid_goal(goal.get('materialAccess')))):
        raise ValueError('Original material authorization, binding or budget is damaged')
    saved = state['_state']
    tracked = 'materialAccessTrackingVersion' in saved
    if tracked:
        if (type(saved['materialAccessTrackingVersion']) is not int or saved['materialAccessTrackingVersion'] != 1
                or 'materialProductionPolicy' not in saved
                or not valid_queries(saved.get('materialAccessQueries'), used['queries'],
                                     kinds=('observation', 'receipt', 'material_event'))):
            raise ValueError('Original material query accounting is damaged')
    elif 'materialAccessQueries' in saved or initial['materialAccess']['version'] == 2:
        raise ValueError('Original material query tracking is missing')
    policy = saved.get('materialProductionPolicy')
    if (policy is not None and (not isinstance(policy, dict) or set(policy) != POLICY_FIELDS
                               or policy['id'] != POLICY or type(policy['version']) is not int or policy['version'] != 1
                               or any(not integer(policy[k]) for k in POLICY_FIELDS - {'id', 'version'}))
            or initial['materialAccess']['version'] == 2 and not equal(policy, initial['materialAccess']['productionPolicy'])):
        raise ValueError('Original continuous material policy is damaged')
    current_policy = state.get('world', {}).get('materialAccess', {}).get('productionPolicy')
    if policy is not None and current_policy is not None and not equal(policy, current_policy):
        raise ValueError('Saved material policy observations disagree')
    commands = [s.get('commandId') for s in state['steps']]
    if (any(not isinstance(c, str) or not c for c in commands) or len(commands) != len(set(commands))
            or any(type(s.get('index')) is not int or s['index'] != i or s.get('status') not in ('committed', 'rejected', 'pending', 'unknown')
                   or s.get('action', {}).get('type') not in ('reserve_material', 'harvest_material', 'walk', 'build')
                   for i, s in enumerate(state['steps'], 1))):
        raise ValueError('Original material command accounting is damaged')
    original = facts.get('materialReservation')
    harvested = facts.get('materialWoodHarvested', 0)
    harvests = facts.get('materialHarvests', [])
    if (not integer(harvested) or harvested > 3 or not isinstance(harvests, list) or len(harvests) != harvested
            or original is None and harvested != 0):
        raise ValueError('Original material accounting is damaged')
    if original is not None:
        reserved = [s for s in state['steps'] if s['commandId'] == original.get('requestCommandId')
                    and s.get('status') == 'committed' and s.get('action') == {'type': 'reserve_material', 'sourceId': SOURCE}]
        if (not valid_reservation(original, mission['actorId']) or original.get('worldInstanceId') != binding['instanceId']
                or len(reserved) != 1 or reserved[0].get('materialEvidence') != original):
            raise ValueError('Original reservation identity is damaged')
        for index, record in enumerate(harvests):
            steps = [s for s in state['steps'] if s['commandId'] == record.get('commandId') and s.get('status') == 'committed']
            if (any(not integer(record.get(k)) for k in ('remainingBefore', 'remaining', 'quantity',
                                                        'inventoryWoodBefore', 'inventoryWood', 'stateVersion', 'eventCursor'))
                    or record['quantity'] != 1 or record['eventCursor'] < 1 or record['inventoryWoodBefore'] >= 12
                    or record['inventoryWood'] != record['inventoryWoodBefore'] + 1 or record.get('position') != [28, 10]
                    or record.get('actorId') != mission['actorId'] or record.get('operatorId') != ROSTER[mission['actorId']]
                    or record.get('worldInstanceId') != binding['instanceId'] or record.get('sourceId') != SOURCE
                    or record.get('reservationId') != original['reservationId'] or record.get('remainingBefore') != 3 - index
                    or record.get('remaining') != 2 - index or len(steps) != 1 or steps[0].get('materialEvidence') != record):
                raise ValueError('Original harvest accounting is damaged')
    built, has_build = facts.get('construction'), facts.get('constructionBuilt', False)
    if type(has_build) is not bool:
        raise ValueError('Original construction confirmation is damaged')
    committed_builds = [s for s in state['steps'] if s.get('action', {}).get('type') == 'build' and s.get('status') == 'committed']
    if has_build:
        if (not isinstance(built, dict) or harvested != 3 or len(committed_builds) != 1 or used['wood'] != 3
                or built.get('ownerActorId') != mission['actorId'] or built.get('recipeId') != 'platform.v1'
                or built.get('definitionId') != 'platform' or type(built.get('woodSpent')) is not int or built['woodSpent'] != 3
                or not equal(built.get('position'), goal['target']) or not integer(built.get('stateVersion'))
                or built.get('commandId') != committed_builds[0]['commandId']
                or built.get('entityId') != committed_builds[0].get('entityId')
                or built['stateVersion'] != committed_builds[0].get('stateVersion')
                or facts.get('createdEntityIds') != [built['entityId']]):
            raise ValueError('Original material construction evidence is damaged')
    elif built is not None or committed_builds or used['wood'] != 0:
        raise ValueError('Unconfirmed material construction cannot spend the task budget')
    if not is_material:
        return
    request, snapshot = pending['request'], pending.get('materialBefore')
    action, step = request['action'], state['steps'][-1]
    if (goal is None or request.get('rulesVersion') != 'r10' or request.get('preconditionMode') != ACTOR_STATE
            or type(pending.get('woodCost')) is not int or pending['woodCost'] != 0
            or not valid_before(snapshot, action['type'])
            or snapshot['actorId'] != mission['actorId'] or snapshot['position'] != step.get('position')
            or snapshot['inventoryWood'] != step.get('inventoryWood') or action != step.get('action')):
        raise ValueError('Original material request or before facts are damaged')
    if action['type'] == 'reserve_material':
        if original is not None or action != {'type': 'reserve_material', 'sourceId': SOURCE}:
            raise ValueError('A task may request only its original reservation')
    elif (original is None or action != {'type': 'harvest_material', 'reservationId': original['reservationId']}
          or any(snapshot['reservation'].get(k) != original[k] for k in
                 ('actorId', 'operatorId', 'requestCommandId', 'queueSequence', 'requestedAtMs', 'reservationId'))
          or snapshot['reservation']['remaining'] != 3 - harvested):
        raise ValueError('Original harvest must retain its reservation and remaining amount')
