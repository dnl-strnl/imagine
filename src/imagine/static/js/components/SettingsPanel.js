const SettingsPanel = ({ initialSettings = {}, onSettingsChange }) => {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const [settings, setSettings] = React.useState({
    guidanceScale: initialSettings.guidanceScale || 5,
    num_inference_steps: initialSettings.num_inference_steps || 50,
    negativePrompt: initialSettings.negativePrompt || '',
    model: initialSettings.model || '',
    width: initialSettings.width || 1024,
    height: initialSettings.height || 1024
  });

  React.useEffect(() => {
    setSettings(prevSettings => ({
      ...prevSettings,
      model: initialSettings.model || prevSettings.model,
      width: initialSettings.width || prevSettings.width,
      height: initialSettings.height || prevSettings.height
    }));
  }, [initialSettings.model, initialSettings.width, initialSettings.height]);

  React.useEffect(() => {
    if (initialSettings.model && initialSettings.model !== settings.model) {
      setSettings(prevSettings => ({
        ...prevSettings,
        model: initialSettings.model
      }));
    }
  }, []);

  const handleSettingChange = (key, value) => {
    const newSettings = {
      ...settings,
      [key]: value
    };
    setSettings(newSettings);
    onSettingsChange?.(newSettings);
  };

  return React.createElement('div', {
    className: 'settings-panel'
  }, [
    React.createElement('button', {
      key: 'settings-toggle',
      onClick: () => setIsExpanded(!isExpanded),
      className: 'settings-toggle'
    }, [
      React.createElement('span', {
        key: 'toggle-label',
      }, ''),
      React.createElement('span', {
        key: 'toggle-icon',
        className: `toggle-icon ${isExpanded ? 'expanded' : ''}`
      }, '▼')
    ]),
    isExpanded && React.createElement('div', {
      key: 'settings-content',
      className: 'settings-content'
    }, [
      React.createElement('div', {
        key: 'setting-model',
        className: 'setting-item'
      }, [
        React.createElement('label', {
          key: 'model-label',
          htmlFor: 'model'
        }, 'Model'),
        React.createElement('input', {
          key: 'model-input',
          id: 'model',
          type: 'text',
          value: settings.model,
          onChange: (e) => handleSettingChange('model', e.target.value),
          placeholder: 'Enter model name'
        })
      ]),

      React.createElement('div', {
        key: 'setting-width',
        className: 'setting-item'
      }, [
        React.createElement('label', {
          key: 'width-label',
          htmlFor: 'width'
        }, 'Image Width'),
        React.createElement('input', {
          key: 'width-input',
          id: 'width',
          type: 'number',
          value: settings.width,
          onChange: (e) => handleSettingChange('width', parseInt(e.target.value)),
          placeholder: 'Image width'
        })
      ]),

      React.createElement('div', {
        key: 'setting-height',
        className: 'setting-item'
      }, [
        React.createElement('label', {
          key: 'height-label',
          htmlFor: 'height'
        }, 'Image Height'),
        React.createElement('input', {
          key: 'height-input',
          id: 'height',
          type: 'number',
          value: settings.height,
          onChange: (e) => handleSettingChange('height', parseInt(e.target.value)),
          placeholder: 'Image height'
        })
      ]),

      React.createElement('div', {
        key: 'setting-guidance-scale',
        className: 'setting-item'
      }, [
        React.createElement('label', {
          key: 'guidance-scale-label',
          htmlFor: 'guidance-scale'
        }, 'Guidance Scale'),
        React.createElement('input', {
          key: 'guidance-scale-input',
          id: 'guidance-scale',
          type: 'number',
          min: '1',
          max: '20',
          step: '0.25',
          value: settings.guidanceScale,
          onChange: (e) => handleSettingChange('guidanceScale', parseFloat(e.target.value))
        })
      ]),

      React.createElement('div', {
        key: 'setting-inference-steps',
        className: 'setting-item'
      }, [
        React.createElement('label', {
          key: 'inference-steps-label',
          htmlFor: 'num-inference-steps'
        }, 'Inference Steps'),
        React.createElement('input', {
          key: 'inference-steps-input',
          id: 'num-inference-steps',
          type: 'number',
          min: '1',
          max: '1000',
          value: settings.num_inference_steps,
          onChange: (e) => handleSettingChange('num_inference_steps', parseInt(e.target.value))
        })
      ]),

      React.createElement('div', {
        key: 'setting-negative-prompt',
        className: 'setting-item'
      }, [
        React.createElement('label', {
          key: 'negative-prompt-label',
          htmlFor: 'negative-prompt'
        }, 'Negative Prompt'),
        React.createElement('input', {
          key: 'negative-prompt-input',
          id: 'negative-prompt',
          type: 'text',
          value: settings.negativePrompt,
          onChange: (e) => handleSettingChange('negativePrompt', e.target.value),
          placeholder: 'Text Prompt'
        })
      ])
    ])
  ]);
};

window.SettingsPanel = SettingsPanel;
