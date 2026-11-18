const MEDIA_DRAG_TYPE = 'application/x-imagine-media';

// A start frame continues a clip from its last frame; an end frame leads
// into its first.
const FRAME_OF_CLIP = { first_frame: 'last', last_frame: 'first' };

const dragMedia = (event, media) => {
    event.dataTransfer.setData(MEDIA_DRAG_TYPE, JSON.stringify({
        filename: media.filename, media_type: media.media_type
    }));
    event.dataTransfer.effectAllowed = 'copy';
};

const FrameLibrary = {
    frames: [],
    listeners: new Set(),

    async refresh() {
        const response = await fetch('/frames');
        this.frames = (await response.json()).frames;
        this.listeners.forEach(listener => listener());
    },

    byFilename(filename) {
        return this.frames.find(frame => frame.filename === filename) || null;
    },

    family(frame) {
        return this.frames
            .filter(other => other.root_id === frame.root_id)
            .sort((a, b) => a.version - b.version);
    },

    latest() {
        return this.frames.filter(frame => frame.version === frame.versions);
    },

    async post(options) {
        const response = await fetch('/frames', { method: 'POST', ...options });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Could not save the frame');
        }
        await this.refresh();
        return data.frame;
    },

    // `at` is { frame: 'first' | 'last' } or { time } in seconds.
    cut(media, at = {}) {
        return this.post({
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: media.filename, ...at })
        });
    },

    upload(file, parent = null) {
        const formData = new FormData();
        formData.append('file', file);
        if (parent) formData.append('parent', parent.id);
        return this.post({ body: formData });
    }
};

const useFrameLibrary = () => {
    const [, setTick] = React.useState(0);
    React.useEffect(() => {
        const listener = () => setTick(tick => tick + 1);
        FrameLibrary.listeners.add(listener);
        return () => FrameLibrary.listeners.delete(listener);
    }, []);
    return FrameLibrary;
};

const shorten = (text, length = 48) => {
    return text && text.length > length ? text.slice(0, length - 1) + '…' : text || '';
};

const describeFrame = (frame) => {
    if (!frame) return 'Uploaded file';

    const root = FrameLibrary.family(frame)[0] || frame;
    const clip = root.source?.prompt ? `"${shorten(root.source.prompt)}"` : root.source?.filename;
    let origin = 'Uploaded file';
    if (root.kind === 'extract') {
        origin = `Frame ${root.frame_index} (${root.time.toFixed(2)} s) of ${clip}`;
    } else if (root.kind === 'image') {
        origin = `Image ${clip}`;
    }

    if (frame.kind !== 'edit') return origin;
    const parent = FrameLibrary.frames.find(other => other.id === frame.parent_id);
    return `${origin} · v${frame.version}, edited from v${parent ? parent.version : 1}`;
};

// slot: 'first_frame', 'last_frame' or 'reference'.
const sendToFrame = (slot, filename) => {
    window.dispatchEvent(new CustomEvent('imagine:set-frame', { detail: { slot, filename } }));
};
