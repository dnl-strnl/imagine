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

from imagine import sweep
from imagine.database import ImageDatabase
from imagine.estimate import Estimator
from imagine.frames import FrameLibrary
from imagine.jobs import JobQueue

def make_app(cfg):
    app = Flask(__name__)

    app.config['DATABASE'] = ImageDatabase(cfg.db_file)
    app.config['GENERATED'] = Path(cfg.outputs) / 'generated'
    app.config['UPLOADS'] = Path(cfg.datadir) / 'uploads'
    app.config['GENERATED'].mkdir(parents=True, exist_ok=True)
    app.config['UPLOADS'].mkdir(parents=True, exist_ok=True)
    app.config['MODEL'] = default_model = f'{cfg.model_host}:{cfg.model_port}/predict'

    max_steps = cfg.num_inference_steps
    default_image_width = cfg.default_image_width
    default_image_height = cfg.default_image_height

    video_host = cfg.video_host or cfg.model_host
    video_models = dict(
        fl2va=f'{video_host}:{cfg.video_fl2va_port}/predict' if video_host else None,
        ref2va=f'{video_host}:{cfg.video_ref2va_port}/predict' if video_host else None,
    )

    @app.route('/model-info', methods=['GET'])
    def get_model_info():
        return jsonify(dict(
            model=app.config['MODEL'],
            video=video_models,
            video_limits=dict(
                min_duration=sweep.MIN_DURATION,
                max_duration=sweep.MAX_DURATION,
                references=sweep.REFERENCE_LIMITS,
                max_references=sweep.MAX_REFERENCES,
            ),
        ))

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
                seed=int(data.get('seed', 0)),
                prompt=prompt,
                style=data.get('style', ''),
                negative_prompt=data.get('negative_prompt', ''),
                width=int(data.get('width', default_image_width)),
                height=int(data.get('height', default_image_height)),
                num_inference_steps=int(data.get('num_inference_steps', max_steps)),
                batch=min(int(data.get('batch_size', 1)), cfg.max_batch),
                guidance_scale=float(data.get('guidance_scale', cfg.guidance_scale)),
            )

            image = None
            if image_path:
                source_image = Path(app.config['UPLOADS'] / image_path)
                if source_image.exists():
                    img = Image.open(source_image)
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG')
                    image = base64.b64encode(buffer.getvalue()).decode('utf-8')

            api_payload = dict(image=image, **payload)

            db_payload = dict(
                model=app.config['MODEL'], source_image=image_path, **payload
            )

            output = requests.post(
                app.config['MODEL'], json=api_payload, verify=cfg.model_cert
            )

            result = json.loads(output.content)

            if 'images' in result:
                image_list = result['images']
            elif 'image' in result:
                image_list = [result['image']]
            else:
                return jsonify(dict(error='No image data in response.')), 500

            image_metadata = []
            for idx, image_bytes in enumerate(image_list):
                filestem = db_payload['prompt'] + f'_{str(uuid.uuid4())[:8]}'
                filename = f'{secure_filename(filestem)}.png'
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
            log.error(error := f'{image_generation_exception=}')
            return jsonify(dict(error=error)), 500

    def encode_upload(filename):
        upload = app.config['UPLOADS'] / secure_filename(filename)
        if not upload.exists():
            raise FileNotFoundError(f'missing upload: {filename}')
        return base64.b64encode(upload.read_bytes()).decode('utf-8')

    def run_video_job(job):
        api_payload = dict(
            workflow=job['workflow'],
            prompt=job['prompt'],
            style=job.get('style', ''),
            seed=job['seed'],
            width=job['width'],
            height=job['height'],
            num_frames=job['num_frames'],
            fps=job['fps'],
            num_inference_steps=job['num_inference_steps'],
            first_frame=encode_upload(job['first_frame']) if job.get('first_frame') else None,
            last_frame=encode_upload(job['last_frame']) if job.get('last_frame') else None,
            references=[
                dict(type=r['type'], filename=r['filename'], data=encode_upload(r['filename']))
                for r in job.get('references', [])
            ],
        )

        started = datetime.now()
        output = requests.post(job['model'], json=api_payload, verify=cfg.model_cert)
        result = json.loads(output.content)
        if 'video' not in result:
            raise RuntimeError(result.get('detail') or result.get('error') or 'No video data in response.')

        filestem = job['prompt'][:80] + f'_{str(uuid.uuid4())[:8]}'
        filename = f'{secure_filename(filestem)}.mp4'
        filepath = app.config['GENERATED'] / filename
        filepath.write_bytes(base64.b64decode(result['video']))

        video_data = dict(
            filename=filename,
            filepath=str(filepath),
            url=f'/generated/{filename}',
            media_type='video',
            elapsed=(datetime.now() - started).total_seconds(),
            **{k: job.get(k) for k in (
                'prompt', 'style', 'seed', 'model', 'width', 'height', 'num_frames', 'fps',
                'duration', 'num_inference_steps', 'sweep_id', 'first_frame', 'last_frame',
                'references',
            )}
        )
        app.config['DATABASE'].save_image(video_data)
        return video_data

    estimator = Estimator(cfg.db_file)
    app.config['QUEUE'] = JobQueue(cfg.db_file, run_video_job, estimator)

    def expand_sweep(spec):
        spec['workflow'] = spec.get('workflow') or 'fl2va'
        spec['model'] = spec.get('model') or video_models.get(spec['workflow'])
        if not spec['model']:
            raise ValueError('No video model configured: set video_host or model_host.')
        return sweep.expand(spec)

    @app.route('/sweeps/preview', methods=['POST'])
    def preview_sweep():
        try:
            spec = request.get_json()
            jobs = expand_sweep(spec)
            estimate = estimator.estimate(
                sweep.configurations(jobs), spec['model'], spec['workflow']
            )
            return jsonify(dict(success=True, model=spec['model'], **estimate))
        except (ValueError, KeyError, TypeError) as sweep_exception:
            return jsonify(dict(error=str(sweep_exception))), 400

    @app.route('/sweeps', methods=['POST'])
    def submit_sweep():
        try:
            spec = request.get_json()
            jobs = expand_sweep(spec)
        except (ValueError, KeyError, TypeError) as sweep_exception:
            return jsonify(dict(error=str(sweep_exception))), 400

        name = spec.get('name') or jobs[0]['prompt'][:60]
        sweep_id = app.config['QUEUE'].submit(name, spec, jobs)
        return jsonify(dict(success=True, sweep_id=sweep_id, clips=len(jobs)))

    @app.route('/sweeps', methods=['GET'])
    def list_sweeps():
        return jsonify(dict(sweeps=app.config['QUEUE'].sweeps()))

    @app.route('/sweeps/<int:sweep_id>', methods=['GET'])
    def get_sweep(sweep_id):
        summary = app.config['QUEUE'].sweep(sweep_id)
        if summary is None:
            return jsonify(dict(error='No such sweep.')), 404
        return jsonify(summary)

    @app.route('/sweeps/<int:sweep_id>/cancel', methods=['POST'])
    def cancel_sweep(sweep_id):
        cancelled = app.config['QUEUE'].cancel(sweep_id)
        return jsonify(dict(success=True, cancelled=cancelled))

    @app.route('/media', methods=['GET'])
    def new_media():
        after = request.args.get('after', 0, type=int)
        return jsonify(dict(media=app.config['DATABASE'].get_all_images(after_id=after)))

    frames = FrameLibrary(cfg.db_file, app.config['UPLOADS'])

    @app.route('/frames', methods=['GET'])
    def list_frames():
        return jsonify(dict(frames=frames.all()))

    @app.route('/frames', methods=['POST'])
    def add_frame():
        try:
            if 'file' in request.files:
                file = request.files['file']
                frame = frames.add(
                    file.read(), splitext(file.filename)[1],
                    parent_id=request.form.get('parent', type=int),
                )
            else:
                data = request.get_json()
                source = app.config['GENERATED'] / secure_filename(data.get('filename') or '')
                if not source.is_file():
                    return jsonify(dict(error='No such generated file.')), 404
                frame = frames.cut(source, frame=data.get('frame'), time=data.get('time'))
            return jsonify(dict(success=True, frame=frame))
        except ValueError as frame_exception:
            return jsonify(dict(error=str(frame_exception))), 400
        except Exception as frame_exception:
            log.error(error := f'{frame_exception=}')
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

@hydra.main(version_base=None, config_path='config', config_name='app')
def main(cfg: DictConfig):
    app = make_app(cfg)
    # under the debug reloader, only the serving process runs the queue.
    if not cfg.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        app.config['QUEUE'].start()
    app.run(host=cfg.app_host, port=cfg.app_port, debug=cfg.debug)

if __name__ == '__main__':
    main()
