import base64
from diffusers import DiffusionPipeline
import hydra
from hydra.utils import instantiate
import io
import litserve
import logging
from omegaconf import DictConfig, OmegaConf
from PIL import Image
import torch
from typing import Any, Dict

class API(litserve.LitAPI):
    def __init__(self):
        super().__init__()
        self.aspect_ratios = {
            "1:1": (1328, 1328),
            "16:9": (1664, 928),
            "9:16": (928, 1664),
            "4:3": (1472, 1140),
            "3:4": (1140, 1472),
            "3:2": (1584, 1056),
            "2:3": (1056, 1584),
        }

    def setup(self, device: str) -> None:
        self.device = device

        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(True)
        torch.backends.cuda.enable_math_sdp(True)

        # load image transformer model.
        self.pipe = DiffusionPipeline.from_pretrained(
            pretrained_model_name_or_path="Qwen/Qwen-Image",
            device_map="balanced",
            low_cpu_mem_usage=True,
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
        )

        # print memory footprint.
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / 1024**2
            reserved = torch.cuda.memory_reserved() / 1024**2
            print(f"VRAM: {allocated=:.1f} MB, {reserved=:.1f} MB")

    def decode_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        json_data = request if not "body" in request else request["body"]
        return json_data

    def predict(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        image = inputs.pop("image", None)
        print(inputs)

        seed = inputs.pop("seed", 0)
        generator = torch.Generator(device=self.pipe.device).manual_seed(seed)

        if "height" in inputs and "width" in inputs:
            height = inputs.pop("height")
            width = inputs.pop("width")
        else:
            aspect_ratio = inputs.pop("aspect_ratio", "1:1")
            height, width = self.aspect_ratios[aspect_ratio]

        result = self.pipe(
            image=image,
            height=height,
            width=width,
            generator=generator,
            output_type="pil",
            **inputs
        )
        image = result.images[0]

        buffer = io.BytesIO()
        processed_image.save(buffer, format="PNG")
        base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return dict(image=base64_image, seed=seed, **inputs)

@hydra.main(config_path="config", config_name="image", version_base=None)
def main(cfg: DictConfig):
    logging.info(OmegaConf.to_yaml(cfg))
    try:
        server = instantiate(cfg.server)
        server.run(host=cfg.host, port=cfg.port, num_api_servers=cfg.apis)
    except Exception as model_exception:
        logging.error(f"{model_exception=}")
        raise
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
