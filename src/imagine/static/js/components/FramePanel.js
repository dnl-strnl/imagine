const FramePanel = ({ media, videoRef, onSent }) => {
    const library = useFrameLibrary();
    const isVideo = media.media_type === 'video';
    const fps = media.fps || 24;
    const [time, setTime] = React.useState(0);
    const [lastIndex, setLastIndex] = React.useState(0);
    const [sending, setSending] = React.useState(false);

    React.useEffect(() => {
        const video = videoRef.current;
        if (!isVideo || !video) return;

        const update = () => {
            setTime(video.currentTime);
            if (video.duration) setLastIndex(Math.max(0, Math.round(video.duration * fps) - 1));
        };
        const events = ['timeupdate', 'seeked', 'loadedmetadata'];
        events.forEach(event => video.addEventListener(event, update));
        update();
        return () => events.forEach(event => video.removeEventListener(event, update));
    }, [media.url]);

    const frameAt = (seconds) => Math.min(lastIndex, Math.floor(seconds * fps + 1e-3));
    const index = frameAt(time);

    // the middle of a frame, so the player and the server agree on which.
    const seek = (target) => {
        const video = videoRef.current;
        video.pause();
        video.currentTime = (Math.max(0, Math.min(lastIndex, target)) + 0.5) / fps;
    };

    // from the player, which is ahead of this panel's state on quick clicks.
    const step = (change) => seek(frameAt(videoRef.current.currentTime) + change);

    const send = async (slot) => {
        setSending(true);
        try {
            videoRef.current?.pause();
            const frame = await library.cut(media, isVideo ? { time: (index + 0.5) / fps } : {});
            sendToFrame(slot, frame.filename);
            onSent();
        } catch (error) {
            alert('Failed to use that as a frame: ' + error.message);
            setSending(false);
        }
    };

    const stepButton = (label, title, onClick) => React.createElement('button', {
        className: 'frame-step',
        title,
        onClick
    }, label);

    const sendButton = (label, slot) => React.createElement('button', {
        className: 'frame-send',
        disabled: sending,
        onClick: () => send(slot)
    }, label);

    const taken = library.frames
        .filter(frame => frame.kind === 'extract' && frame.source?.filename === media.filename)
        .sort((a, b) => a.frame_index - b.frame_index);

    return React.createElement('div', { className: 'frame-panel' },
        React.createElement('span', { className: 'frame-panel-label' },
            isVideo ? 'Use a frame in a new clip' : 'Use in a clip'
        ),
        isVideo && React.createElement('div', { className: 'frame-stepper' },
            stepButton('⏮', 'First frame', () => seek(0)),
            stepButton('◀', 'Previous frame', () => step(-1)),
            React.createElement('span', { className: 'frame-position' },
                `Frame ${index} of ${lastIndex} · ${(index / fps).toFixed(2)} s`
            ),
            stepButton('▶', 'Next frame', () => step(1)),
            stepButton('⏭', 'Last frame', () => seek(lastIndex))
        ),
        React.createElement('div', { className: 'frame-send-row' },
            sendButton('Start frame', 'first_frame'),
            sendButton('End frame', 'last_frame'),
            sendButton('Reference', 'reference')
        ),
        taken.length > 0 && React.createElement('div', { className: 'frame-taken' },
            taken.map(frame => React.createElement('button', {
                key: frame.id,
                title: `Frame ${frame.frame_index}: go to it`,
                onClick: () => seek(frame.frame_index)
            },
                React.createElement('img', { src: frame.url, alt: '' }),
                React.createElement('span', null, `f${frame.frame_index}`)
            ))
        )
    );
};

const FrameLineage = ({ label, filename, images, onOpen }) => {
    const library = useFrameLibrary();
    const frame = library.byFilename(filename);
    const root = frame ? library.family(frame)[0] : null;
    const source = root?.source ? images.findIndex(image => image.filename === root.source.filename) : -1;

    return React.createElement('div', { className: 'frame-lineage' },
        React.createElement('a', { href: `/uploads/${filename}`, target: '_blank' },
            React.createElement('img', { src: `/uploads/${filename}`, alt: label })
        ),
        React.createElement('div', null,
            React.createElement('span', { className: 'frame-panel-label' }, label),
            React.createElement('span', { className: 'frame-lineage-text' }, describeFrame(frame)),
            source !== -1 && React.createElement('button', {
                className: 'link-btn',
                onClick: () => onOpen(source)
            }, 'Open source clip')
        )
    );
};

window.FramePanel = FramePanel;
window.FrameLineage = FrameLineage;
