# imagine

> "*Imagination is the beginning of creation. You imagine what you desire, you will what you imagine, and at last you create what you will.*"
>     - George Bernard Shaw

<p align="center">
  <br>
  <img src="assets/image-grid.png" width="100%"/>
  </br>
</p>

### Overview

`imagine` is a simple and extensible model-agnostic web interface for text-to-image generation. It relies on an external model server to generate images, while providing a minimal and extendible interface for specifying runs and persisting returned results and metadata in a database.

### Features

- Text-to-image and image-to-image generation capabilities.
- Batch image processing support.
- Persistent image and prompt database storage with complete metadata coverage.
- RESTful API backend for plug-and-play client-side model configuration.
- Extendible inference settings panel for fine-grained control of generations.
- Seamless ablation of prompting workflows across models.

### Model Inference

This application relies on an external model server for inference. Instead of performing inference directly within the application, predictions are made by sending requests to a configured model endpoint. This approach allows the front-end to remain model-agnostic by providing a consistent interface for common parameters like the random seed, batch size, and image resolution.

### Advanced Settings

There are three main arguments used when submitting generations:

- **Prompt**: Text description that specifies the contents and style of the image.
- **Batch**: Number of different images to generate in a single run.
- **Seed**: Random seed used to ensure reproducibility across identical runs.

An additional collapsible interface can be expanded for modifying other  inference arguments:

- **Guidance Scale**: Controls how closely the generated image aligns with the input prompt(s).
- **Inference Steps**: Determines the generation quality and detail. More steps produce greater detail at the cost of inference time.
- **Image Width**: Sets the output image width in pixels.
- **Image Height**: Sets the output image height in pixels.
- **Negative Prompt**: Text description that specifies what to avoid generating in the image.

<p align="center">
  <br>
  <img src="assets/settings-panel.png" width="100%"/>
  </br>
</p>

___

### Quickstart
Install the package:
```bash
git clone https://github.com/dnl-strnl/imagine.git
cd imagine/
poetry install
```
Install the local model server dependencies:
```bash
poetry add torchserve==0.8.1 torch diffusers accelerate
```
Create a `config.properties` file with the following contents:
```bash
inference_address=http://localhost:8443
management_address=http://localhost:8444
metrics_address=http://localhost:8445
default_workers_per_model=1
max_response_size=100000000
default_response_timeout=1000
install_py_dep_per_model=true
```
The `max_response_size` should be set to a reasonable value depending on the number of images being returned and their respective resolution. Similarly, the  `default_response_timeout` should be set to a sufficently high value to ensure that large models working with high resolution images have a sufficient time to run and return a response without timing out.

Start the model server using the provided `stable-diffusion-v1-5.mar` model archive:
```bash
poetry run torchserve --start --ncs --model-store models/ --models all
```
It may be advantageous to pre-download the necessay model artfacits to `~/.cache/huggingface/hub/models--stable-diffusion-v1-5--stable-diffusion-v1-5`, if the file download becomes problematic within the TorchServe initialization process.

Start the application:
```bash
poetry run python -m imagine.app model_name=stable-diffusion-v1-5
```
Navigate to `http://127.0.0.1:5678`, enter a prompt, and click `Generate`.
