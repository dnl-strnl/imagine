import base64
from diffusers import ModularPipeline
from diffusers.utils.export_utils import encode_video
import hydra
from hydra.utils import instantiate
import io
import litserve
import logging
from omegaconf import DictConfig, OmegaConf
from pathlib import Path
from PIL import Image
import tempfile
import time
import torch
from typing import Any, Dict

from imagine.sweep import snap_dimension, snap_num_frames

FPS = 24

class API(litserve.LitAPI):
    """MiniMax-H3 video with audio, int8 for a 24-32 GB card.

    One workflow per server, since each has its own transformer: `fl2va`
    (text, start frame, end frame) or `ref2va` (references named in the
    prompt as <Picture 1>, <Video 1>, <Audio 1>).
    """

    def __init__(self, model: str = "MiniMaxAI/MiniMax-H3", workflow: str = "fl2va"):
        super().__init__()
        if workflow not in ("fl2va", "ref2va"):
            raise ValueError(f"unknown workflow: {workflow!r}")
        self.model = model
        self.workflow = workflow

    def setup(self, device: str) -> None:
        self.device = device
        reference = self.workflow == "ref2va"
        # fixing ref2va keeps the other transformer from loading; fl2va stays
        # unfixed so text-only requests route per call.
        fixed = dict(workflow="ref2va") if reference else {}
        load = {} if reference else dict(workflow="fl2va")
        component = "transformer_ref" if reference else "transformer"

        self.pipe = ModularPipeline.from_pretrained(self.model, **fixed)
        self.pipe.update_components(**self._int8_components(component))
        self.pipe.load_components(dtype=torch.bfloat16, **load)

        transformer = getattr(self.pipe, component)
        transformer.requires_grad_(False)
        self.pipe.text_encoder.requires_grad_(False)

        # ~75 GB of int8 weights stay in host RAM and stream through the card.
        from diffusers.hooks import apply_group_offloading
        offload = dict(
            onload_device=torch.device(device),
            offload_device=torch.device("cpu"),
            use_stream=True,
        )
        transformer.enable_group_offload(
            offload_type="block_level", num_blocks_per_group=1, **offload
        )
        apply_group_offloading(
            self.pipe.text_encoder.model, offload_type="leaf_level", **offload
        )
        self.pipe.vae.to(device)
        self.pipe.audio_vae.to(device)

    def _int8_components(self, component: str) -> Dict[str, Any]:
        from diffusers import MiniMaxH3Transformer3DModel, TorchAoConfig
        from torchao.quantization import Int8WeightOnlyConfig
        from transformers import Qwen3VLForConditionalGeneration
        from transformers import TorchAoConfig as TransformersTorchAoConfig

        # the diffusers recipe for this model on a 24-32 GB card.
        return {
            component: MiniMaxH3Transformer3DModel.from_pretrained(
                self.model,
                subfolder=component,
                dtype=torch.bfloat16,
                quantization_config=TorchAoConfig(
                    Int8WeightOnlyConfig(version=2),
                    modules_to_not_convert=[
                        "proj_in", "audio_proj_in", "context_embedder", "time_embedder",
                        "time_proj", "token_refiner", "norm_out", "proj_out", "audio_proj_out",
                    ],
                ),
                low_cpu_mem_usage=False,
            ),
            "text_encoder": Qwen3VLForConditionalGeneration.from_pretrained(
                self.model,
                subfolder="text_encoder",
                dtype=torch.bfloat16,
                quantization_config=TransformersTorchAoConfig(
                    Int8WeightOnlyConfig(version=2),
                    modules_to_not_convert=[
                        "model.visual", "model.language_model.embed_tokens",
                        "model.language_model.norm", "lm_head",
                    ],
                ),
            ),
        }

    def decode_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        json_data = request if not "body" in request else request["body"]
        return json_data

    def _image(self, data: str) -> Image.Image:
        return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")

    def _references(self, references: list, folder: Path) -> list:
        from diffusers.modular_pipelines.minimax_h3 import (
            MiniMaxH3AudioReference,
            MiniMaxH3ImageReference,
            MiniMaxH3VideoReference,
        )

        loaded = []
        for index, reference in enumerate(references):
            if reference["type"] == "image":
                loaded.append(MiniMaxH3ImageReference(image=self._image(reference["data"])))
                continue
            # video and audio load from a file to keep frame and sample rates.
            suffix = Path(reference.get("filename") or "").suffix
            media = folder / f"reference_{index}{suffix}"
            media.write_bytes(base64.b64decode(reference["data"]))
            kind = MiniMaxH3VideoReference if reference["type"] == "video" else MiniMaxH3AudioReference
            loaded.append(kind.from_file(str(media)))
        return loaded

    def predict(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        seed = int(inputs.get("seed", 0) or 0)
        style = (inputs.get("style", "") or "").strip(" ,")
        subject = (inputs.get("prompt", "") or "").strip(" ,")
        prompt = ", ".join(p for p in (style, subject) if p)

        width = snap_dimension(inputs.get("width", 1344))
        height = snap_dimension(inputs.get("height", 768))
        num_frames = snap_num_frames(inputs.get("num_frames", 124), FPS)
        steps = int(inputs.get("num_inference_steps", 50))

        first, last = inputs.get("first_frame"), inputs.get("last_frame")
        references = inputs.get("references") or []
        if self.workflow == "ref2va" and not references:
            raise ValueError("this server runs ref2va and needs references.")
        if self.workflow == "fl2va" and references:
            raise ValueError("this server runs fl2va; send references to the ref2va server.")

        logging.info(
            f"{prompt=} {seed=} {width=} {height=} {num_frames=} {steps=} "
            f"first={bool(first)} last={bool(last)} references={len(references)}"
        )

        with tempfile.TemporaryDirectory() as folder:
            conditions = {}
            if references:
                conditions["references"] = self._references(references, Path(folder))
            if first:
                conditions["image"] = self._image(first)
            if last:
                conditions["last_image"] = self._image(last)

            results = self.pipe(
                prompt=prompt,
                width=width,
                height=height,
                num_frames=num_frames,
                num_inference_steps=steps,
                generator=torch.Generator().manual_seed(seed),
                output=["videos", "audio", "sampling_rate"],
                **conditions,
            )

            output = Path(folder) / "output.mp4"
            encode_video(
                results["videos"][0],
                fps=FPS,
                output_path=str(output),
                audio=results["audio"][0],
                audio_sample_rate=results["sampling_rate"],
            )
            video = base64.b64encode(output.read_bytes()).decode("utf-8")

        return dict(
            video=video, seed=seed, prompt=prompt, width=width, height=height,
            num_frames=num_frames, fps=FPS, elapsed=time.time() - started,
        )

@hydra.main(config_path="config", config_name="h3", version_base=None)
def main(cfg: DictConfig):
    logging.info(OmegaConf.to_yaml(cfg))
    try:
        server = instantiate(cfg.server)
        server.run(
            host=cfg.host, port=cfg.port, num_api_servers=cfg.apis,
            generate_client_file=False,
        )
    except Exception as model_exception:
        logging.error(f"{model_exception=}")
        raise
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
