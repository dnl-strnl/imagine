import io

import av
import numpy as np
from PIL import Image
import pytest

from imagine.database import ImageDatabase
from imagine.frames import FrameLibrary

FPS = 24
FRAMES = 48

def make_clip(path):
    """A clip whose frame number can be read back from its brightness."""
    with av.open(str(path), 'w') as container:
        stream = container.add_stream('mpeg4', rate=FPS)
        stream.width, stream.height, stream.pix_fmt = 64, 64, 'yuv420p'
        # every frame a keyframe, so a small clip keeps its values exact enough.
        stream.gop_size = 1
        stream.bit_rate = 4_000_000
        for index in range(FRAMES):
            pixels = np.full((64, 64, 3), index * 5, dtype=np.uint8)
            for packet in stream.encode(av.VideoFrame.from_ndarray(pixels, format='rgb24')):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path

def png_bytes(color):
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), color).save(buffer, format='PNG')
    return buffer.getvalue()

@pytest.fixture
def library(tmp_path):
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    # frames name their source clips in the media table.
    ImageDatabase(tmp_path / 'test.db')
    return FrameLibrary(tmp_path / 'test.db', uploads)

def brightness(library, frame):
    return np.asarray(Image.open(library.uploads / frame['filename'])).mean()

def test_cut_takes_the_frame_on_screen(tmp_path, library):
    clip = make_clip(tmp_path / 'clip.mp4')

    first = library.cut(clip, frame='first')
    last = library.cut(clip, frame='last')
    # the middle of frame 30, as the preview sends it.
    middle = library.cut(clip, time=30.5 / FPS)

    assert (first['frame_index'], middle['frame_index'], last['frame_index']) == (0, 30, FRAMES - 1)
    assert middle['time'] == pytest.approx(30 / FPS)
    assert middle['source']['filename'] == 'clip.mp4'
    for frame in (first, middle, last):
        assert brightness(library, frame) == pytest.approx(frame['frame_index'] * 5, abs=4)

def test_cutting_the_same_frame_twice_gives_one_frame(tmp_path, library):
    clip = make_clip(tmp_path / 'clip.mp4')

    assert library.cut(clip, time=10.5 / FPS)['id'] == library.cut(clip, time=10.6 / FPS)['id']
    assert len(library.all()) == 1

def test_edits_are_versions_of_the_frame_they_came_from(tmp_path, library):
    clip = make_clip(tmp_path / 'clip.mp4')
    original = library.cut(clip, frame='last')

    edit = library.add(png_bytes('red'), '.png', parent_id=original['id'])
    # an edit of an edit stays in the original's family.
    second = library.add(png_bytes('blue'), '.png', parent_id=edit['id'])
    other = library.add(png_bytes('green'), '.png')

    assert (edit['kind'], edit['version'], second['version']) == ('edit', 2, 3)
    assert second['root_id'] == original['id'] and second['parent_id'] == edit['id']
    assert library.get(original['id'])['versions'] == 3
    assert (other['kind'], other['root_id'], other['versions']) == ('upload', other['id'], 1)

def test_add_rejects_what_is_not_an_image(library):
    with pytest.raises(ValueError):
        library.add(b'not an image', '.png')
    with pytest.raises(ValueError):
        library.add(png_bytes('red'), '.png', parent_id=99)
