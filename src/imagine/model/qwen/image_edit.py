import base64
import hydra
from hydra.utils import instantiate
import io
import litserve
import logging
from omegaconf import DictConfig, OmegaConf
from PIL import Image
import torch
from transformers import BitsAndBytesConfig, Qwen2_5_VLForConditionalGeneration
from diffusers import QwenImageEditPipeline, QwenImageTransformer2DModel
from typing import Any, Dict

class API(litserve.LitAPI):
    def __init__(self):
        super().__init__()

    def setup(self, device: str) -> None:
        self.device = device

        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(True)
        torch.backends.cuda.enable_math_sdp(True)

        shared_args = dict(
            pretrained_model_name_or_path="Qwen/Qwen-Image-Edit",
            device_map="balanced",
            low_cpu_mem_usage=True,
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
        )

        quantization = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            llm_int8_skip_modules=["transformer_blocks.0.img_mod"]
        )

        # load image transformer model.
        self.transformer = QwenImageTransformer2DModel.from_pretrained(
            subfolder="transformer",
            quantization_config=quantization,
            **shared_args
        )

        # load text encoder model.
        self.text_encoder = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            subfolder="text_encoder",
            quantization_config=quantization,
            **shared_args
        )

        # wrap model components.
        self.pipe = QwenImageEditPipeline.from_pretrained(
            transformer=self.transformer,
            text_encoder=self.text_encoder,
            **shared_args
        )

        # print memory footprint.
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / 1024**2
            reserved = torch.cuda.memory_reserved() / 1024**2
            print(f"VRAM: {allocated=:.1f} MB, {reserved=:.1f} MB")

    def decode_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        json_data = request if not "body" in request else request["body"]

        image = None
        image_base64 = json_data.pop("image", None)
        if image_base64 is not None:
            image_bytes = io.BytesIO(base64.b64decode(image_base64))
            image = Image.open(image_bytes).convert("RGB")

        return dict(image=image, **json_data)

    def predict(self, inputs:Dict[str, Any]) -> Dict[str, Any]:
        image = inputs.pop('image', None)

        print(inputs)

        # set random seed or default to zero.
        seed = inputs.pop('seed', 0)
        generator = torch.Generator(device=self.pipe.device).manual_seed(seed)

        # edit the image using the model pipeline.
        image_edit = self.pipe(image=image, output_type="pil", **inputs).images[0]

        # convert image to base64.
        buffer = io.BytesIO()
        image_edit.save(buffer, format="PNG")
        base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return dict(image=base64_image, seed=seed, **inputs)

@hydra.main(config_path="config", config_name="image_edit", version_base=None)
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
