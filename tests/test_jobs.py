import pytest

from imagine import sweep
from imagine.estimate import Estimator, PRIOR_OVERHEAD, PRIOR_RATE, fit, work
from imagine.jobs import JobQueue

MODEL = 'http://model/predict'

def make_jobs(prompts=('a', 'b', 'c')):
    return sweep.expand(dict(model=MODEL, prompts=list(prompts)))

def test_fit_recovers_rate_and_overhead_despite_an_outlier():
    samples = [(w, 20 + 0.5 * w) for w in (100, 200, 400, 800, 1600)]
    # the first job after a server start also pays for loading the model.
    samples.append((100, 900))
    rate, overhead = fit(samples)
    assert rate == pytest.approx(0.5, rel=0.05)
    assert overhead == pytest.approx(20, abs=15)

def test_fit_with_one_configuration():
    assert fit([(100, 50), (100, 54), (100, 52)]) == (pytest.approx(0.52), 0.0)
    assert fit([]) is None

def test_estimate_uses_prior_then_measurements(tmp_path):
    estimator = Estimator(tmp_path / 'test.db')
    jobs = make_jobs()
    groups = sweep.configurations(jobs)

    before = estimator.estimate(groups, MODEL, 'fl2va')
    assert not before['calibration']['calibrated']
    assert before['seconds'] == pytest.approx(3 * (PRIOR_OVERHEAD + PRIOR_RATE * work(jobs[0])))

    estimator.record(jobs[0], 100.0)
    after = estimator.estimate(groups, MODEL, 'fl2va')
    assert after['calibration']['calibrated']
    assert after['clips'] == 3
    assert after['seconds'] == pytest.approx(300.0)
    # another model's timings are kept apart.
    assert not estimator.calibration('http://other/predict', 'fl2va')['calibrated']

def test_failed_job_does_not_stop_the_sweep(tmp_path):
    def run_job(job):
        if job['prompt'] == 'b':
            raise RuntimeError('out of memory')
        return dict(filename=f"{job['prompt']}.mp4")

    db_file = tmp_path / 'test.db'
    queue = JobQueue(db_file, run_job, Estimator(db_file))
    sweep_id = queue.submit('test', {}, make_jobs())
    while queue.run_next():
        pass

    summary = queue.sweep(sweep_id)
    assert summary['status'] == 'done'
    assert summary['counts'] == dict(queued=0, running=0, done=2, failed=1, cancelled=0)
    assert 'out of memory' in summary['errors'][0]['error']

def test_interrupted_job_is_requeued_on_restart(tmp_path):
    class Interrupted(BaseException):
        pass

    def crash(job):
        raise Interrupted()

    db_file = tmp_path / 'test.db'
    queue = JobQueue(db_file, crash, Estimator(db_file))
    sweep_id = queue.submit('test', {}, make_jobs())
    with pytest.raises(Interrupted):
        queue.run_next()
    assert queue.sweep(sweep_id)['counts']['running'] == 1

    ran = []
    restarted = JobQueue(db_file, lambda job: ran.append(job['prompt']) or {}, Estimator(db_file))
    while restarted.run_next():
        pass
    assert ran == ['a', 'b', 'c']
    assert restarted.sweep(sweep_id)['counts']['done'] == 3

def test_cancel_and_remaining_time(tmp_path):
    db_file = tmp_path / 'test.db'
    estimator = Estimator(db_file)
    queue = JobQueue(db_file, lambda job: {}, estimator)
    jobs = make_jobs()
    first = queue.submit('first', {}, jobs)
    second = queue.submit('second', {}, jobs)

    per_clip = estimator.seconds(jobs[0])
    newest, oldest = queue.sweeps()
    assert oldest['remaining_seconds'] == pytest.approx(3 * per_clip)
    # the second sweep waits behind the first on the one worker.
    assert newest['remaining_seconds'] == pytest.approx(6 * per_clip)

    assert queue.cancel(first) == 3
    assert queue.sweep(first)['status'] == 'cancelled'
    queue.run_next()
    assert queue.sweep(second)['counts']['done'] == 1
