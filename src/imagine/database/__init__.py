import sqlite3
from pathlib import Path
import json

class ImageDatabase:
    def __init__(self, db_file):
        self.db_file = db_file
        self._init_db()

    def _init_db(self):
        """Initialize the database with proper schema including seed."""
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def save_image(self, image_data):
        """Save image metadata including seed to database."""
        with sqlite3.connect(self.db_file) as conn:
            conn.execute('''
                INSERT INTO images
                (filename, filepath, url, prompt, seed, source_image)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                image_data['filename'],
                image_data['filepath'],
                image_data['url'],
                image_data['prompt'],
                image_data['seed'],  # Make sure seed is included
                image_data['source_image']
            ))
            conn.commit()

    def get_all_images(self):
        """Retrieve all images with their metadata including seed."""
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
                'source_image': row['source_image']
            } for row in cursor.fetchall()]

    def verify_images(self, generated_dir):
        """Verify all images exist and clean up database if they don't."""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.execute('SELECT id, filepath FROM images')
            for row in cursor:
                if not Path(row[1]).exists():
                    conn.execute('DELETE FROM images WHERE id = ?', (row[0],))
            conn.commit()
