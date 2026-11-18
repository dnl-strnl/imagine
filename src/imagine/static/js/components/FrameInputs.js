const REFERENCE_TAGS = { image: 'Picture', video: 'Video', audio: 'Audio' };

const mediaKind = (file) => {
    const kind = (file.type || '').split('/')[0];
    return REFERENCE_TAGS[kind] ? kind : null;
};

const uploadMedia = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/upload', { method: 'POST', body: formData });
    const data = await response.json();
    if (!data.success) {
        throw new Error(data.error || 'Upload failed');
    }
    return data.filename;
};

const MediaThumb = ({ type, filename }) => {
    const src = `/uploads/${filename}`;
    if (type === 'video') {
        return React.createElement('video', { src, muted: true, preload: 'metadata' });
    }
    if (type === 'audio') {
        return React.createElement('div', { className: 'audio-thumb' }, '♪');
    }
    return React.createElement('img', { src, alt: filename });
};

const MediaSlot = ({ label, accept, multiple, onFiles, children }) => {
    const [dragover, setDragover] = React.useState(false);
    const inputRef = React.useRef(null);

    return React.createElement('div', {
        className: `drop-zone media-slot ${dragover ? 'dragover' : ''}`,
        onClick: () => inputRef.current?.click(),
        onDragOver: (e) => { e.preventDefault(); setDragover(true); },
        onDragLeave: () => setDragover(false),
        onDrop: (e) => {
            e.preventDefault();
            setDragover(false);
            onFiles(Array.from(e.dataTransfer.files));
        }
    },
        React.createElement('p', null, label),
        React.createElement('input', {
            ref: inputRef,
            type: 'file',
            accept,
            multiple,
            style: { display: 'none' },
            onChange: (e) => {
                onFiles(Array.from(e.target.files));
                e.target.value = '';
            }
        }),
        children
    );
};

const FrameSlot = ({ label, slot, filename, media, onPick, onClear }) => {
    const library = useFrameLibrary();
    const [hovered, setHovered] = React.useState(false);
    const [dragover, setDragover] = React.useState(false);
    const [loading, setLoading] = React.useState(false);
    const inputRef = React.useRef(null);

    const frame = filename ? library.byFilename(filename) : null;
    const family = frame ? library.family(frame) : [];

    const pick = async (work) => {
        setLoading(true);
        try {
            onPick((await work()).filename);
        } catch (error) {
            alert('Failed to use that as a frame: ' + error.message);
        } finally {
            setLoading(false);
        }
    };

    // a file dropped on a filled slot is a new version of its frame.
    const take = (files) => {
        const file = files.find(f => mediaKind(f) === 'image');
        if (file) pick(() => library.upload(file, frame));
    };

    const step = (event, change) => {
        event.stopPropagation();
        onPick(family[frame.version - 1 + change].filename);
    };

    const pickerItem = (key, title, onClick, content, badge) => React.createElement('div', {
        key,
        className: 'frame-picker-item',
        title,
        onClick: () => {
            setHovered(false);
            onClick();
        }
    }, content, badge && React.createElement('span', { className: 'frame-picker-badge' }, badge));

    const frames = library.latest().slice(0, 12);
    const picker = hovered && !dragover && (frames.length > 0 || media?.length > 0)
        && React.createElement('div', { className: 'frame-picker' },
            frames.length > 0 && React.createElement('div', { className: 'frame-picker-note' }, 'Frames'),
            frames.length > 0 && React.createElement('div', { className: 'frame-picker-grid' },
                frames.map(item => pickerItem(
                    item.id,
                    describeFrame(item),
                    () => onPick(item.filename),
                    React.createElement('img', { src: item.url, alt: '' }),
                    item.versions > 1 && `v${item.version}`
                ))
            ),
            media?.length > 0 && React.createElement('div', { className: 'frame-picker-note' },
                `Recent results. A clip gives its ${FRAME_OF_CLIP[slot]} frame.`
            ),
            media?.length > 0 && React.createElement('div', { className: 'frame-picker-grid' },
                media.map(item => pickerItem(
                    item.url,
                    item.prompt,
                    () => pick(() => library.cut(item, { frame: FRAME_OF_CLIP[slot] })),
                    item.media_type === 'video'
                        ? React.createElement('video', { src: item.url, muted: true, preload: 'metadata' })
                        : React.createElement('img', { src: item.url, alt: '' })
                ))
            )
        );

    return React.createElement('div', {
        className: 'frame-slot-wrap',
        onMouseEnter: () => setHovered(true),
        onMouseLeave: () => setHovered(false)
    }, React.createElement('div', {
        className: `frame-slot ${filename ? 'filled' : ''} ${dragover ? 'dragover' : ''}`,
        title: filename ? `${describeFrame(frame)}\nDrop or click to add an edited version.` : null,
        onClick: () => inputRef.current?.click(),
        onDragOver: (e) => { e.preventDefault(); setDragover(true); },
        onDragLeave: () => setDragover(false),
        onDrop: (e) => {
            e.preventDefault();
            setDragover(false);
            const dragged = e.dataTransfer.getData(MEDIA_DRAG_TYPE);
            if (dragged) {
                pick(() => library.cut(JSON.parse(dragged), { frame: FRAME_OF_CLIP[slot] }));
            } else {
                take(Array.from(e.dataTransfer.files));
            }
        }
    },
        React.createElement('input', {
            ref: inputRef,
            type: 'file',
            accept: 'image/*',
            style: { display: 'none' },
            onChange: (e) => {
                take(Array.from(e.target.files));
                e.target.value = '';
            }
        }),
        filename && React.createElement('img', { src: `/uploads/${filename}`, alt: label }),
        React.createElement('span', { className: 'frame-label' }, label),
        !filename && React.createElement('div', { className: 'frame-empty' },
            React.createElement('span', { className: 'frame-plus' }, '+'),
            React.createElement('span', null, loading ? 'Loading…' : 'Drop or click')
        ),
        filename && (loading || dragover) && React.createElement('div', { className: 'frame-busy' },
            loading ? 'Loading…' : 'Add as an edited version'
        ),
        frame && React.createElement('div', {
            className: 'frame-meta',
            onClick: (e) => e.stopPropagation()
        },
            family.length > 1 && React.createElement('button', {
                disabled: frame.version === 1,
                title: 'Earlier version',
                onClick: (e) => step(e, -1)
            }, '‹'),
            React.createElement('span', null,
                (family[0].frame_index != null ? `f${family[0].frame_index} · ` : '')
                + (family.length > 1 ? `v${frame.version} of ${family.length}` : 'original')
            ),
            family.length > 1 && React.createElement('button', {
                disabled: frame.version === family.length,
                title: 'Later version',
                onClick: (e) => step(e, 1)
            }, '›'),
            React.createElement('a', {
                href: `/uploads/${filename}`,
                download: `frame-${frame.root_id}-v${frame.version}${filename.slice(filename.lastIndexOf('.'))}`,
                title: 'Download to edit elsewhere, then drop the edit here'
            }, '⤓')
        ),
        filename && React.createElement('button', {
            className: 'remove-btn',
            title: `Remove ${label.toLowerCase()}`,
            onClick: (e) => { e.stopPropagation(); onClear(); }
        }, '×')
    ), picker);
};

const FrameInputs = ({ workflow, value, onChange, limits, onRemove, onAdd, index, media }) => {
    const references = value.references || [];

    const addReferences = async (files) => {
        const added = [...references];
        for (const file of files) {
            const type = mediaKind(file);
            if (!type) continue;
            const limit = limits?.references?.[type] ?? Infinity;
            if (added.filter(r => r.type === type).length >= limit) {
                alert(`At most ${limit} ${type} references.`);
                continue;
            }
            if (added.length >= (limits?.max_references ?? Infinity)) {
                alert(`At most ${limits.max_references} references in total.`);
                break;
            }
            try {
                added.push({ type, filename: await uploadMedia(file) });
            } catch (error) {
                alert('Failed to upload reference: ' + error.message);
            }
        }
        onChange({ ...value, references: added });
    };

    const frameSlot = (key, label) => React.createElement(FrameSlot, {
        label,
        slot: key,
        filename: value[key],
        media,
        onPick: (filename) => onChange({ ...value, [key]: filename }),
        onClear: () => onChange({ ...value, [key]: null })
    });

    if (workflow !== 'ref2va') {
        return React.createElement('div', { className: 'frame-set' },
            React.createElement('div', { className: 'frame-pair' },
                frameSlot('first_frame', 'Start frame'),
                React.createElement('button', {
                    className: 'swap-btn',
                    title: 'Swap start and end frame',
                    disabled: !value.first_frame && !value.last_frame,
                    onClick: () => onChange({
                        ...value,
                        first_frame: value.last_frame,
                        last_frame: value.first_frame
                    })
                }, '⇄'),
                frameSlot('last_frame', 'End frame')
            ),
            React.createElement('div', { className: 'frame-hint' },
                onRemove && React.createElement('span', null, `Frame set ${index + 1}`),
                React.createElement('div', { className: 'frame-links' },
                    onAdd && React.createElement('button', {
                        className: 'link-btn',
                        onClick: onAdd
                    }, '+ Frame set'),
                    onRemove && React.createElement('button', {
                        className: 'link-btn',
                        onClick: onRemove
                    }, 'Remove set')
                )
            )
        );
    }

    const counts = {};
    const tagged = references.map(reference => {
        counts[reference.type] = (counts[reference.type] || 0) + 1;
        return { ...reference, tag: `<${REFERENCE_TAGS[reference.type]} ${counts[reference.type]}>` };
    });

    return React.createElement('div', { className: 'input-set' },
        React.createElement(MediaSlot, {
                label: 'References — images, videos, audio. Use the tags in the prompt.',
                accept: 'image/*,video/*,audio/*',
                multiple: true,
                onFiles: addReferences
            }, tagged.length > 0 && React.createElement('div', {
                className: 'reference-list',
                onClick: (e) => e.stopPropagation()
            }, tagged.map((reference, index) => React.createElement('div', {
                key: reference.filename,
                className: 'preview-container reference-item',
                title: reference.type === 'image'
                    ? describeFrame(FrameLibrary.byFilename(reference.filename)) : null
            },
                React.createElement(MediaThumb, reference),
                React.createElement('span', { className: 'reference-tag' }, reference.tag),
                React.createElement('button', {
                    className: 'remove-btn',
                    onClick: () => onChange({
                        ...value,
                        references: references.filter((_, i) => i !== index)
                    })
                }, '×')
            )))),
        onRemove && React.createElement('button', {
            className: 'link-btn',
            onClick: onRemove
        }, 'Remove')
    );
};

window.FrameInputs = FrameInputs;
