const QueuePanel = ({ sweeps, selectedSweep, onSelect, onCancel }) => {
    if (!sweeps || sweeps.length === 0) return null;

    return React.createElement('div', { className: 'queue-panel' },
        sweeps.map(sweep => {
            const { counts, current } = sweep;
            const finished = counts.done + counts.failed + counts.cancelled;
            const active = counts.queued + counts.running > 0;
            const percent = sweep.total ? (finished / sweep.total) * 100 : 0;

            const parts = [`${counts.done} of ${sweep.total} done`];
            if (counts.failed) parts.push(`${counts.failed} failed`);
            if (counts.cancelled) parts.push(`${counts.cancelled} cancelled`);
            if (active) {
                parts.push(`${formatDuration(sweep.remaining_seconds)} left`);
                parts.push(`finishes about ${formatClock(sweep.finish_at)}`);
            }

            return React.createElement('div', {
                key: sweep.id,
                className: `queue-item ${selectedSweep === sweep.id ? 'selected' : ''}`
            },
                React.createElement('div', { className: 'queue-header' },
                    React.createElement('button', {
                        className: 'link-btn queue-name',
                        title: 'Show only this sweep',
                        onClick: () => onSelect(selectedSweep === sweep.id ? null : sweep.id)
                    }, sweep.name || `Sweep ${sweep.id}`),
                    React.createElement('span', { className: 'queue-stats' }, parts.join(' · ')),
                    active && React.createElement('button', {
                        className: 'link-btn',
                        onClick: () => onCancel(sweep.id)
                    }, 'Cancel')
                ),
                React.createElement('div', { className: 'progress-bar' },
                    React.createElement('div', {
                        className: `progress-fill ${active ? '' : 'done'}`,
                        style: {
                            width: `${percent}%`,
                            // stretch the spectrum to the whole bar: red at start, blue near done.
                            backgroundSize: percent ? `${10000 / percent}% 100%` : undefined
                        }
                    })
                ),
                current && React.createElement('div', { className: 'queue-current' },
                    `${current.config_key} · ${formatDuration(current.elapsed)} of about ${formatDuration(current.expected)} · ${current.prompt}`
                ),
                sweep.errors.map(error => React.createElement('div', {
                    key: error.job_id,
                    className: 'sweep-error'
                }, error.error))
            );
        })
    );
};

window.QueuePanel = QueuePanel;
