const splitLines = (text) => text.split('\n').map(line => line.trim()).filter(Boolean);
const splitList = (text) => text.split(/[,\n]/).map(item => item.trim()).filter(Boolean);

const SweepBuilder = ({ modelInfo, media, onQueued }) => {
    const [workflow, setWorkflow] = React.useState('fl2va');
    const [style, setStyle] = React.useState('');
    const [prompts, setPrompts] = React.useState('');
    const [variables, setVariables] = React.useState([]);
    const [inputs, setInputs] = React.useState([{}]);
    const [durations, setDurations] = React.useState([5]);
    const [resolutions, setResolutions] = React.useState('1344x768');
    const [steps, setSteps] = React.useState('50');
    const [seed, setSeed] = React.useState(0);
    const [seedCount, setSeedCount] = React.useState(1);
    const [model, setModel] = React.useState('');
    const [preview, setPreview] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [isQueueing, setIsQueueing] = React.useState(false);

    const spec = {
        workflow,
        model: model.trim() || undefined,
        style: style.trim(),
        prompts: splitLines(prompts),
        variables: Object.fromEntries(
            variables
                .filter(variable => variable.name.trim())
                .map(variable => [variable.name.trim(), splitLines(variable.values)])
        ),
        inputs,
        settings: {
            duration: [...new Set(durations)],
            resolution: splitList(resolutions),
            num_inference_steps: splitList(steps).map(Number)
        },
        seeds: { base: parseInt(seed) || 0, count: parseInt(seedCount) || 1 }
    };
    const specKey = JSON.stringify(spec);

    React.useEffect(() => {
        if (spec.prompts.length === 0) {
            setPreview(null);
            setError(null);
            return;
        }
        const timer = setTimeout(async () => {
            try {
                const response = await fetch('/sweeps/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: specKey
                });
                const data = await response.json();
                setPreview(data.success ? data : null);
                setError(data.success ? null : data.error);
            } catch (previewError) {
                setPreview(null);
                setError(previewError.message);
            }
        }, 400);
        return () => clearTimeout(timer);
    }, [specKey]);

    const queue = async (sweepSpec) => {
        setIsQueueing(true);
        try {
            const response = await fetch('/sweeps', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(sweepSpec)
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Could not queue the sweep');
            }
            onQueued?.(data);
        } catch (queueError) {
            alert('Failed to queue: ' + queueError.message);
        } finally {
            setIsQueueing(false);
        }
    };

    // two clips of different cost separate per-clip overhead from per-step time.
    const calibrate = () => queue({
        ...spec,
        name: 'Calibration',
        prompts: spec.prompts.slice(0, 1),
        variables: Object.fromEntries(
            Object.entries(spec.variables).map(([name, values]) => [name, values.slice(0, 1)])
        ),
        inputs: inputs.slice(0, 1),
        settings: { duration: [5], resolution: ['960x544'], num_inference_steps: [6, 12] },
        seeds: { base: spec.seeds.base, count: 1 }
    });

    React.useEffect(() => {
        const onSetFrame = (event) => {
            const { slot, filename } = event.detail;
            const target = slot === 'reference' ? 'ref2va' : 'fl2va';
            setWorkflow(target);
            setInputs(current => {
                const sets = workflow === target ? current : [{}];
                return sets.map((set, index) => {
                    if (index !== sets.length - 1) return set;
                    if (slot !== 'reference') return { ...set, [slot]: filename };
                    const references = set.references || [];
                    return references.some(reference => reference.filename === filename)
                        ? set
                        : { ...set, references: [...references, { type: 'image', filename }] };
                });
            });
        };
        window.addEventListener('imagine:set-frame', onSetFrame);
        return () => window.removeEventListener('imagine:set-frame', onSetFrame);
    }, [workflow]);

    const changeWorkflow = (value) => {
        setWorkflow(value);
        setInputs([{}]);
    };

    const updateVariable = (index, change) => {
        setVariables(variables.map((variable, i) => i === index ? { ...variable, ...change } : variable));
    };

    const field = (label, input, key) => React.createElement('div', {
        className: `setting-item setting-${key}`,
        key
    },
        React.createElement('label', null, label),
        input
    );

    const defaultModel = modelInfo?.video?.[workflow];
    const minDuration = modelInfo?.video_limits?.min_duration ?? 5;
    const maxDuration = modelInfo?.video_limits?.max_duration ?? 15;

    const durationSliders = React.createElement(React.Fragment, null,
        durations.map((duration, index) => React.createElement('div', {
            key: index,
            className: 'duration-row'
        },
            React.createElement('input', {
                type: 'range',
                min: minDuration,
                max: maxDuration,
                step: 1,
                value: duration,
                style: {
                    background: `linear-gradient(90deg, var(--primary) ${
                        (duration - minDuration) / (maxDuration - minDuration) * 100
                    }%, var(--border) 0)`
                },
                onChange: (e) => setDurations(
                    durations.map((item, i) => i === index ? Number(e.target.value) : item)
                )
            }),
            React.createElement('span', { className: 'duration-value' }, `${duration} s`),
            index === 0
                ? React.createElement('button', {
                    className: 'link-btn duration-button',
                    title: 'Sweep another duration',
                    onClick: () => setDurations([...durations, Math.min(maxDuration, Math.max(...durations) + 5)])
                }, '+')
                : React.createElement('button', {
                    className: 'link-btn duration-button',
                    title: 'Remove this duration',
                    onClick: () => setDurations(durations.filter((_, i) => i !== index))
                }, '×')
        ))
    );

    return React.createElement('div', { className: 'sweep-builder' },
        React.createElement('div', { className: 'search-controls' },
            React.createElement('div', { className: 'workflow-toggle' },
                [
                    ['fl2va', 'Frames', 'Text alone, or a start and end frame'],
                    ['ref2va', 'References', 'Omni reference: images, videos and audio named in the prompt']
                ].map(([value, label, title]) => React.createElement('button', {
                    key: value,
                    className: workflow === value ? 'active' : '',
                    title,
                    onClick: () => workflow !== value && changeWorkflow(value)
                }, label))
            ),
            React.createElement('input', {
                type: 'text',
                className: 'search-bar',
                value: style,
                onChange: (e) => setStyle(e.target.value),
                placeholder: 'Style (optional)'
            })
        ),
        React.createElement('textarea', {
            className: 'search-bar prompt-list',
            value: prompts,
            onChange: (e) => setPrompts(e.target.value),
            rows: 3,
            title: 'One prompt per line',
            placeholder: 'Text Prompt'
        }),

        React.createElement('div', { className: 'variable-list' },
            variables.map((variable, index) => React.createElement('div', {
                key: index,
                className: 'variable-row'
            },
                React.createElement('input', {
                    type: 'text',
                    className: 'control-input variable-name',
                    value: variable.name,
                    onChange: (e) => updateVariable(index, { name: e.target.value }),
                    placeholder: 'name'
                }),
                React.createElement('textarea', {
                    className: 'search-bar',
                    value: variable.values,
                    onChange: (e) => updateVariable(index, { values: e.target.value }),
                    rows: 2,
                    placeholder: 'Values, one per line'
                }),
                React.createElement('button', {
                    className: 'link-btn',
                    onClick: () => setVariables(variables.filter((_, i) => i !== index))
                }, 'Remove')
            )),
            React.createElement('button', {
                className: 'link-btn',
                title: 'Write {name} in a prompt to run it once per value',
                onClick: () => setVariables([...variables, { name: '', values: '' }])
            }, '+ Variable')
        ),

        React.createElement('div', { className: 'input-sets' },
            inputs.map((inputSet, index) => React.createElement(FrameInputs, {
                key: index,
                index,
                workflow,
                media,
                value: inputSet,
                limits: modelInfo?.video_limits,
                onChange: (value) => setInputs(inputs.map((item, i) => i === index ? value : item)),
                onRemove: inputs.length > 1
                    ? () => setInputs(inputs.filter((_, i) => i !== index))
                    : null,
                onAdd: index === inputs.length - 1 ? () => setInputs([...inputs, {}]) : null
            })),
            workflow === 'ref2va' && React.createElement('button', {
                className: 'link-btn',
                onClick: () => setInputs([...inputs, {}])
            }, '+ Reference set')
        ),

        React.createElement('div', { className: 'sweep-settings' }, [
            field('Duration', durationSliders, 'durations'),
            field('Resolutions', React.createElement('input', {
                type: 'text', value: resolutions, onChange: (e) => setResolutions(e.target.value),
                placeholder: '1344x768, 960x544'
            }), 'resolutions'),
            field('Steps', React.createElement('input', {
                type: 'text', value: steps, onChange: (e) => setSteps(e.target.value)
            }), 'steps'),
            field('Seed', React.createElement('input', {
                type: 'number', min: '0', value: seed, onChange: (e) => setSeed(e.target.value)
            }), 'seed'),
            field('Seeds / prompt', React.createElement('select', {
                value: seedCount, onChange: (e) => setSeedCount(e.target.value)
            }, [1, 2, 3, 4, 5, 6, 8, 10, 12, 16].map(count => {
                return React.createElement('option', { key: count, value: count }, count);
            })), 'seed-count'),
            field('Model', React.createElement('input', {
                type: 'text', value: model, onChange: (e) => setModel(e.target.value),
                placeholder: defaultModel || 'Model server URL'
            }), 'model')
        ]),

        React.createElement(SweepPreview, { preview, error }),

        React.createElement('div', { className: 'sweep-actions' },
            React.createElement('button', {
                className: 'link-btn',
                disabled: !preview || isQueueing,
                onClick: calibrate
            }, 'Calibrate'),
            React.createElement('button', {
                className: 'generate-btn',
                disabled: !preview || isQueueing,
                onClick: () => queue(spec)
            }, preview ? `Queue ${preview.clips} clip${preview.clips === 1 ? '' : 's'}` : 'Queue')
        )
    );
};

window.SweepBuilder = SweepBuilder;
