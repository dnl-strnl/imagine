import base64
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
import hydra
import io
import json
import logging as log
import numpy as np
from omegaconf import DictConfig
import os
from os.path import exists, join, splitext
from pathlib import Path
from PIL import Image
import requests
import uuid
from werkzeug.utils import secure_filename

from imagine.database import ImageDatabase

def make_app(cfg):
    model_url = f"{cfg.model_host}:{cfg.model_port}/predictions/{cfg.model_name}"
    log.info(f"{model_url}")

    app = Flask(__name__)

    app.config['DATABASE'] = ImageDatabase(cfg.db_file)
    app.config['GENERATED'] = Path(cfg.outputs) / 'generated'
    app.config['UPLOADS'] = Path(cfg.datadir) / 'uploads'

    app.config['GENERATED'].mkdir(parents=True, exist_ok=True)
    app.config['UPLOADS'].mkdir(parents=True, exist_ok=True)

    app.config['MODEL'] = cfg.model_name

    @app.route('/model-info', methods=['GET'])
    def get_model_info():
        return jsonify(dict(model=app.config['MODEL']))

    @app.route('/')
    def index():
        app.config['DATABASE'].verify_images(app.config['GENERATED'])
        images = app.config['DATABASE'].get_all_images()
        return render_template('index.html', saved_images=images)

    @app.route('/generated/<path:filename>')
    def serve_generated(filename):
        return send_from_directory(app.config['GENERATED'], filename)

    @app.route('/uploads/<path:filename>')
    def serve_upload(filename):
        return send_from_directory(app.config['UPLOADS'], filename)

    @app.route('/generate', methods=['POST'])
    def generate_batch():
        try:
            data = request.get_json()

            seed = data.get('seed', 0)
            prompt = data.get('prompt', '')
            negative_prompt = data.get('negative_prompt', '')

            image_path = data.get('image', None)
            image = None
            if image_path:
                source_image = Path(app.config['UPLOADS'] / image_path)
                if source_image.exists():
                    img = Image.open(source_image)
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG")
                    image = base64.b64encode(buffer.getvalue()).decode('utf-8')

            batch = min(int(data.get('batch_size', 1)), cfg.max_batch)
            verify = cfg.model_cert

            num_inference_steps = data.get('num_inference_steps', cfg.num_inference_steps)
            guidance_scale = data.get('guidance_scale', cfg.guidance_scale)

            if not prompt and not image_path:
                return jsonify(dict(error='No inputs provided.')), 400

            base_args = dict(seed=seed, batch=batch)
            pipe_args = dict(
                prompt=prompt,
                image=image,
                negative_prompt=negative_prompt,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
            )

            json_data = dict(**base_args, **pipe_args)
            log.info(json_data)

            output = requests.post(model_url, verify=verify, json=json_data)

            result = json.loads(output.content)
            output = json.loads(result['body'])

            image_metadata = []
            for idx, imbytes in enumerate(output['images'][:batch]):

                extras = f'{str(guidance_scale).zfill(4)}_{str(num_inference_steps).zfill(3)}'
                filestem = f'{prompt}_{seed}_{extras}' + (f'_{idx}' if idx else '')
                filename = f"{secure_filename(filestem)}.png"
                filepath = app.config['GENERATED'] / filename
                url = f'/generated/{filename}'
                file_data = dict(
                    filename=filename,
                    filepath=str(filepath),
                    source_image=image_path,
                    url=url,
                )
                pil = Image.open(io.BytesIO(base64.b64decode(imbytes)))
                pil.save(filepath)

                image_data = dict(**file_data, **json_data)

                app.config['DATABASE'].save_image(image_data)
                image_metadata.append(image_data)

            return jsonify(dict(success=True, images=image_metadata))
        except Exception as image_generation_exception:
            log.error(error := f"{image_generation_exception=}")
            return jsonify(dict(error=error)), 500

    @app.route('/upload', methods=['POST'])
    def upload_file():
        if 'file' not in request.files:
            return jsonify(dict(error='No file part.')), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify(dict(error='No selected file.')), 400

        if file:
            unique_id  = str(uuid.uuid4()) + splitext(file.filename)[1]
            filename = secure_filename(unique_id)
            filepath = join(app.config['UPLOADS'], filename)
            file.save(filepath)
            return jsonify(dict(filename=filename, success=True))

    return app

@hydra.main(version_base=None, config_path="config", config_name="app")
def main(cfg: DictConfig):
    app = make_app(cfg)
    app.run(host=cfg.app_host, port=cfg.app_port, debug=cfg.debug)

if __name__ == '__main__':
    main()
