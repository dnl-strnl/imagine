from itertools import product
import math
import re
from typing import Any, Dict, List

FPS = 24
MIN_DURATION, MAX_DURATION = 5, 15
# 1344x768 in either orientation.
MAX_PIXELS = 1032192
WORKFLOWS = ('fl2va', 'ref2va')
REFERENCE_LIMITS = dict(image=9, video=3, audio=3)
MAX_REFERENCES = 12

PLACEHOLDER = re.compile(r'\{(\w+)\}')

def snap_num_frames(frames: int, fps: int = FPS) -> int:
    """Snap a frame count up to the next `17 * n + 5` the pipeline accepts.

    Clamped to the 5-15 s window, so 15 s gives 345 frames rather than 362.
    """
    shortest = math.ceil((MIN_DURATION * fps - 5) / 17)
    longest = (MAX_DURATION * fps - 5) // 17
    n = math.ceil((int(frames) - 5) / 17)
    return 17 * min(max(n, shortest), longest) + 5

def snap_frames(duration: float, fps: int = FPS) -> int:
    return snap_num_frames(math.ceil(float(duration) * fps), fps)

def snap_dimension(value: int) -> int:
    return max(256, int(value)) // 32 * 32

def parse_resolution(resolution: Any) -> tuple:
    if isinstance(resolution, str):
        resolution = re.split(r'[x×*,\s]+', resolution.strip().lower())
    width, height = (snap_dimension(v) for v in resolution)
    if width * height > MAX_PIXELS:
        raise ValueError(f'{width}x{height} is larger than the model canvas (1344x768).')
    return width, height

def expand_prompts(templates: List[str], variables: Dict[str, List[str]]) -> List[str]:
    """Fill `{name}` placeholders with every combination of the variables a template uses."""
    prompts = []
    for template in templates:
        template = template.strip()
        if not template:
            continue
        used = [n for n in dict.fromkeys(PLACEHOLDER.findall(template)) if variables.get(n)]
        for values in product(*(variables[n] for n in used)):
            filled = dict(zip(used, values))
            prompt = PLACEHOLDER.sub(
                lambda m: str(filled.get(m.group(1), m.group(0))), template
            )
            if prompt not in prompts:
                prompts.append(prompt)
    return prompts

def _values(value: Any, default: Any) -> List[Any]:
    if value is None or value == '' or value == []:
        return [default]
    return list(value) if isinstance(value, (list, tuple)) else [value]

def _seeds(seeds: Any) -> List[int]:
    if isinstance(seeds, (list, tuple)):
        return [int(s) for s in seeds] or [0]
    seeds = seeds or {}
    base = int(seeds.get('base', 0) or 0)
    return [base + i for i in range(max(1, int(seeds.get('count', 1) or 1)))]

def _input_sets(spec: Dict[str, Any], workflow: str) -> List[Dict[str, Any]]:
    input_sets = []
    for item in spec.get('inputs') or [{}]:
        references = [
            dict(type=r['type'], filename=r['filename'])
            for r in item.get('references') or []
        ]
        first, last = item.get('first_frame') or None, item.get('last_frame') or None

        if workflow == 'ref2va':
            if not references:
                raise ValueError('ref2va needs at least one reference per input set.')
            if first or last:
                raise ValueError('ref2va takes references, not start/end frames.')
            for kind, limit in REFERENCE_LIMITS.items():
                if sum(r['type'] == kind for r in references) > limit:
                    raise ValueError(f'ref2va allows at most {limit} {kind} references.')
            if any(r['type'] not in REFERENCE_LIMITS for r in references):
                raise ValueError('references must be image, video or audio.')
            if all(r['type'] == 'audio' for r in references):
                raise ValueError('ref2va needs an image or video reference besides audio.')
            if len(references) > MAX_REFERENCES:
                raise ValueError(f'ref2va allows at most {MAX_REFERENCES} references.')
        elif references:
            raise ValueError('fl2va takes start/end frames, not references.')

        input_sets.append(dict(first_frame=first, last_frame=last, references=references))
    return input_sets

def config_key(job: Dict[str, Any]) -> str:
    return (
        f"{job['width']}x{job['height']} · {job['duration']:g}s · "
        f"{job['num_inference_steps']} steps"
    )

def expand(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn a sweep spec into jobs, grouped by configuration so an interrupted
    sweep leaves whole configurations finished."""
    workflow = spec.get('workflow') or 'fl2va'
    if workflow not in WORKFLOWS:
        raise ValueError(f'unknown workflow: {workflow!r}')

    prompts = expand_prompts(spec.get('prompts') or [], spec.get('variables') or {})
    if not prompts:
        raise ValueError('a sweep needs at least one prompt.')

    settings = spec.get('settings') or {}
    durations = [float(d) for d in _values(settings.get('duration'), MIN_DURATION)]
    for duration in durations:
        if not MIN_DURATION <= duration <= MAX_DURATION:
            raise ValueError(f'duration must be {MIN_DURATION} to {MAX_DURATION} seconds.')
    resolutions = [parse_resolution(r) for r in _values(settings.get('resolution'), '1344x768')]
    steps = [int(s) for s in _values(settings.get('num_inference_steps'), 50)]
    if any(s < 2 for s in steps):
        raise ValueError('num_inference_steps must be at least 2.')

    input_sets = _input_sets(spec, workflow)
    seeds = _seeds(spec.get('seeds'))
    style = (spec.get('style') or '').strip(' ,')

    jobs = []
    for (width, height), duration, num_inference_steps in product(resolutions, durations, steps):
        for prompt, inputs, seed in product(prompts, input_sets, seeds):
            job = dict(
                workflow=workflow,
                model=spec.get('model'),
                prompt=prompt,
                style=style,
                seed=seed,
                width=width,
                height=height,
                duration=duration,
                num_frames=snap_frames(duration),
                fps=FPS,
                num_inference_steps=num_inference_steps,
                **inputs,
            )
            job['config_key'] = config_key(job)
            jobs.append(job)
    return jobs

def configurations(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped = {}
    for job in jobs:
        group = grouped.setdefault(job['config_key'], dict(
            config_key=job['config_key'],
            width=job['width'],
            height=job['height'],
            duration=job['duration'],
            num_frames=job['num_frames'],
            num_inference_steps=job['num_inference_steps'],
            clips=0,
        ))
        group['clips'] += 1
    return list(grouped.values())
