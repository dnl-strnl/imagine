import pytest

from imagine import sweep

def test_snap_frames_stays_in_window():
    assert sweep.snap_frames(5) == 124
    assert sweep.snap_frames(10) == 243
    # 15 s would snap up to 362 frames, past the 15 s limit.
    assert sweep.snap_frames(15) == 345
    for duration in range(5, 16):
        frames = sweep.snap_frames(duration)
        assert (frames - 5) % 17 == 0
        assert 5 <= frames / sweep.FPS <= 15

def test_parse_resolution():
    assert sweep.parse_resolution('1344x768') == (1344, 768)
    assert sweep.parse_resolution('960×544') == (960, 544)
    assert sweep.parse_resolution([1000, 600]) == (992, 576)
    with pytest.raises(ValueError):
        sweep.parse_resolution('1920x1080')

def test_variables_only_multiply_templates_that_use_them():
    prompts = sweep.expand_prompts(
        ['a {animal} in {place}', 'a plain prompt', 'keep {unknown} braces'],
        dict(animal=['fox', 'owl'], place=['snow', 'rain'], unused=['x', 'y']),
    )
    assert prompts == [
        'a fox in snow', 'a fox in rain', 'a owl in snow', 'a owl in rain',
        'a plain prompt', 'keep {unknown} braces',
    ]

def test_expand_grid_counts():
    spec = dict(
        model='http://model/predict',
        prompts=['a {animal} runs', 'a {animal} sleeps'],
        variables=dict(animal=['fox', 'owl']),
        settings=dict(duration=[5, 10], resolution=['960x544'], num_inference_steps=[50]),
        seeds=dict(base=7, count=2),
    )
    jobs = sweep.expand(spec)
    groups = sweep.configurations(jobs)

    assert len(jobs) == 16
    assert [g['clips'] for g in groups] == [8, 8]
    assert {j['seed'] for j in jobs} == {7, 8}
    # configuration by configuration, so an interrupted sweep leaves whole ones.
    assert [j['config_key'] for j in jobs] == [groups[0]['config_key']] * 8 + [groups[1]['config_key']] * 8

def test_input_sets_multiply_and_validate():
    spec = dict(
        prompts=['p'],
        inputs=[dict(first_frame='a.png'), dict(first_frame='b.png', last_frame='c.png')],
    )
    jobs = sweep.expand(spec)
    assert [(j['first_frame'], j['last_frame']) for j in jobs] == [('a.png', None), ('b.png', 'c.png')]

    with pytest.raises(ValueError):
        sweep.expand(dict(prompts=['p'], workflow='ref2va'))
    with pytest.raises(ValueError):
        sweep.expand(dict(prompts=['p'], inputs=[dict(references=[dict(type='image', filename='a.png')])]))
    with pytest.raises(ValueError):
        sweep.expand(dict(prompts=['p'], workflow='ref2va', inputs=[
            dict(references=[dict(type='audio', filename='a.wav')])
        ]))
    with pytest.raises(ValueError):
        sweep.expand(dict(prompts=['p'], workflow='ref2va', inputs=[
            dict(references=[dict(type='video', filename=f'{i}.mp4') for i in range(4)])
        ]))

    references = [dict(type='image', filename='a.png'), dict(type='audio', filename='a.wav')]
    jobs = sweep.expand(dict(prompts=['p'], workflow='ref2va', inputs=[dict(references=references)]))
    assert jobs[0]['references'] == references

def test_rejects_bad_settings():
    with pytest.raises(ValueError):
        sweep.expand(dict(prompts=[]))
    with pytest.raises(ValueError):
        sweep.expand(dict(prompts=['p'], settings=dict(duration=[20])))
