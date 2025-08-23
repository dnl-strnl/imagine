import base64
import io
import json
import numpy as np
from omegaconf import DictConfig, OmegaConf
from pathlib import Path
from PIL import Image
from rich.table import Table
from rich.text import Text
from typing import Dict, List, Union
import yaml

def base64_image_array(image_array: np.ndarray) -> str:

    if not isinstance(image_array, np.ndarray):
        image_array = np.array(image_array)

    # handle different array shapes and datatypes.
    if image_array.ndim == 2:
        # handle grayscale image.
        if image_array.dtype != np.uint8:
            if image_array.max() <= 1.0:  # normalize to 0-255 range
                # assume values are in 0-1 range.
                image_array = (image_array * 255).astype(np.uint8)
            else:
                image_array = np.clip(image_array, 0, 255).astype(np.uint8)

        image = Image.fromarray(image_array, mode='L')

    elif image_array.ndim == 3:
        if image_array.shape[2] == 1:
            # handle single channel images as grayscale.
            image_array = np.squeeze(image_array, axis=2)
            if image_array.dtype != np.uint8:
                if image_array.max() <= 1.0:
                    image_array = (image_array * 255).astype(np.uint8)
                else:
                    image_array = np.clip(image_array, 0, 255).astype(np.uint8)
            image = Image.fromarray(image_array, mode='L')

        elif image_array.shape[2] == 3:
            # handle RGB images.
            if image_array.dtype != np.uint8:
                if image_array.max() <= 1.0:
                    image_array = (image_array * 255).astype(np.uint8)
                else:
                    image_array = np.clip(image_array, 0, 255).astype(np.uint8)
            image = Image.fromarray(image_array, mode='RGB')

        elif image_array.shape[2] == 4:
            # handle RGBA images.
            if image_array.dtype != np.uint8:
                if image_array.max() <= 1.0:
                    image_array = (image_array * 255).astype(np.uint8)
                else:
                    image_array = np.clip(image_array, 0, 255).astype(np.uint8)
            image = Image.fromarray(image_array, mode='RGBA')

        else:
            raise ValueError(f'unsupported image shape: {image_array.shape[2]=}')

    else:
        raise ValueError(f'unsupported array shape: {image_array.shape=}')

    image_bytes = io.BytesIO()

    if image.mode == 'L':
        image.save(image_bytes, format='PNG')
    else:
        image.save(image_bytes, format='JPEG')

    image_bytes = image_bytes.getvalue()
    image64 = base64.b64encode(image_bytes).decode('utf-8')
    return image64

def config_table(cfg: DictConfig) -> Table:
    """Create a Rich table from the config for display."""
    table = Table(title='Configuration')
    table.add_column('Parameter', style='cyan')
    table.add_column('Value', style='cyan')

    def add_config_rows(config_dict, prefix=''):
        for key, value in config_dict.items():
            full_key = f'{prefix}.{key}' if prefix else key
            if isinstance(value, DictConfig):
                add_config_rows(value, full_key)
            else:
                table.add_row(full_key, str(value))

    add_config_rows(cfg)
    return table

def load_prompts(
    prompt_config: Union[str, dict, Path], image_files: List[Path]
) -> Dict[str, str]:
    """Load prompts based on configuration type."""

    # handle dictionary input: absolute filepath -> prompt
    if isinstance(prompt_config, dict):
        return {str(k): str(v) for k, v in prompt_config.items()}

    # handle string input (filename or prompt string).
    if isinstance(prompt_config, (str, Path)):
        prompt_path = Path(prompt_config)

        # attempt to load from file.
        if prompt_path.exists():
            return _load_prompts_from_file(prompt_path, image_files)

        # fallback: use single prompt for all images.
        return {str(image_file): str(prompt_config) for image_file in image_files}

    raise ValueError(f'{type(prompt_config)=}')

def _load_prompts_from_file(prompt_path: Path, image_files: List[Path]) -> Dict[str, str]:
    """Load prompts from a file."""
    suffix = prompt_path.suffix.lower()

    if suffix == '.txt':
        return _load_text_prompts(prompt_path, image_files)
    elif suffix in ['.json', '.yaml']:
        return _load_structured_prompts(prompt_path, image_files)
    else:
        raise ValueError(f'Unsupported: {suffix=}')

def _load_text_prompts(prompt_path: Path, image_files: List[Path]) -> Dict[str, str]:
    """Load prompts from a text file."""
    with open(prompt_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        raise ValueError(f'{prompt_path=}: {len(lines)=}')

    if len(lines) == 1:  # one prompt for all images.
        return {str(image_file): lines[0] for image_file in image_files}

    # cycle multiple prompts.
    return {str(image_file): lines[i % len(lines)] for i, image_file in enumerate(image_files)}

def _load_structured_prompts(prompt_path: Path, image_files: List[Path]) -> Dict[str, str]:
    """Load prompts from JSON/YAML file."""

    with open(prompt_path, 'r', encoding='utf-8') as f:
        if prompt_path.suffix.lower() == '.json':
            prompt_data = json.load(f)
        else:
            prompt_data = yaml.safe_load(f)

    prompts = {}
    missing_keys = []
    # create prompt to image mapping...
    for image_file in image_files:
        image_key = str(image_file)

        # find prompt for image using various key formats.
        prompt = None
        candidates = [
            str(image_file),  # full path
            image_file.name,  # filename with extension
            image_file.stem,  # filename without extension
        ]
        for candidate in candidates:
            if candidate in prompt_data:
                prompt = str(prompt_data[candidate])
                break

        if prompt is not None:
            prompts[image_key] = prompt
        else:
            missing_keys.append(image_key)

    if missing_keys:
        raise ValueError(f'No prompts found for images: {missing_keys}')

    return prompts
