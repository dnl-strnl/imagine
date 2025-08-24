import base64
import io
import json
import numpy as np
from omegaconf import DictConfig, OmegaConf
from pathlib import Path
from PIL import Image
from rich.table import Table
from rich.text import Text
from typing import Dict, List, Optional, Union
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
    prompt_config: Union[str, dict, Path, List[str]],
    image_files: Optional[List[Path]] = None
) -> Dict[str, str]:
    """
    Load prompts based on configuration type."""

    # Handle list input: list of prompt strings (text-to-image only)
    if isinstance(prompt_config, list):
        if image_files:
            raise ValueError("List of prompts not supported for image-to-image mode")
        return {f"prompt_{i}": str(prompt) for i, prompt in enumerate(prompt_config)}

    # Handle dictionary input: flexible mapping (image-to-image only)
    if isinstance(prompt_config, dict):
        if not image_files:
            raise ValueError("Dictionary prompts only supported for image-to-image mode")
        return _parse_prompt_dict(prompt_config, image_files)

    # Handle string input (filename or prompt string)
    if isinstance(prompt_config, (str, Path)):
        prompt_path = Path(prompt_config)

        # Attempt to load from file if it exists
        if prompt_path.exists():
            return load_prompts_from_file(prompt_path, image_files)

        # Fallback: treat as single prompt string
        if image_files:
            # Image-to-image: map single prompt to all images
            return {str(image_file): str(prompt_config) for image_file in image_files}
        else:
            # Text-to-image: return single prompt with generic key
            return {"prompt_0": str(prompt_config)}

    raise ValueError(f'Unsupported prompt_config type: {type(prompt_config)}')

def load_prompts_from_file(
    prompt_path: Path,
    image_files: Optional[List[Path]] = None
) -> Dict[str, str]:
    """Load prompts from a file."""
    suffix = prompt_path.suffix.lower()

    if suffix == '.txt':
        return load_text_prompts(prompt_path, image_files)
    elif suffix in ['.json', '.yaml', '.yml']:
        return load_structured_prompts(prompt_path, image_files)
    else:
        raise ValueError(f'Unsupported file extension: {suffix}')

def load_text_prompts(
    prompt_path: Path,
    image_files: Optional[List[Path]] = None
) -> Dict[str, str]:
    """Load prompts from a text file (one prompt per line)."""
    with open(prompt_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        raise ValueError(f'No valid prompts found in {prompt_path}')

    if image_files:
        # Map prompts to images
        if len(lines) == 1:
            # Single prompt for all images
            return {str(image_file): lines[0] for image_file in image_files}
        else:
            # Cycle through prompts for multiple images
            return {str(image_file): lines[i % len(lines)]
                   for i, image_file in enumerate(image_files)}
    else:
        # No images - return prompts with sequential keys
        return {f"prompt_{i}": prompt for i, prompt in enumerate(lines)}

def load_structured_prompts(
    prompt_path: Path,
    image_files: Optional[List[Path]] = None
) -> Dict[str, str]:
    """Load prompts from JSON/YAML file (image-to-image only)."""
    if not image_files:
        raise ValueError("Structured prompt files (JSON/YAML) only supported for image-to-image mode")

    with open(prompt_path, 'r', encoding='utf-8') as f:
        if prompt_path.suffix.lower() == '.json':
            prompt_data = json.load(f)
        else:
            prompt_data = yaml.safe_load(f)

    if not isinstance(prompt_data, dict):
        raise ValueError(f'Expected dict in {prompt_path}, got {type(prompt_data)}')

    return _parse_prompt_dict(prompt_data, image_files)

def _parse_prompt_dict(prompt_data: dict, image_files: List[Path]) -> Dict[str, str]:
    """Parse flexible prompt dictionary structures."""
    prompts = {}

    # create lookup sets for efficient matching.
    image_paths = {str(img) for img in image_files}
    image_names = {img.name for img in image_files}
    image_stems = {img.stem for img in image_files}

    def find_image_matches(key: str) -> List[Path]:
        """Find image files that match the given key."""
        matches = []
        for img in image_files:
            if key in [str(img), img.name, img.stem]:
                matches.append(img)
        return matches

    def is_image_reference(key: str) -> bool:
        """Check if key refers to an image file."""
        return key in image_paths or key in image_names or key in image_stems

    # process each key-value pair in the dict...
    for key, value in prompt_data.items():
        key_str = str(key)

        if is_image_reference(key_str):
            # Case 1: "image1.jpg": "prompt" or "image1.jpg": ["prompt1", "prompt2"]
            matching_images = find_image_matches(key_str)

            if isinstance(value, list):
                # multiple prompts for one image.
                for i, img in enumerate(matching_images):
                    prompt_idx = i % len(value)
                    prompts[str(img)] = str(value[prompt_idx])
            else:
                # single prompt for matching image(s).
                for img in matching_images:
                    prompts[str(img)] = str(value)
        else:
            # Case 2: "prompt": "image1.jpg" or "prompt": ["image1.jpg", "image2.jpg"]
            prompt_text = key_str

            if isinstance(value, list):
                # one prompt for multiple images.
                for img_ref in value:
                    matching_images = find_image_matches(str(img_ref))
                    for img in matching_images:
                        prompts[str(img)] = prompt_text
            else:
                # one prompt for one image.
                matching_images = find_image_matches(str(value))
                for img in matching_images:
                    prompts[str(img)] = prompt_text

    # check for missing mappings.
    missing_keys = []
    for img in image_files:
        if str(img) not in prompts:
            missing_keys.append(str(img))

    if missing_keys:
        raise ValueError(f'No prompts found for images: {missing_keys}')

    return prompts
