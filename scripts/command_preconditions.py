"""Freeze the chosen command mode and verify its original execution evidence."""
from foundation_agent import valid_world_instance
from math import isfinite

ACTOR_STATE = 'actor-state-v1'


def integer(value):
    return type(value) is int and value >= 0


def point(value):
    return (isinstance(value, list) and len(value) == 2
            and all(type(n) in (int, float) and isfinite(n) for n in value))


def select_mode(observed):
    capability = observed.get('commandConcurrency')
    if (observed.get('rulesVersion') in ('r8', 'r9')
            and valid_world_instance(observed.get('world', {}).get('instanceId'))
            and isinstance(capability, dict) and type(capability.get('version')) is int
            and capability['version'] == 1 and isinstance(capability.get('supportedModes'), list)
            and ACTOR_STATE in capability['supportedModes']):
        return ACTOR_STATE
    return None


def saved_mode(state):
    """Never negotiate again or silently downgrade a damaged new task."""
    binding, mission = state['_state']['binding'], state['mission']
    marked = 'preconditionBindingVersion' in binding
    if not marked:
        if 'preconditionMode' in binding or 'preconditionMode' in mission:
            raise ValueError('Missing original command precondition binding version')
        mode = None
    else:
        version = binding['preconditionBindingVersion']
        if type(version) is not int or version != 1:
            raise ValueError('Unknown command precondition binding version')
        if 'preconditionMode' not in binding or 'preconditionMode' not in mission:
            raise ValueError('Missing original command precondition mode')
        mode = binding['preconditionMode']
        if mode not in (None, ACTOR_STATE) or mission['preconditionMode'] != mode:
            raise ValueError('Persisted command precondition modes disagree')
        if mode == ACTOR_STATE and (binding.get('rulesVersion') not in ('r8', 'r9')
                                   or not valid_world_instance(binding.get('instanceId'))):
            raise ValueError('Actor-state commands require the original protected continuous world')
    pending = state['_state'].get('pending')
    if pending is not None:
        intent = pending['request']
        if mode is None:
            if 'preconditionMode' in intent:
                raise ValueError('Strict pending command cannot acquire a new mode')
        else:
            step = state['steps'][-1] if state['steps'] else {}
            action = intent.get('action', {}).get('type')
            required = {'walk': ('walkBefore', ('position', 'maxStepDistance')),
                        'gather': ('gatherBefore', ('position', 'remainingWood', 'inventoryWood')),
                        'build': ('constructionBefore', ('inventoryWood',)),
                        'transfer': ('transferBefore', ('position', 'inventoryWood'))}
            if (intent.get('preconditionMode') != mode or action not in required
                    or not integer(intent.get('expectedStateVersion'))
                    or step.get('commandId') != intent.get('commandId')
                    or step.get('preconditionMode') != mode
                    or step.get('expectedStateVersion') != intent['expectedStateVersion']):
                raise ValueError('Original pending command precondition evidence is damaged')
            name, fields = required[action]
            if not isinstance(pending.get(name), dict) or not all(k in pending[name] for k in fields):
                raise ValueError('Original pending command is missing its before facts')
            before = pending[name]
            if action == 'walk':
                valid = (point(before['position']) and type(before['maxStepDistance']) in (int, float)
                         and 0 < before['maxStepDistance'] <= .6)
            elif action == 'gather':
                valid = (point(before['position']) and integer(before['remainingWood'])
                         and 1 <= before['remainingWood'] <= 3 and integer(before['inventoryWood'])
                         and before['inventoryWood'] < 12)
            elif action == 'transfer':
                valid = (binding['rulesVersion'] == 'r9' and point(before['position'])
                         and integer(before['inventoryWood']) and before['inventoryWood'] <= 12)
            else:
                valid = integer(before['inventoryWood']) and before['inventoryWood'] <= 12
            if not valid:
                raise ValueError('Original pending command has invalid before facts')
    if mode is None and any('preconditionMode' in step or 'execution' in step for step in state['steps']):
        raise ValueError('Actor-state steps cannot be downgraded to a strict task')
    return mode


def valid_execution(receipt, intent, *, committed=True):
    """Match E and S, retaining the old E+1 check for every strict command."""
    expected, version = intent.get('expectedStateVersion'), receipt.get('stateVersion')
    if (not integer(expected) or not integer(version)
            or receipt.get('status') != ('committed' if committed else 'rejected')):
        return False
    if 'preconditionMode' not in intent:
        return 'execution' not in receipt and (version == expected + 1 if committed else True)
    execution = receipt.get('execution')
    if (intent['preconditionMode'] != ACTOR_STATE or not isinstance(execution, dict)
            or execution.get('preconditionMode') != ACTOR_STATE
            or not integer(execution.get('observedStateVersion'))
            or execution['observedStateVersion'] != expected
            or not integer(execution.get('appliedOnStateVersion'))):
        return False
    applied = execution['appliedOnStateVersion']
    if committed:
        return applied >= expected and version == applied + 1
    return version == applied and (applied >= expected or
                                  (receipt.get('error') or {}).get('code') == 'STATE_VERSION_AHEAD')
