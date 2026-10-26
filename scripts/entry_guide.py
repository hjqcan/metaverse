"""Whitelist the optional read-only arrival guide for a resident's public context."""
from copy import deepcopy


def public_entry_guide(observed):
    guide = observed.get('entryGuide')
    if (not isinstance(guide, dict) or type(guide.get('version')) is not int or guide['version'] != 1
            or guide.get('stateVersion') != observed['stateVersion']
            or guide.get('actorId') != observed['self']['actorId']
            or guide.get('position') != observed['self']['position']):
        return None
    def pick(value, keys):
        return {key: deepcopy(value[key]) for key in keys}
    try:
        result = pick(guide, ('version', 'stateVersion', 'actorId', 'position'))
        result['sharedBridges'] = [pick(b, ('entityId', 'ownerActorId', 'position')) for b in guide['sharedBridges']]
        result['places'] = [pick(p, ('id', 'label', 'position', 'activityId', 'reachable', 'walkingSteps', 'route', 'bridgeEntityIds')) for p in guide['places']]
        result['materials'] = pick(guide['materials'], ('publicWood', 'ownWood', 'depotPosition'))
        result['participation'] = pick(guide['participation'], ('walkWoodCost', 'visitSupported', 'postcardSupported', 'mosaicSupported', 'foreignMosaicNeedsConsent'))
        return result
    except (KeyError, TypeError):
        return None
