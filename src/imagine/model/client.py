from pathlib import Path

import base64
import glob

import hydra
from hydra.utils import instantiate
import io
import json
import logging

import numpy as np
from omegaconf import DictConfig
from PIL import Image
import requests
from rich.console import Console
from rich.progress import (
     Progress, BarColumn, TextColumn, TimeElapsedColumn,TimeRemainingColumn
)
import threading
import time
from typing import Dict


from imagine.model.utils import base64_image_array, config_table, load_prompts

console = Console()
log = logging.getLogger('imagine.model.client')

class Client:
    def __init__(self, model_endpoint: str, estimated_wait: int = None):
        self.model_endpoint = model_endpoint
        self.estimated_wait = estimated_wait

    def _load_image_data(self, image_path: str = None, image_array: np.ndarray = None, image: Image.Image = None):
        """Load and encode image data as base64 string from various input types."""
        try:
            if image is not None:
                return base64_image_array(image)
            elif image_array is not None:
                return base64_image_array(image_array)
            elif image_path is not None:
                with open(image_path, 'rb') as f:
                    return base64.b64encode(f.read()).decode('utf-8')
            else:
                raise ValueError(f'No valid image input provided: image={type(image)}, image_array={image_array is not None}, image_path={image_path}')
        except Exception as load_input_image_error:
            logging.error(f'load_input_image_error={load_input_image_error}')
            raise

    def _predict_thread(self, image_payload: Dict, image_container: Dict, error_container: Dict, timeout: int = 300):
        """Thread function to make the prediction request."""
        try:
            response = requests.post(
                self.model_endpoint,
                json=image_payload,
                timeout=timeout,
                headers={'Content-Type': 'application/json'},
            )
            response.raise_for_status()
            response_data = response.json()
            image_container['image'] = response_data.get('body', response_data)
        except Exception as predict_error:
            error_container['error'] = f'predict_error={predict_error}'

    def predict(self, image_path: str = None, image_array: np.ndarray = None, image: Image.Image = None, timeout: int = 300, **kwargs):
        try:
            base64_input = self._load_image_data(image_path, image_array, image)
            image_payload = dict(image=base64_input, **kwargs)
        except Exception:
            return {}

        # create and run the prediction thread.
        image_container = {}
        error_container = {}
        prediction_thread = threading.Thread(
            target=self._predict_thread,
            args=(image_payload, image_container, error_container, timeout)
        )
        prediction_thread.daemon = True
        prediction_thread.start()
        prediction_thread.join(timeout=timeout)

        # check for timeout.
        if prediction_thread.is_alive():
            logging.error(f'error: timeout={timeout} reached waiting for a response...')
            return {}

        # check for errors.
        if 'error' in error_container:
            logging.error(error_container['error'])
            return {}

        return image_container.get('image', {})

    def predict_verbose(
        self,
        image_path: str = None,
        image_array: np.ndarray = None,
        image: Image.Image = None,
        show_progress: bool = True,
        **kwargs
    ):
        """Predict with a progress bar based on expected wait time."""
        if not show_progress or self.estimated_wait is None:
            return self.predict(image_path, image_array, image, **kwargs)

        try:
            base64_input = self._load_image_data(image_path, image_array, image)
            image_payload = dict(image=base64_input, **kwargs)
        except Exception:
            return {}

        # start the prediction in a separate thread.
        image_container = {}
        error_container = {}
        prediction_thread = threading.Thread(
            target=self._predict_thread,
            args=(image_payload, image_container, error_container)
        )
        prediction_thread.daemon = True
        prediction_thread.start()

        # create progress bar.
        with Progress(
            TextColumn('[bold blue]Imagining... 🧠✨🎨'),
            BarColumn(),
            TextColumn('[bold green][progress.percentage]{task.percentage:>3.0f}%'),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:

            task = progress.add_task('Imagining', total=self.estimated_wait)
            start_time = time.time()

            # update progress while the thread is running...
            while prediction_thread.is_alive():
                elapsed = time.time() - start_time
                # cap progress at 99% until we know the request is complete.
                progress_percent = min(elapsed / self.estimated_wait, 0.99)
                progress.update(task, completed=progress_percent * self.estimated_wait)
                time.sleep(0.1)  # small delay to avoid busy waiting

            # check if thread completed successfully.
            if 'error' in error_container:
                inference_error = error_container['error']
                progress.update(task, completed=self.estimated_wait)
                logging.error(f'inference_error={inference_error}')
                return {}

            # complete progress.
            progress.update(task, completed=self.estimated_wait)
            return image_container.get('image', {})

def process_request(
    client: Client,
    item_id: str,
    prompt_text: str,
    input_file: str = None,
    inference_args: Dict = None,
    output_dir: Path = None
) -> Dict:
    """Process a single inference request."""
    inference_args = inference_args or {}

    # add prompt to inference arguments.
    input_args = inference_args.copy()
    input_args['prompt'] = prompt_text

    # run inference with progress bar.
    t0 = time.time()
    if input_file:
        model_output = client.predict_verbose(
            image_path=input_file,
            show_progress=True,
            **input_args
        )
    else:
        model_output = client.predict_verbose(
            show_progress=True,
            **input_args
        )
    tN = time.time()
    latency = tN - t0

    if not model_output:
        return {
            'success': False,
            'error': 'No response from model server.',
            'latency': latency,
            'prompt': prompt_text
        }

    # unpack model predictions.
    output_base64 = model_output.pop('image', None)
    if not output_base64:
        return {
            'success': False,
            'error': 'No image found in model server response.',
            'latency': latency,
            'prompt': prompt_text
        }

    # generate output filename.
    safe_prompt = "".join(
        c for c in prompt_text if c.isalnum() or c in (' ', '-', '_')
    ).rstrip()
    safe_prompt = safe_prompt.replace(' ', '_')[:50]  # limit length
    filename = output_dir / f'{item_id}_{safe_prompt}.png'

    # save the output image.
    try:
        image_data = base64.b64decode(output_base64)
        output_image = Image.open(io.BytesIO(image_data))
        output_image.save(filename)
        log.info(f'filename={filename}')
    except Exception as save_error:
        return {
            'success': False,
            'error': f'save_error={save_error}',
            'latency': latency,
            'prompt': prompt_text
        }

    return {
        'success': True,
        'filename': str(filename),
        'latency': latency,
        'prompt': prompt_text,
        **input_args,
    }

@hydra.main(config_path='../config', config_name='client', version_base=None)
def main(cfg: DictConfig):
    console.print(config_table(cfg))
    output_dir = None

    try:
        # create the inference client.
        client = instantiate(cfg.client)

        # handle image inputs, if provided.
        image_files = []
        if hasattr(cfg.data, 'image') and cfg.data.image:
            input_path = Path(cfg.data.image)
            image_exts = ['.jpeg', '.jpg', '.png']

            # handle different input types...
            if input_path.is_file():
                image_files = [input_path]
            elif input_path.is_dir():
                image_files = [f for f in input_path.iterdir() if f.suffix.lower() in image_exts]
            else:
                image_files = [Path(f) for f in glob.glob(str(input_path))]

        # load text prompts.
        prompts = load_prompts(cfg.data.prompt, image_files if image_files else None)
        prompt_only = len(image_files) == 0

        # determine additional inference arguments from input config.
        inference_arguments = hasattr(cfg, 'inference') and cfg.inference is not None
        inference_args = dict(cfg.inference) if inference_arguments else {}

        # create output directory and save run configuration.
        output_dir = Path(cfg.output.path)
        output_dir.mkdir(parents=True, exist_ok=True)

        # iterate over prompts or images depending on input data.
        items = list(prompts.items()) if prompt_only else \
            [(str(f), prompts.get(str(f), '')) for f in image_files]

        results = {}
        for i, (item_key, prompt_text) in enumerate(items):
            try:
                if prompt_only:
                    display_name = item_key
                    item_id = item_key
                    input_file = None
                else:
                    image_file = Path(item_key)
                    display_name = image_file.name
                    item_id = image_file.stem
                    input_file = item_key

                    if not prompt_text:
                        console.print(f'[yellow]WARNING  ⚠️: No input prompt for {input_file}[/yellow]')
                        results[item_key] = {
                            'latency': None,
                            'filename': None,
                            'prompt': '',
                            'error': 'No input prompt.'
                        }
                        continue

                console.print(f'\n[bold]{i+1}/{len(items)}: {display_name}[/bold]')
                console.print(f'[blue]prompt: {prompt_text}[/blue]')

                result = process_request(
                    client=client,
                    item_id=item_id,
                    prompt_text=prompt_text,
                    input_file=input_file,
                    inference_args=inference_args,
                    output_dir=output_dir
                )

                if result['success']:
                    console.print(f'[green]✓ DONE: {item_id} in {result["latency"]:.2f}s[/green]')
                    result.pop('success')
                    results[item_key] = result
                else:
                    console.print(f'[yellow]WARNING  ⚠️: {result["error"]}[/yellow]')
                    result.pop('success')
                    result.update({
                        'latency': result.get('latency'),
                        'filename': None,
                    })
                    results[item_key] = result

            except Exception as processing_error:
                error_msg = str(processing_error)
                console.print(f'[red]ERROR ⛔: {display_name} {error_msg}[/red]')
                results[item_key] = {
                    'latency': None,
                    'filename': None,
                    'prompt': prompt_text,
                    'error': error_msg
                }

        log.info(f'processed {len(results)} item(s)')

        # save results to JSON file.
        output_path = output_dir / 'output.json'
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

    except Exception as client_exception:
        console.print(f'\n[bold red]DONE: client_exception={client_exception}[/bold red]')
        raise
    except KeyboardInterrupt:
        console.print(f'\n[bold yellow]DONE: exiting early...[/bold yellow]')
    finally:
        if output_dir is not None:
            console.print(f'\n[bold green]DONE: {output_dir}[/bold green]')

if __name__ == '__main__':
    main()
