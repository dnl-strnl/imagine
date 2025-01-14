const SettingsPanel = ({ initialSettings = {}, onSettingsChange }) => {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const [settings, setSettings] = React.useState({
    guidanceScale: initialSettings.guidanceScale || 7.5,
    num_inference_steps: initialSettings.num_inference_steps || 50,
    negativePrompt: initialSettings.negativePrompt || ''
  });

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
      key: 'toggle',
      onClick: () => setIsExpanded(!isExpanded),
      className: 'settings-toggle'
    }, [
      React.createElement('span', {
        key: 'label',
      }, ''),
      React.createElement('span', {
        key: 'icon',
        className: `toggle-icon ${isExpanded ? 'expanded' : ''}`
      }, '▼')
    ]),
    isExpanded && React.createElement('div', {
      key: 'content',
      className: 'settings-content'
    }, [

      // Guidance Scale Input
      React.createElement('div', {
        key: 'guidance-scale',
        className: 'setting-item'
      }, [
        React.createElement('label', {
          htmlFor: 'guidance-scale'
        }, 'Guidance Scale'),
        React.createElement('input', {
          id: 'guidance-scale',
          type: 'number',
          min: '1',
          max: '20',
          step: '0.25',
          value: settings.guidanceScale,
          onChange: (e) => handleSettingChange('guidanceScale', parseFloat(e.target.value))
        })
      ]),

      // Inference Steps Input
      React.createElement('div', {
        key: 'inference-steps',
        className: 'setting-item'
      }, [
        React.createElement('label', {
          htmlFor: 'num-inference-steps'
        }, 'Inference Steps'),
        React.createElement('input', {
          id: 'num-inference-steps',
          type: 'number',
          min: '1',
          max: '1000',
          value: settings.num_inference_steps,
          onChange: (e) => handleSettingChange('num_inference_steps', parseInt(e.target.value))
        })
      ]),

      // Negative Prompt Input
      React.createElement('div', {
        key: 'negative-prompt',
        className: 'setting-item'
      }, [
        React.createElement('label', {
          htmlFor: 'negative-prompt'
        }, 'Negative Prompt'),
        React.createElement('input', {
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

// Make the component available globally
window.SettingsPanel = SettingsPanel;
