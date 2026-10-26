"""Explicit r8 facility goals: public geometry plans; original receipts prove builds."""
from copy import deepcopy
import math

import continuous_navigation as nav

RECIPES = {'platform.v1': ('platform', 3, 1., 1.), 'bridge.v1': ('bridge', 6, 2.4, .8)}


def placement_issue(observed, goal):
    recipe = goal['buildRecipeId']
    definition, cost, hx, hz = RECIPES[recipe]
    x, z = goal['target']
    x0, z0, x1, z1 = observed['world']['bounds']
    if x - hx < x0 or x + hx > x1 or z - hz < z0 or z + hz > z1:
        return 'construction_outside_world'
    river = observed['terrain']['river']
    if definition == 'bridge':
        center = nav._river_x(river['centerline'], z)
        if center is None or abs(x - center) > .08:
            return 'bridge_alignment_required'
    else:
        heights = [z - hz, z + hz, *(p[1] for p in river['centerline'] if z - hz < p[1] < z + hz)]
        if any(x + hx > nav._river_x(river['centerline'], h) - river['halfWidth']
               and x - hx < nav._river_x(river['centerline'], h) + river['halfWidth'] for h in heights):
            return 'platform_requires_land'
    for cx, cz, radius in nav.navigation(observed).circles:
        nearest = (max(x - hx, min(cx, x + hx)), max(z - hz, min(cz, z + hz)))
        if nav.distance((cx, cz), nearest) < radius:
            return 'construction_site_occupied'
    for entity in observed['entities']:
        ex, ez = (2.4, .8) if entity['definitionId'] == 'bridge' else (1., 1.)
        if abs(entity['position'][0] - x) < ex + hx and abs(entity['position'][1] - z) < ez + hz:
            return 'construction_site_occupied'
    return None


def approach(observed, target):
    """Find a reachable actual position in build reach; never create access bridges."""
    start = observed['self']['position']
    movement = observed['movement']
    geometry = nav.navigation(observed)
    if nav.distance(start, target) <= movement['buildReach'] and geometry.walkable(start):
        return []
    angle = math.atan2(start[1] - target[1], start[0] - target[0])
    reach = movement['buildReach'] - .12
    candidates = [[target[0] + reach * math.cos(a), target[1] + reach * math.sin(a)]
                  for a in (angle, *(i * math.tau / 16 for i in range(16)))]
    candidates.append(target)
    for point in sorted(candidates, key=lambda p: nav.distance(start, p)):
        path = geometry.route(start, point)
        if path is not None:
            return path
    return None


def plan(observed, goal, allow_gather):
    recipe = goal['buildRecipeId']
    definition, cost, _, _ = RECIPES[recipe]
    empty = {'reason': None, 'cells': [], 'bridges': int(definition == 'bridge'),
             'wood': cost, 'commands': None, 'nextAction': None}
    published = next((r for r in observed['recipes'] if r['id'] == recipe), None)
    if published is None or type(published['woodCost']) is not int or published['woodCost'] != cost:
        return {**empty, 'reason': 'construction_recipe_unavailable'}
    issue = placement_issue(observed, goal)
    if issue:
        return {**empty, 'reason': issue}
    path = approach(observed, goal['target'])
    if path is None:
        return {**empty, 'reason': 'construction_site_unreachable'}
    shortage = max(0, cost - observed['self']['inventory']['wood'])
    if shortage:
        if not allow_gather:
            return {**empty, 'reason': 'natural_material_collection_required'}
        collecting = nav.collect(observed, shortage)
        if collecting['reason']:
            return {**empty, 'reason': collecting['reason']}
        after = plan(collecting['forecast'], goal, False)
        if after['reason']:
            return after
        return {**after, 'commands': after['commands'] + 2 * collecting['commands'],
                'nextAction': collecting['actions'][0], 'nextReason': '采集本次指定设施所需木材'}
    forecast = deepcopy(observed)
    forecast['entities'].append({'definitionId': definition, 'position': deepcopy(goal['target'])})
    landing = path[-1] if path else observed['self']['position']
    onward = nav.navigation(forecast).route(landing, goal['target'])
    back = nav.navigation(forecast).route(goal['target'], observed['self']['position'])
    if onward is None or back is None:
        return {**empty, 'reason': 'construction_site_unreachable'}
    step = observed['movement']['maxStepDistance']
    commands = nav.walk_count(observed['self']['position'], path, step) + 1
    commands += nav.walk_count(landing, onward, step) + nav.walk_count(goal['target'], back, step)
    action = {'type': 'walk', 'to': list(path[0])} if path else {'type': 'build', 'recipeId': recipe, 'at': deepcopy(goal['target'])}
    return {**empty, 'cells': path, 'commands': commands, 'nextAction': action,
            'nextReason': '走到指定建造地点旁' if path else '建造本任务选定的设施'}


def evidence(receipt, intent, actor, before, observed):
    """Bind a build receipt and its resulting public entity to this original command."""
    result = receipt.get('result')
    recipe = intent['action'].get('recipeId')
    if recipe not in RECIPES or not isinstance(result, dict) or not isinstance(before, dict):
        return None
    definition, cost, _, _ = RECIPES[recipe]
    position = intent['action'].get('at')
    if (receipt.get('commandId') != intent['commandId'] or receipt.get('status') != 'committed'
            or type(receipt.get('schemaVersion')) is not int or receipt['schemaVersion'] != 1
            or receipt.get('rulesVersion') != 'r8' or not isinstance(receipt.get('identity'), dict)
            or receipt['identity'].get('actorId') != actor
            or type(receipt.get('stateVersion')) is not int or receipt['stateVersion'] != intent['expectedStateVersion'] + 1
            or observed['stateVersion'] < receipt['stateVersion'] or observed['self']['actorId'] != actor
            or result.get('action') != 'build' or not nav.point(result.get('position')) or result['position'] != position
            or not isinstance(result.get('entityId'), str) or not result['entityId']
            or type(result.get('inventoryWood')) is not int or result['inventoryWood'] != before['inventoryWood'] - cost):
        return None
    entity = next((e for e in observed['entities'] if e['entityId'] == result['entityId']), None)
    if (entity is None or entity['ownerActorId'] != actor or entity['rulesVersion'] != 'r8'
            or entity['definitionId'] != definition or entity['definitionVersion'] != 1
            or entity['position'] != position or entity['embodiedWood'] != cost):
        return None
    return {'commandId': intent['commandId'], 'entityId': entity['entityId'], 'recipeId': recipe,
            'definitionId': definition, 'ownerActorId': actor, 'position': deepcopy(position),
            'woodSpent': cost, 'stateVersion': receipt['stateVersion']}
