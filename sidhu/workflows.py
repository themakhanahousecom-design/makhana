"""User-authored workflows only; no shell, recursion, AI-generated plans or implicit sends."""
import re
from .intents import app_intent, website_intent


MAX_STEPS = 10


def validate_workflows(value):
    if not isinstance(value, dict) or len(value) > 30:
        raise ValueError('Workflows must be an object with at most 30 named workflows.')
    validated = {}
    for name, steps in value.items():
        if not isinstance(name, str) or not re.fullmatch(r'[\w -]{1,60}', name, re.UNICODE):
            raise ValueError('Workflow names must contain 1–60 letters, digits, spaces, hyphens or underscores.')
        canonical = name.strip().casefold()
        if not canonical or canonical in validated:
            raise ValueError('Workflow names must be nonempty and unique ignoring case.')
        if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
            raise ValueError(f'{name}: supply 1–{MAX_STEPS} command strings.')
        for step in steps:
            if not isinstance(step, str) or not step.strip() or len(step) > 2000:
                raise ValueError(f'{name}: each step must be a nonempty command of at most 2000 characters.')
            # Deliberately narrower than interactive commands: no AI, notes or workflow recursion.
            command = step.strip().casefold()
            if command.startswith("open ") and not (app_intent(step) or website_intent(step)):
                raise ValueError(f"{name}: open steps must name one supported application or one URL.")
            if not (command in {'diagnostics', 'battery', 'latest pdf', 'recent files', 'duplicates'} or command.startswith(('open ', 'inspect ', 'find ', 'volume ', 'read ', 'search text ', 'document ', 'summarize file ', 'analyze csv '))):
                raise ValueError(f'{name}: only open, inspect, find, volume, diagnostics, battery read, search text, recent files, duplicates and latest PDF are supported.')
        validated[canonical] = [step.strip() for step in steps]
    return validated
