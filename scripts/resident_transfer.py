"""Explicit gifts at a frozen meeting point; no implicit authority to spend or chase."""
from copy import deepcopy
import re

import continuous_navigation as nav
from command_preconditions import ACTOR_STATE, integer, point, valid_execution

CAPABILITY = {'version': 1, 'resource': 'wood', 'maxQuantity': 12, 'reach': 1.6, 'recipientConfirmation': False}


def valid_goal(value):
    return (isinstance(value, dict) and set(value) == {'recipientActorId', 'resource', 'quantity'}
            and isinstance(value['recipientActorId'], str)
            and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value['recipientActorId']) is not None
            and value['resource'] == 'wood' and type(value['quantity']) is int and 1 <= value['quantity'] <= 12)


def supported(observed):
    capability = observed.get('materialTransfer')
    return (observed.get('rulesVersion') == 'r9' and observed.get('world', {}).get('scenarioId') == 'wilderness-cooperation-v1'
            and isinstance(capability, dict) and type(capability.get('version')) is int
            and capability.get('recipientConfirmation') is False and capability == CAPABILITY)


def plan(observed, goal, allow_build, allow_gather):
    transfer = goal['transfer']
    quantity = transfer['quantity']
    empty = {'reason': None, 'cells': [], 'bridges': 0, 'wood': quantity, 'commands': None, 'nextAction': None}
    if not supported(observed):
        return {**empty, 'reason': 'transfer_unavailable'}
    recipient = next((r for r in observed.get('residents', []) if r['actorId'] == transfer['recipientActorId']), None)
    if recipient is None or recipient['actorId'] == observed['self']['actorId']:
        return {**empty, 'reason': 'transfer_recipient_unavailable'}
    geometry = nav.navigation(observed)
    if (nav.distance(goal['target'], recipient['position']) > CAPABILITY['reach']
            or not geometry.clear(goal['target'], recipient['position'])):
        return {**empty, 'reason': 'transfer_recipient_not_at_meeting'}
    route = nav.route_info(observed, goal['target'], allow_build, allow_gather)
    if route['reason']:
        return {**route, 'wood': route['wood'] + quantity if route['wood'] is not None else None}
    cost = route['wood'] + quantity
    shortage = max(0, cost - observed['self']['inventory']['wood'])
    if shortage and not allow_gather:
        return {**empty, 'wood': cost, 'reason': 'transfer_material_unavailable'}
    if route['bridges']:
        # Total authorized spending includes the gift, but the current bridge stage
        # needs only its own six wood. The new bridge may make later sources reachable.
        # Re-observe after every real action; never forecast a gift as already delivered.
        return {**route, 'wood': cost, 'commands': route['commands'] + shortage + 1}
    if shortage:
        collecting = nav.collect(observed, shortage)
        if collecting['reason']:
            return {**empty, 'wood': cost, 'reason': collecting['reason']}
        after = plan(collecting['forecast'], goal, allow_build, False)
        if after['reason']:
            return after
        return {**after, 'commands': after['commands'] + 2 * collecting['commands'],
                'nextAction': collecting['actions'][0], 'nextReason': '采集已授权赠送与通路所需木材'}
    at_meeting = nav.near(observed['self']['position'], goal['target'])
    return {**route, 'wood': cost, 'commands': route['commands'] + 1,
            'nextAction': {'type': 'transfer', **deepcopy(transfer)} if at_meeting else route['nextAction'],
            'nextReason': '在会面点交付已授权的木材' if at_meeting else '前往已选赠送会面点'}


def valid_before(before):
    return (isinstance(before, dict) and set(before) == {'position', 'inventoryWood'}
            and point(before['position']) and integer(before['inventoryWood']) and before['inventoryWood'] <= 12)


def validate_saved(state):
    """Reject damaged transfer authorization/accounting before any network operation."""
    pending = state['_state'].get('pending')
    if pending is None or pending.get('request', {}).get('action', {}).get('type') != 'transfer':
        return
    mission, spec = state['mission'], state['_state']['spec']
    goal, request = mission.get('goal'), pending['request']
    action = request['action']
    if (mission.get('allowTransfer') is not True or spec.get('allowTransfer') is not True
            or not isinstance(goal, dict) or goal not in spec['goals'] or not valid_goal(goal.get('transfer'))
            or action != {'type': 'transfer', **goal['transfer']} or request.get('rulesVersion') != 'r9'
            or request.get('preconditionMode') != ACTOR_STATE or not valid_before(pending.get('transferBefore'))
            or type(pending.get('woodCost')) is not int or pending['woodCost'] != action['quantity']
            or action['recipientActorId'] == mission['actorId']):
        raise ValueError('Original transfer permission or evidence is damaged')
    before, step = pending['transferBefore'], state['steps'][-1]
    if (before['inventoryWood'] < action['quantity'] or before['inventoryWood'] != step.get('inventoryWood')
            or before['position'] != step.get('position') or not nav.near(before['position'], goal['target'])):
        raise ValueError('Original transfer before facts do not match the frozen funded meeting')


def evidence(receipt, intent, actor, before, instance):
    action, result = intent['action'], receipt.get('result')
    if (not valid_before(before) or not isinstance(result, dict) or intent.get('rulesVersion') != 'r9'
            or receipt.get('rulesVersion') != intent['rulesVersion'] or type(receipt.get('schemaVersion')) is not int
            or receipt['schemaVersion'] != 1 or receipt.get('commandId') != intent['commandId']
            or not isinstance(receipt.get('identity'), dict)
            or receipt.get('identity', {}).get('actorId') != actor or not valid_execution(receipt, intent)
            or result.get('action') != 'transfer' or result.get('senderActorId') != actor
            or result.get('recipientActorId') != action['recipientActorId'] or result.get('resource') != 'wood'
            or not integer(result.get('quantity')) or result['quantity'] != action['quantity']
            or not integer(result.get('inventoryWood')) or result['inventoryWood'] != before['inventoryWood'] - action['quantity']):
        return None
    return {'worldInstanceId': instance, 'commandId': intent['commandId'], 'senderActorId': actor,
            'recipientActorId': action['recipientActorId'], 'resource': 'wood', 'quantity': action['quantity'],
            'position': deepcopy(before['position']), 'inventoryWoodBefore': before['inventoryWood'],
            'inventoryWoodAfter': result['inventoryWood'], 'stateVersion': receipt['stateVersion']}
