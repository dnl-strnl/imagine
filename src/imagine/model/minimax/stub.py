import base64
import hydra
from hydra.utils import instantiate
import litserve
import logging
from omegaconf import DictConfig, OmegaConf
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict

from imagine.sweep import snap_dimension, snap_num_frames

class API(litserve.LitAPI):
    """Stand-in for the H3 server: same contract, no model. Waits in proportion
    to the work and returns a test pattern, or clips from a folder."""

    def __init__(self, rate: float = 0.002, overhead: float = 1.0, clips: str = None):
        super().__init__()
        self.rate = rate
        self.overhead = overhead
        self.clips = clips

    def setup(self, device: str) -> None:
        self.served = 0
        if self.clips:
            self.files = sorted(Path(self.clips).expanduser().glob("*.mp4"))
            if not self.files:
                raise RuntimeError(f"no mp4 files in {self.clips}.")
            return
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("the stub video server needs ffmpeg on the PATH.")

    def decode_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        json_data = request if not "body" in request else request["body"]
        return json_data

    def predict(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        seed = int(inputs.get("seed", 0) or 0)
        fps = int(inputs.get("fps", 24))
        width = snap_dimension(inputs.get("width", 1344))
        height = snap_dimension(inputs.get("height", 768))
        num_frames = snap_num_frames(inputs.get("num_frames", 124), fps)
        steps = int(inputs.get("num_inference_steps", 50))
        logging.info(f"{inputs.get('prompt')=} {seed=} {width=} {height=} {num_frames=} {steps=}")

        megapixels = width * height / 1e6
        time.sleep(self.overhead + self.rate * max(1, steps - 1) * megapixels * num_frames / 4)

        if self.clips:
            clip = self.files[self.served % len(self.files)]
            self.served += 1
            video = base64.b64encode(clip.read_bytes()).decode("utf-8")
            return dict(
                video=video, seed=seed, prompt=inputs.get("prompt"), width=width, height=height,
                num_frames=num_frames, fps=fps, elapsed=time.time() - started,
            )

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "stub.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-y",
                "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate={fps}",
                "-f", "lavfi", "-i", f"sine=frequency={220 + seed % 12 * 40}:sample_rate=32000",
                "-frames:v", str(num_frames), "-t", str(num_frames / fps),
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ac", "2", "-movflags", "+faststart",
                str(output),
            ], check=True)
            video = base64.b64encode(output.read_bytes()).decode("utf-8")

        return dict(
            video=video, seed=seed, prompt=inputs.get("prompt"), width=width, height=height,
            num_frames=num_frames, fps=fps, elapsed=time.time() - started,
        )

@hydra.main(config_path="config", config_name="stub", version_base=None)
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
