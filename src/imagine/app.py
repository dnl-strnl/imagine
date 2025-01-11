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
            prompt = data.get('prompt', '')
            seed = data.get('seed', 0)
            batch = min(int(data.get('batch_size', 1)), cfg.max_batch)
            image_path = data.get('image')

            if not prompt and not image_path:
                return jsonify(dict(error='No inputs provided.')), 400

            json_data = dict(prompt=prompt, seed=seed, batch=batch)

            output = requests.post(model_url, verify=cfg.model_cert, json=json_data)

            result = json.loads(output.content)
            output = json.loads(result['body'])

            image_metadata = []
            for idx, imbytes in enumerate(output['images'][:batch]):
                filestem = f'{prompt}_{seed}' + (f'_{idx}' if idx else '')
                filename = f"{secure_filename(filestem)}.png"
                filepath = app.config['GENERATED'] / filename
                url = f'/generated/{filename}'

                pil = Image.open(io.BytesIO(base64.b64decode(imbytes)))
                pil.save(filepath)

                image_data = dict(
                    filename=filename,
                    filepath=str(filepath),
                    url=url,
                    prompt=prompt,
                    seed=seed,
                    source_image=image_path
                )

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
