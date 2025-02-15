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
    app = Flask(__name__)

    app.config['DATABASE'] = ImageDatabase(cfg.db_file)
    app.config['GENERATED'] = Path(cfg.outputs) / 'generated'
    app.config['UPLOADS'] = Path(cfg.datadir) / 'uploads'
    app.config['GENERATED'].mkdir(parents=True, exist_ok=True)
    app.config['UPLOADS'].mkdir(parents=True, exist_ok=True)
    app.config['MODEL'] = default_model = cfg.model_name

    max_steps = cfg.num_inference_steps
    default_image_width = cfg.default_image_width
    default_image_height = cfg.default_image_height

    model_url = lambda model_name: \
        f"{cfg.model_host}:{cfg.model_port}/predictions/{model_name}"

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

            prompt = data.get('prompt', '')
            image_path = data.get('image', None)

            if not prompt and not image_path:
                return jsonify(dict(error='No inputs provided.')), 400

            app.config['MODEL'] = data.get('model', default_model)

            payload = dict(
                prompt=prompt,
                seed=int(data.get('seed', 0)),
                batch=min(int(data.get('batch_size', 1)), cfg.max_batch),
                negative_prompt=data.get('negative_prompt', ''),
                width=int(data.get('width', default_image_width)),
                height=int(data.get('height', default_image_height)),
                guidance_scale=float(data.get('guidance_scale', cfg.guidance_scale)),
                num_inference_steps=int(data.get('num_inference_steps', max_steps)),
            )

            image = None
            if image_path:
                source_image = Path(app.config['UPLOADS'] / image_path)
                if source_image.exists():
                    img = Image.open(source_image)
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG")
                    image = base64.b64encode(buffer.getvalue()).decode('utf-8')

            api_payload = dict(image=image, **payload)

            db_payload = dict(
                model=app.config['MODEL'], source_image=image_path, **payload
            )

            url = model_url(model := app.config['MODEL'])
            output = requests.post(url, json=api_payload, verify=cfg.model_cert)
            result = json.loads(output.content)
            output = json.loads(result['body'])

            image_metadata = []
            for idx, image_bytes in enumerate(output['images']):
                filestem = db_payload['prompt'] + f'_{str(uuid.uuid4())[:8]}'
                filename = f"{secure_filename(filestem)}.png"
                filepath = str(app.config['GENERATED'] / filename)
                url = f'/generated/{filename}'

                image_data = {
                    'filename': filename,
                    'filepath': filepath,
                    'url': url,
                    'settings': db_payload,
                    **db_payload
                }
                image_metadata.append(image_data)

                image = Image.open(io.BytesIO(base64.b64decode(image_bytes)))
                image.save(filepath)

                app.config['DATABASE'].save_image(image_data)

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
            file.save(join(app.config['UPLOADS'], filename))
            return jsonify(dict(filename=filename, success=True))

    return app

@hydra.main(version_base=None, config_path="config", config_name="app")
def main(cfg: DictConfig):
    app = make_app(cfg)
    app.run(host=cfg.app_host, port=cfg.app_port, debug=cfg.debug)

if __name__ == '__main__':
    main()
