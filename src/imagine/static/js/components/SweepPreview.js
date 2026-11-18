const SweepPreview = ({ preview, error }) => {
    if (error) {
        return React.createElement('div', { className: 'sweep-preview sweep-error' }, error);
    }
    if (!preview) return null;

    const { calibration } = preview;

    return React.createElement('div', { className: 'sweep-preview' },
        React.createElement('table', { className: 'sweep-table' },
            React.createElement('thead', null,
                React.createElement('tr', null,
                    React.createElement('th', null, 'Configuration'),
                    React.createElement('th', null, 'Clips'),
                    React.createElement('th', null, 'Per clip'),
                    React.createElement('th', null, 'Total')
                )
            ),
            React.createElement('tbody', null,
                preview.configurations.map(configuration => React.createElement('tr', {
                    key: configuration.config_key
                },
                    React.createElement('td', null, configuration.config_key),
                    React.createElement('td', null, configuration.clips),
                    React.createElement('td', null, formatDuration(configuration.seconds_per_clip)),
                    React.createElement('td', null, formatDuration(configuration.seconds))
                ))
            ),
            React.createElement('tfoot', null,
                React.createElement('tr', null,
                    React.createElement('td', null, `Finishes about ${formatClock(preview.finish_at)}`),
                    React.createElement('td', null, preview.clips),
                    React.createElement('td', null),
                    React.createElement('td', null, formatDuration(preview.seconds))
                )
            )
        ),
        React.createElement('div', { className: 'sweep-note' },
            calibration.calibrated
                ? `Estimated from ${calibration.samples} finished clip${calibration.samples === 1 ? '' : 's'} on this model.`
                : 'Not calibrated: no clip has finished on this model yet, so this is a rough guess from published timings. Calibrate runs two short clips to measure it.'
        )
    );
};

window.SweepPreview = SweepPreview;
