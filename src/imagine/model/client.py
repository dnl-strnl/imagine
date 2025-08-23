import base64
import collections
import glob
import hydra
import io
import json
import logging
import numpy as np
import requests
import threading
import time
import tqdm
import yaml
from hydra.utils import instantiate
from omegaconf import DictConfig, OmegaConf
from pathlib import Path
from PIL import Image
from rich.console import Console
from rich.progress import Progress, TimeElapsedColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table
from rich.text import Text
from typing import Any, Dict, List

from imagine.model.utils import base64_image_array, config_table, load_prompts

console = Console()
log = logging.getLogger('imagine.model.client')

class Client:
    def __init__(self, model_endpoint: str, estimate_wait:int = None):
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
                raise ValueError(f'No valid image input provided: {type(image)=}, {image_array=}, {image_path=}')
        except Exception as load_input_image_error:
            logging.error(f'{load_input_image_error=}')
            raise

    def _predict_thread(self, image_payload, image_container, error_container, timeout:int=300):
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
            error_container['error'] = f'{predict_error=}'

    def predict(self, image_path: str = None, image_array: np.ndarray = None, image: Image.Image = None, timeout=300, **kwargs):
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
            args=(image_payload, image_container, error_container)
        )
        prediction_thread.daemon = True
        prediction_thread.start()
        prediction_thread.join(timeout=timeout)

        # check for timeout.
        if prediction_thread.is_alive():
            logging.error(f'error: {timeout=} reached waiting for a response...')
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

        if not show_progress:
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

            task = progress.add_task('Imagining', total=self.estimate_wait)
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
                logging.error(f'{inference_error=}')
                return {}

            # complete progress.
            progress.update(task, completed=self.estimated_wait)
            return image_container.get('result', {})

@hydra.main(config_path='../config', config_name='client', version_base=None)
def main(cfg: DictConfig):
    console.print(config_table(cfg))
    output_dir = None

    try:
        # create the client and initialize inputs.
        client = instantiate(cfg.client)
        input_path = Path(cfg.data.image)
        image_files = []

        # handle different input types...
        if input_path.is_file():
            image_files = [input_path]
        elif input_path.is_dir():
            image_files = [f for f in input_path.iterdir()
                          if f.suffix.lower() in ['.jpeg','.jpg','.png']]
        else:
            image_files = [Path(f) for f in glob.glob(str(input_path))]

        if not image_files:
            raise ValueError(f'No images found: {input_path}')

        log.info(f'processing {len(image_files)} image(s)...')

        # Load prompts based on configuration
        prompts = load_prompts(cfg.data.prompt, image_files)

        # determine additional inference arguments from input config.
        inference_arguments = hasattr(cfg, 'inference') and cfg.inference is not None
        inference_args = dict(cfg.inference) if inference_arguments else {}

        # create output directory and save run configuration.
        output_dir = Path(cfg.output.path)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = {}
        for i, image_file in enumerate(image_files):
            try:
                input_file = str(image_file)
                image_id = image_file.stem
                input_prompt = prompts.get(input_file, None)

                console.print(f'\n[bold]Imagining 🧠✨🎨 {i+1}/{len(image_files)}: {image_file.name}[/bold]')

                if not input_prompt:
                    console.print(f'[yellow]WARNING ⚠️: No input prompt for {input_file}[/yellow]')
                    continue

                # add prompt to inference arguments.
                input_args = inference_args.copy()
                input_args['prompt'] = input_prompt

                # run inference with progress bar
                t0 = time.time()
                model_output = client.predict_verbose(
                    image_path=input_file,
                    show_progress=True,
                    **input_args
                )
                tN = time.time()
                latency = tN - t0

                if not model_output:
                    console.print(f'[yellow]WARNING ⚠️: No output returned for {input_file}[/yellow]')
                    continue

                # unpack model predictions.
                output_base64 = model_output.pop('image', None)

                if not output_base64:
                    console.print(f'[yellow]WARNING ⚠️: No image found in response.[/yellow]')
                    continue

                # generate output filename.
                output_file = output_dir / f'{image_id}_{input_prompt}.png'

                # save the output image.
                try:
                    image_data = base64.b64decode(output_base64)
                    output_image = Image.open(io.BytesIO(image_data))
                    output_image.save(output_file)
                    log.info(f'{output_file=}')
                except Exception as save_error:
                    console.print(f'[red]ERROR ⛔: {image_file.name} {save_error=}[/red]')
                    continue

                # log success
                console.print(f'[green]✓ DONE: {image_id} in {latency:.2f}s[/green]')

                # save predictions for export.
                results[input_file] = dict(
                    output_file=str(output_file),
                    latency=latency,
                    **input_args,
                )

            except Exception as image_inference_error:
                console.print(f'[red]ERROR ⛔: {image_file.name} {image_inference_error=}[/red]')
                results[input_file] = dict(
                    latency=None,
                    output_file=None,
                    prompt=prompts.get(input_file, ''),
                    error=str(image_inference_error)
                )

        log.info(f'processed {len(results)} image(s)')

        # save results to JSON file.
        output_path = output_dir / 'output.json'
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

    except Exception as client_exception:
        console.print(f'\n[red]DONE: {client_exception=}[/bold red]')
        raise
    except KeyboardInterrupt:
        console.print(f'\n[yellow]DONE: exiting early...[/bold yellow]')
    finally:
        if output_dir is not None:
            console.print(f'\n[bold green]DONE: {output_dir}[/bold green]')

if __name__ == '__main__':
    main()
