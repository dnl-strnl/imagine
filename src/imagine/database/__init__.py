import sqlite3
from pathlib import Path
import json

class ImageDatabase:
    def __init__(self, db_file):
        self.db_file = db_file
        self._init_db()

    def _init_db(self):
        """Initialize the database with proper schema."""

        # create the database file parent directory.
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_file) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    url TEXT NOT NULL,
                    prompt TEXT,
                    seed INTEGER,
                    source_image TEXT,
                    model TEXT,
                    guidance_scale REAL,
                    num_inference_steps INTEGER,
                    negative_prompt TEXT,
                    width INTEGER,
                    height INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def save_image(self, image_data):
        """Save image metadata to database."""
        with sqlite3.connect(self.db_file) as conn:
            conn.execute('''
                INSERT INTO images (
                    filename, filepath, url, prompt, seed, source_image,
                    model, guidance_scale, num_inference_steps, negative_prompt,
                    width, height
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                image_data['filename'],
                image_data['filepath'],
                image_data['url'],
                image_data['prompt'],
                image_data['seed'],
                image_data.get('source_image'),
                image_data.get('model'),
                image_data.get('guidance_scale'),
                image_data.get('num_inference_steps'),
                image_data.get('negative_prompt'),
                image_data.get('width'),
                image_data.get('height')
            ))
            conn.commit()

    def get_all_images(self):
        """Retrieve all images with their metadata."""
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM images
                ORDER BY created_at DESC
            ''')
            return [{
                'filename': row['filename'],
                'filepath': row['filepath'],
                'url': row['url'],
                'prompt': row['prompt'],
                'seed': row['seed'],
                'source_image': row['source_image'],
                'model': row['model'],
                'width': row['width'],
                'height': row['height'],
                'settings': {
                    'guidanceScale': row['guidance_scale'],
                    'num_inference_steps': row['num_inference_steps'],
                    'negativePrompt': row['negative_prompt'],
                    'width': row['width'],
                    'height': row['height']
                }
            } for row in cursor.fetchall()]

    def verify_images(self, generated_dir):
        """Verify all images exist and clean database."""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.execute('SELECT id, filepath FROM images')
            for row in cursor:
                if not Path(row[1]).exists():
                    conn.execute('DELETE FROM images WHERE id = ?', (row[0],))
            conn.commit()
