"""Continuous XZ navigation from public r8/r9/r10 geometry; the server confirms movement."""
from copy import deepcopy
from functools import lru_cache
import heapq
import json
import math

ARRIVAL_TOLERANCE = 0.06
MARGIN = 0.035
ENTITY_HALF_SIZE = {'platform': (1., 1.), 'bridge': (2.4, .8),
                    'workbench': (1., .5), 'wooden_chest': (.5, .5)}
FURNITURE = {'workbench', 'wooden_chest'}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def point(value):
    return isinstance(value, (list, tuple)) and len(value) == 2 and all(finite(n) for n in value)


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def near(a, b):
    return distance(a, b) <= ARRIVAL_TOLERANCE


def continuous(observed):
    expected = {'r8': 'wilderness-continuous-v1', 'r9': 'wilderness-cooperation-v1',
                'r10': 'wilderness-material-access-v1'}.get(observed.get('rulesVersion'))
    return (expected is not None and observed.get('world', {}).get('scenarioId') == expected
            and observed.get('world', {}).get('coordinateSystem') == 'continuous-xz')


def public_geometry(observed):
    terrain = observed['terrain']
    return {'version': terrain['version'],
            'river': {key: deepcopy(terrain['river'][key]) for key in ('polygon', 'centerline', 'halfWidth')},
            'obstacles': [{key: deepcopy(o[key]) for key in ('id', 'kind', 'position', 'radius')} for o in terrain['obstacles']]}


def validate_observation(observed):
    movement, terrain, world = observed.get('movement', {}), observed.get('terrain', {}), observed['world']
    if (movement.get('version') != 1 or movement.get('kind') != 'continuous' or terrain.get('version') != 1
            or not point(observed['self']['position'])
            or any(not finite(movement.get(k)) or movement[k] <= 0 for k in ('speed', 'radius', 'maxStepDistance', 'gatherReach', 'buildReach'))
            or not isinstance(world.get('bounds'), list) or len(world['bounds']) != 4
            or not all(finite(n) for n in world['bounds'])
            or world['bounds'] != [0, 0, world['width'], world['height']]):
        raise ValueError('Invalid continuous movement observation')
    for field, minimum in (('polygon', 3), ('centerline', 2)):
        vertices = terrain.get('river', {}).get(field)
        if not isinstance(vertices, list) or len(vertices) < minimum or not all(point(p) for p in vertices):
            raise ValueError('Invalid continuous river geometry')
    if any(not point(o.get('position')) or not finite(o.get('radius')) or o['radius'] <= 0 for o in terrain.get('obstacles', [])):
        raise ValueError('Invalid continuous obstacle geometry')
    furniture_geometry(observed)
    forestry_circles(observed)


def entity_half_size(entity):
    definition = entity.get('definitionId')
    if definition not in ENTITY_HALF_SIZE or not point(entity.get('position')):
        raise ValueError('Unknown or malformed continuous entity geometry')
    return ENTITY_HALF_SIZE[definition]


def furniture_geometry(observed, exclude_entity_id=None):
    """Only a named interaction ray may omit its target, never ordinary walking."""
    cap = observed.get('workshop')
    if cap is not None and (not isinstance(cap, dict) or cap.get('capability') != 'workshop-v1'
                            or type(cap.get('version')) is not int or cap['version'] != 1):
        raise ValueError('Unknown workshop geometry capability')
    rectangles = []
    for entity in observed['entities']:
        hx, hz = entity_half_size(entity)
        if entity['definitionId'] not in FURNITURE:
            continue
        if (cap is None or entity.get('rulesVersion') != 'r10'
                or type(entity.get('definitionVersion')) is not int or entity['definitionVersion'] != 1
                or not isinstance(entity.get('entityId'), str) or not entity['entityId']):
            raise ValueError('Furniture requires its explicit supported capability and identity')
        if entity['entityId'] != exclude_entity_id:
            rectangles.append([*entity['position'], hx, hz])
    return rectangles


def forestry_circles(observed, interaction_obstacle=None):
    """Validate forestry obstacles and omit only a named target for its ray."""
    cap = observed.get('forestry')
    obstacles = observed['terrain']['obstacles']
    kinds = ('forestry_nursery', 'forestry_tree')
    tagged = [o for o in obstacles if o.get('kind') in kinds]
    expected = {}
    if cap is not None:
        if (not isinstance(cap, dict) or cap.get('capability') != 'forestry-v1'
                or type(cap.get('version')) is not int or cap['version'] != 1):
            raise ValueError('Unknown forestry geometry capability')
        nursery, plots, plants = cap.get('nursery'), cap.get('plots'), cap.get('plants')
        if (not isinstance(nursery, dict) or nursery.get('sourceId') != 'nursery-west'
                or not point(nursery.get('position')) or nursery['position'] != [7, 6]
                or not finite(nursery.get('radius')) or nursery['radius'] != .3
                or not isinstance(plots, list) or len(plots) != 4 or not isinstance(plants, list)):
            raise ValueError('Incomplete forestry geometry')
        centers = {}
        for p in plots:
            if (not isinstance(p, dict) or not isinstance(p.get('plotId'), str) or p['plotId'] in centers
                    or not point(p.get('position')) or not finite(p.get('radius')) or p['radius'] != .45):
                raise ValueError('Invalid forestry plot geometry')
            centers[p['plotId']] = p['position']
        expected['nursery-west'] = ('forestry_nursery', nursery['position'], .3)
        for p in plants:
            if (not isinstance(p, dict) or not isinstance(p.get('plantId'), str) or not p['plantId']
                    or p['plantId'] in expected or p.get('plotId') not in centers or p.get('state') not in ('growing', 'mature')):
                raise ValueError('Invalid original forestry plant geometry')
            expected[p['plantId']] = ('forestry_tree', centers[p['plotId']], .45)
        if (len(tagged) != len(expected) or len({o.get('id') for o in tagged}) != len(tagged)
                or any(o.get('id') not in expected or [o.get('kind'), o.get('position'), o.get('radius')] != list(expected[o['id']]) for o in tagged)):
            raise ValueError('Public forestry obstacles do not match the original plants')
    elif tagged:
        raise ValueError('Forestry obstacles require an explicit supported capability')
    if interaction_obstacle is not None and interaction_obstacle not in expected:
        raise ValueError('Only the original forestry interaction target may be omitted')
    return [[*o['position'], o['radius']] for o in obstacles if o.get('id') != interaction_obstacle]


def _point_segment(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = min(1, max(0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length)) if length else 0
    return distance(p, (a[0] + t * dx, a[1] + t * dy))


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_distance(a, b, c, d):
    # Endpoint distance covers collinear disjoint segments, including zero length.
    ab_c, ab_d, cd_a, cd_b = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    if ab_c * ab_d < 0 and cd_a * cd_b < 0:
        return 0
    return min(_point_segment(a, c, d), _point_segment(b, c, d), _point_segment(c, a, b), _point_segment(d, a, b))


def _point_rectangle(p, rectangle):
    x, z, hx, hz = rectangle
    return math.hypot(max(abs(p[0] - x) - hx, 0), max(abs(p[1] - z) - hz, 0))


def _segment_rectangle(a, b, rectangle):
    if _point_rectangle(a, rectangle) == 0 or _point_rectangle(b, rectangle) == 0:
        return 0.
    x, z, hx, hz = rectangle
    vertices = [(x-hx, z-hz), (x+hx, z-hz), (x+hx, z+hz), (x-hx, z+hz)]
    return min(_segments_distance(a, b, c, d) for c, d in zip(vertices, vertices[1:] + vertices[:1]))


def _inside(p, polygon):
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


class Navigation:
    def __init__(self, geometry):
        self.bounds, self.radius = geometry['bounds'], geometry['radius']
        self.river = geometry['river']
        self.circles = geometry['circles']
        self.bridges = geometry['bridges']
        self.rectangles = geometry.get('rectangles', [])
        self.nodes = []
        self.edges = None

    def _covered(self, p):
        return any(abs(p[0] - b[0]) <= 2.4 - self.radius and abs(p[1] - b[1]) <= .8 - self.radius for b in self.bridges)

    def walkable(self, p):
        x0, z0, x1, z1 = self.bounds
        if not (x0 + self.radius <= p[0] <= x1 - self.radius and z0 + self.radius <= p[1] <= z1 - self.radius):
            return False
        if any(distance(p, c[:2]) < c[2] + self.radius - 1e-9 for c in self.circles):
            return False
        if any(_point_rectangle(p, rectangle) < self.radius - 1e-9 for rectangle in self.rectangles):
            return False
        if self._covered(p):
            return True
        return not _inside(p, self.river) and all(_point_segment(p, a, b) >= self.radius - 1e-9 for a, b in zip(self.river, self.river[1:] + self.river[:1]))

    def clear(self, a, b):
        if not self.walkable(a) or not self.walkable(b):
            return False
        if any(_point_segment(c[:2], a, b) < c[2] + self.radius - 1e-9 for c in self.circles):
            return False
        if any(_segment_rectangle(a, b, rectangle) < self.radius - 1e-9 for rectangle in self.rectangles):
            return False
        dx, dz = b[0] - a[0], b[1] - a[1]
        cuts = [0., 1.]
        for center in self.bridges:
            for dimension, half in ((0, 2.4 - self.radius), (1, .8 - self.radius)):
                delta = dx if dimension == 0 else dz
                if abs(delta) > 1e-12:
                    for edge in (center[dimension] - half, center[dimension] + half):
                        t = (edge - a[dimension]) / delta
                        if 0 < t < 1:
                            cuts.append(t)
        cuts.sort()
        at = lambda t: (a[0] + dx * t, a[1] + dz * t)
        for start, end in zip(cuts, cuts[1:]):
            if self._covered(at((start + end) / 2)):
                continue
            lo, hi = at(start), at(end)
            if _inside(at((start + end) / 2), self.river):
                return False
            if any(_segments_distance(lo, hi, c, d) < self.radius - 1e-9 for c, d in zip(self.river, self.river[1:] + self.river[:1])):
                return False
        return True

    def _graph(self):
        if self.edges is not None:
            return
        candidates = []
        for x, z, radius in [*self.circles, *((p[0], p[1], 0) for p in self.river)]:
            size = (radius + self.radius + MARGIN) / math.cos(math.pi / 12)
            candidates.extend((x + math.cos(i * math.tau / 12) * size, z + math.sin(i * math.tau / 12) * size) for i in range(12))
        clearance = (self.radius + MARGIN) / math.cos(math.pi / 12)
        for x, z, hx, hz in self.rectangles:
            for cx in (x-hx, x+hx):
                for cz in (z-hz, z+hz):
                    candidates.extend((cx + math.cos(i * math.tau / 12) * clearance,
                                       cz + math.sin(i * math.tau / 12) * clearance) for i in range(12))
        x0, z0, x1, z1 = self.bounds
        padding = self.radius + MARGIN
        candidates.extend((x, z) for x in (x0 + padding, x1 - padding) for z in (z0 + padding, z1 - padding))
        for x, z in self.bridges:
            candidates.extend(((x - 2.7, z), (x, z), (x + 2.7, z)))
        self.nodes = list(dict.fromkeys(p for p in candidates if self.walkable(p)))
        self.edges = [[] for _ in self.nodes]
        for i, a in enumerate(self.nodes):
            for j in range(i):
                b = self.nodes[j]
                if self.clear(a, b):
                    length = distance(a, b)
                    self.edges[i].append((j, length)); self.edges[j].append((i, length))

    def route(self, start, target):
        start, target = tuple(start), tuple(target)
        if not self.walkable(start) or not self.walkable(target):
            return None
        if near(start, target):
            return []
        if self.clear(start, target):
            return [target]
        self._graph()
        count = len(self.nodes)
        nodes = [*self.nodes, start, target]
        edges = [list(row) for row in self.edges] + [[], []]
        for endpoint in (count, count + 1):
            for i, p in enumerate(self.nodes):
                if self.clear(nodes[endpoint], p):
                    length = distance(nodes[endpoint], p)
                    edges[endpoint].append((i, length)); edges[i].append((endpoint, length))
        queue = [(0., count)]
        best, previous = {count: 0.}, {}
        while queue:
            cost, index = heapq.heappop(queue)
            if cost != best[index]:
                continue
            if index == count + 1:
                path = []
                while index != count:
                    path.append(nodes[index]); index = previous[index]
                return list(reversed(path))
            for nxt, length in edges[index]:
                new = cost + length
                if new < best.get(nxt, math.inf):
                    best[nxt], previous[nxt] = new, index
                    heapq.heappush(queue, (new, nxt))
        return None


@lru_cache(maxsize=96)
def _navigation(encoded):
    return Navigation(json.loads(encoded))


def navigation(observed, *, interaction_target=None, interaction_obstacle=None):
    geometry = {'bounds': observed['world']['bounds'], 'radius': observed['movement']['radius'],
                'river': observed['terrain']['river']['polygon'],
                'circles': forestry_circles(observed, interaction_obstacle),
                'bridges': [e['position'] for e in observed['entities'] if e['definitionId'] == 'bridge'],
                'rectangles': furniture_geometry(observed, interaction_target)}
    geometry['circles'] += [[*n['position'], .45] for n in observed['resourceNodes'] if n['remainingWood'] > 0]
    return _navigation(json.dumps(geometry, sort_keys=True, separators=(',', ':')))


def path_length(start, path):
    return sum(distance(a, b) for a, b in zip([start, *path], path))


def walk_count(start, path, step):
    return sum(math.ceil(max(0, distance(a, b) - ARRIVAL_TOLERANCE) / step) for a, b in zip([start, *path], path))


def collect(observed, quantity):
    forecast, actions, commands = deepcopy(observed), [], 0
    while quantity > 0:
        nav, choices = navigation(forecast), []
        start = forecast['self']['position']
        reach = forecast['movement']['gatherReach']
        for node in sorted(forecast['resourceNodes'], key=lambda n: (distance(start, n['position']), n['nodeId'])):
            if node['remainingWood'] <= 0:
                continue
            center = node['position']
            if distance(start, center) <= reach:
                choices.append((0., node['nodeId'], [], node))
                break
            angle = math.atan2(start[1] - center[1], start[0] - center[0])
            for heading in [angle, *(i * math.tau / 12 for i in range(12))]:
                target = [center[0] + (reach - .12) * math.cos(heading), center[1] + (reach - .12) * math.sin(heading)]
                path = nav.route(start, target)
                if path is not None:
                    choices.append((path_length(start, path), node['nodeId'], path, node))
                    break
            if choices:
                break
        if not choices:
            return {'reason': 'insufficient_reachable_natural_material'}
        _, _, path, node = min(choices, key=lambda c: (c[0], c[1]))
        actions.extend({'type': 'walk', 'to': list(p)} for p in path)
        commands += walk_count(start, path, forecast['movement']['maxStepDistance'])
        if path:
            forecast['self']['position'] = list(path[-1])
        count = min(quantity, node['remainingWood'])
        actions.extend({'type': 'gather', 'nodeId': node['nodeId']} for _ in range(count))
        commands += count
        node['remainingWood'] -= count
        forecast['self']['inventory']['wood'] += count
        quantity -= count
    return {'reason': None, 'actions': actions, 'forecast': forecast, 'commands': commands}


def _river_x(line, z):
    for a, b in zip(line, line[1:]):
        if a[1] <= z <= b[1]:
            t = (z - a[1]) / (b[1] - a[1])
            return a[0] + (b[0] - a[0]) * t
    return None


def _bridge_free(observed, center):
    x, z = center
    x0, z0, x1, z1 = observed['world']['bounds']
    if x - 2.4 < x0 or x + 2.4 > x1 or z - .8 < z0 or z + .8 > z1:
        return False
    for cx, cz, radius in navigation(observed).circles:
        closest = (max(x - 2.4, min(cx, x + 2.4)), max(z - .8, min(cz, z + .8)))
        if distance((cx, cz), closest) < radius + MARGIN:
            return False
    for entity in observed['entities']:
        hx, hz = entity_half_size(entity)
        if abs(entity['position'][0] - x) < hx + 2.4 + MARGIN and abs(entity['position'][1] - z) < hz + .8 + MARGIN:
            return False
    return True


def route_info(observed, target, allow_build, allow_gather):
    start, movement = observed['self']['position'], observed['movement']
    nav = navigation(observed)
    path = nav.route(start, target)
    if path is not None:
        return {'reason': None, 'cells': path, 'bridges': 0, 'wood': 0,
                'commands': 2 * walk_count(start, path, movement['maxStepDistance']),
                'nextAction': {'type': 'walk', 'to': list(path[0])} if path else None,
                'nextReason': '沿连续地形前往当前目标'}
    missing = {'reason': 'no_route', 'cells': [], 'bridges': None, 'wood': None, 'commands': None}
    if not allow_build:
        return missing
    recipe = next((r for r in observed['recipes'] if r['id'] == 'bridge.v1'), None)
    if not recipe or recipe['woodCost'] != 6:
        return {**missing, 'reason': 'bridge_recipe_unavailable'}
    line = observed['terrain']['river']['centerline']
    heights = [start[1], target[1], (start[1] + target[1]) / 2, *(p[1] for p in line)]
    heights += [(a[1] + b[1]) / 2 for a, b in zip(line, line[1:])]
    candidates = []
    for z in sorted(set(heights)):
        x = _river_x(line, z)
        if x is None or not _bridge_free(observed, (x, z)):
            continue
        for side in (-1, 1):
            landing, exit_point = (x + side * 2.7, z), (x - side * 2.7, z)
            estimate = distance(start, landing) + distance(exit_point, target)
            candidates.append((estimate, z, x, landing, exit_point))
    choices = []
    for _, z, x, landing, exit_point in sorted(candidates):
        approach, onward = nav.route(start, landing), nav.route(exit_point, target)
        if approach is None or onward is None:
            continue
        forecast = deepcopy(observed)
        forecast['entities'].append({'definitionId': 'bridge', 'position': [x, z]})
        if not navigation(forecast).clear(landing, exit_point):
            continue
        length = path_length(start, approach) + distance(landing, exit_point) + path_length(exit_point, onward)
        choices.append((length, z, x, approach, [*approach, exit_point, *onward]))
        break
    if not choices:
        return missing
    _, z, x, approach, route = min(choices, key=lambda c: c[:3])
    shortage = max(0, 6 - observed['self']['inventory']['wood'])
    if shortage:
        if not allow_gather:
            return {**missing, 'reason': 'natural_material_collection_required', 'bridges': 1, 'wood': 6}
        collected = collect(observed, shortage)
        if collected['reason']:
            return {**missing, 'reason': collected['reason'], 'bridges': 1, 'wood': 6}
        after = route_info(collected['forecast'], target, True, False)
        if after['reason']:
            return after
        # Return estimate includes the material detour; runtime still checks every budget.
        return {**after, 'commands': after['commands'] + 2 * collected['commands'],
                'nextAction': collected['actions'][0],
                'nextReason': '采集建桥所需木材' if collected['actions'][0]['type'] == 'gather' else '沿连续路径走到树旁'}
    action = {'type': 'build', 'recipeId': 'bridge.v1', 'at': [x, z]} if distance(start, (x, z)) <= movement['buildReach'] else {'type': 'walk', 'to': list(approach[0])}
    return {'reason': None, 'cells': route, 'bridges': 1, 'wood': 6,
            'commands': 2 * walk_count(start, route, movement['maxStepDistance']) + 1,
            'nextAction': action, 'nextReason': '搭建跨过河道的公共桥' if action['type'] == 'build' else '走到合适的河岸建桥位置'}


def valid_walk_receipt(receipt, intent, actor, before):
    from command_preconditions import valid_execution
    result = receipt.get('result')
    if (not isinstance(result, dict) or not isinstance(receipt.get('identity'), dict)
            or receipt['identity'].get('actorId') != actor or receipt.get('rulesVersion') != intent.get('rulesVersion')
            or intent.get('rulesVersion') not in ('r8', 'r9', 'r10')
            or type(receipt.get('schemaVersion')) is not int or receipt['schemaVersion'] != 1
            or not valid_execution(receipt, intent)
            or not isinstance(before, dict) or not point(before.get('position'))
            or not finite(before.get('maxStepDistance')) or not 0 < before['maxStepDistance'] <= .6
            or not point(result.get('position')) or type(result.get('blocked')) is not bool):
        return False
    start, end, target = before['position'], result['position'], intent['action']['to']
    return (distance(start, end) <= before['maxStepDistance'] + 1e-6
            and _point_segment(end, start, target) < 1e-6)
