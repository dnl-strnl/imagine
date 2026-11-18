const ImagePreviewModal = ({ images, initialIndex, onClose }) => {
    const [currentIndex, setCurrentIndex] = React.useState(initialIndex);
    const videoRef = React.useRef(null);

    if (!images || !images[currentIndex]) {
        console.error('Invalid images or index');
        return null;
    }

    const currentImage = images[currentIndex];
    const isVideo = currentImage.media_type === 'video';
    const references = currentImage.references || [];

    React.useEffect(() => {
        const handleKeyPress = (e) => {
            if (e.key === 'ArrowLeft') {
                setCurrentIndex(prev => prev > 0 ? prev - 1 : images.length - 1);
            } else if (e.key === 'ArrowRight') {
                setCurrentIndex(prev => prev < images.length - 1 ? prev + 1 : 0);
            } else if (e.key === 'Escape') {
                onClose();
            }
        };

        window.addEventListener('keydown', handleKeyPress);
        return () => window.removeEventListener('keydown', handleKeyPress);
    }, [images.length, onClose]);

    const containerStyle = {
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.85)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 1000
    };

    const contentStyle = {
        backgroundColor: 'rgb(36, 36, 36)',
        borderRadius: '0.75rem',
        width: '90vw',
        height: '90vh',
        display: 'flex',
        position: 'relative',
        overflow: 'hidden',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)'
    };

    const imageContainerStyle = {
        flex: 1,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        position: 'relative',
        backgroundColor: 'rgb(29, 29, 29)'
    };

    const imageStyle = {
        maxHeight: '85vh',
        maxWidth: '100%',
        objectFit: 'contain'
    };

    const sidebarStyle = {
        width: '320px',
        backgroundColor: 'rgb(36, 36, 36)',
        padding: '1.75rem',
        borderLeft: '1px solid rgba(255, 255, 255, 0.1)',
        display: 'flex',
        flexDirection: 'column',
        gap: '1.25rem',
        overflowY: 'auto'
    };

    const buttonStyle = {
        position: 'absolute',
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        color: 'white',
        border: 'none',
        borderRadius: '50%',
        width: '44px',
        height: '44px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        fontSize: '1.25rem',
        backdropFilter: 'blur(4px)'
    };

    const closeButtonStyle = {
        position: 'absolute',
        right: '1.25rem',
        top: '1.25rem',
        backgroundColor: 'rgba(255, 255, 255, 0.1)',
        border: 'none',
        color: 'white',
        cursor: 'pointer',
        width: '32px',
        height: '32px',
        borderRadius: '6px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all 0.2s ease',
        fontSize: '1.25rem'
    };

    const detailsContainerStyle = {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem'
    };

    const detailItemStyle = {
        color: 'white',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.25rem'
    };

    const labelStyle = {
        color: 'rgba(255, 255, 255, 0.6)',
        fontSize: '0.875rem',
        fontWeight: 500
    };

    const valueStyle = {
        color: 'white',
        fontSize: '0.9375rem',
        lineHeight: '1.5',
        wordBreak: 'break-word'
    };

    const settingsGridStyle = {
        display: 'grid',
        gridTemplateColumns: '1fr auto',
        gap: '0.5rem',
        fontSize: '0.875rem',
        color: 'rgba(255, 255, 255, 0.8)'
    };

    return React.createElement('div', { style: containerStyle },
            React.createElement('div', { style: contentStyle },
                React.createElement('div', { style: imageContainerStyle },
                    React.createElement('button', {
                        style: { ...buttonStyle, left: '20px' },
                        onClick: () => setCurrentIndex(prev => prev > 0 ? prev - 1 : images.length - 1)
                    }, '←'),
                    isVideo
                        ? React.createElement('video', {
                            key: currentImage.url,
                            ref: videoRef,
                            src: currentImage.url,
                            controls: true,
                            autoPlay: true,
                            loop: true,
                            style: imageStyle
                        })
                        : React.createElement('img', {
                            src: currentImage.url || `/uploads/${currentImage.filename}`,
                            alt: currentImage.filename,
                            style: imageStyle
                        }),
                    React.createElement('button', {
                        style: { ...buttonStyle, right: '20px' },
                        onClick: () => setCurrentIndex(prev => prev < images.length - 1 ? prev + 1 : 0)
                    }, '→')
                ),
                React.createElement('div', { style: sidebarStyle },
                    React.createElement('button', {
                        onClick: onClose,
                        style: closeButtonStyle
                    }, '×'),
                    React.createElement('h2', {
                        style: {
                            color: 'white',
                            fontSize: '1.25rem',
                            fontWeight: '600',
                            marginBottom: '0.5rem'
                        }
                    }, isVideo ? 'Video Details' : 'Image Details'),
                    React.createElement('div', { style: detailsContainerStyle }, [
                      // Basic Details
                      React.createElement('div', { style: detailItemStyle, key: 'model' },
                          React.createElement('span', { style: labelStyle }, 'Model'),
                          React.createElement('span', { style: valueStyle }, currentImage.model || 'Not specified')
                      ),
                      React.createElement('div', { style: detailItemStyle, key: 'prompt' },
                          React.createElement('span', { style: labelStyle }, 'Prompt'),
                          React.createElement('span', { style: valueStyle }, currentImage.prompt || 'No prompt provided')
                      ),
                      React.createElement('div', { style: detailItemStyle, key: 'seed' },
                          React.createElement('span', { style: labelStyle }, 'Seed'),
                          React.createElement('span', { style: valueStyle },
                              currentImage.seed !== undefined && currentImage.seed !== null
                                  ? currentImage.seed
                                  : 'Not specified'
                          )
                      ),
                      currentImage.style && React.createElement('div', { style: detailItemStyle, key: 'style' },
                          React.createElement('span', { style: labelStyle }, 'Style Prompt'),
                          React.createElement('span', { style: valueStyle }, currentImage.style)
                      ),
                      React.createElement(FramePanel, {
                          key: `frame-panel-${currentImage.url}`,
                          media: currentImage,
                          videoRef,
                          onSent: onClose
                      }),
                      // Video inputs section (only if exists)
                      isVideo && (currentImage.first_frame || currentImage.last_frame || references.length > 0)
                          && React.createElement('div', {
                          style: {
                              ...detailItemStyle,
                              marginTop: '1rem',
                              paddingTop: '1rem',
                              borderTop: '1px solid rgba(255, 255, 255, 0.1)'
                          },
                          key: 'video-inputs-section'
                      }, [
                          currentImage.first_frame && React.createElement(FrameLineage, {
                              key: 'first',
                              label: 'Start Frame',
                              filename: currentImage.first_frame,
                              images,
                              onOpen: setCurrentIndex
                          }),
                          currentImage.last_frame && React.createElement(FrameLineage, {
                              key: 'last',
                              label: 'End Frame',
                              filename: currentImage.last_frame,
                              images,
                              onOpen: setCurrentIndex
                          }),
                          references.map((reference, index) => reference.type === 'image'
                              ? React.createElement(FrameLineage, {
                                  key: reference.filename,
                                  label: `Reference ${index + 1}`,
                                  filename: reference.filename,
                                  images,
                                  onOpen: setCurrentIndex
                              })
                              : React.createElement('div', { style: detailItemStyle, key: reference.filename },
                                  React.createElement('span', { style: labelStyle }, `Reference ${index + 1}`),
                                  React.createElement('span', { style: valueStyle },
                                      `${reference.type}: /uploads/${reference.filename}`
                                  )
                              )
                          )
                      ]),
                      // Image Prompt section (only if exists)
                      !isVideo && currentImage.source_image && React.createElement('div', {
                          style: {
                              ...detailItemStyle,
                              marginTop: '1rem',
                              paddingTop: '1rem',
                              borderTop: '1px solid rgba(255, 255, 255, 0.1)'
                          },
                          key: 'image-prompt-section'
                      }, [
                          React.createElement('div', { style: detailItemStyle, key: 'source' },
                              React.createElement('span', { style: labelStyle }, 'Image Prompt'),
                              React.createElement('span', { style: valueStyle }, `/uploads/${currentImage.source_image}`)
                          )
                      ]),
                      // Settings section with divider
                      React.createElement('div', {
                          style: {
                              ...detailItemStyle,
                              marginTop: '1rem',
                              paddingTop: '1rem',
                              borderTop: '1px solid rgba(255, 255, 255, 0.1)'
                          },
                          key: 'settings'
                      }, [
                          React.createElement('div', { style: settingsGridStyle },
                              React.createElement('span', null, 'Image Width:'),
                              React.createElement('span', null, currentImage.width || 'N/A'),
                              React.createElement('span', null, 'Image Height:'),
                              React.createElement('span', null, currentImage.height || 'N/A'),
                              !isVideo && React.createElement('span', null, 'Guidance Scale:'),
                              !isVideo && React.createElement('span', null, currentImage.settings?.guidanceScale || 'N/A'),
                              React.createElement('span', null, 'Inference Steps:'),
                              React.createElement('span', null, currentImage.settings?.num_inference_steps || 'N/A'),
                              isVideo && React.createElement('span', null, 'Frames:'),
                              isVideo && React.createElement('span', null,
                                  `${currentImage.num_frames} @ ${currentImage.fps} fps`
                              ),
                              isVideo && React.createElement('span', null, 'Generation Time:'),
                              isVideo && React.createElement('span', null, formatDuration(currentImage.elapsed)),
                              isVideo && currentImage.sweep_id && React.createElement('span', null, 'Sweep:'),
                              isVideo && currentImage.sweep_id && React.createElement('span', null, currentImage.sweep_id),
                              currentImage.settings?.negativePrompt && [
                                  React.createElement('span', { key: 'neg-label', style: { gridColumn: '1 / -1' } },
                                      'Negative Prompt:'
                                  ),
                                  React.createElement('span', {
                                      key: 'neg-value',
                                      style: {
                                          gridColumn: '1 / -1',
                                          color: 'rgba(255, 255, 255, 0.6)',
                                          fontStyle: 'italic'
                                      }
                                  }, currentImage.settings.negativePrompt)
                              ]
                          )
                      ])
                  ]),
                  React.createElement('div', {
                      style: {
                          color: 'rgba(255, 255, 255, 0.6)',
                          marginTop: 'auto',
                          fontSize: '0.875rem',
                          textAlign: 'center'
                      }
                  }, `Image ${currentIndex + 1} of ${images.length}`)
                )
            )
        );
};

window.ImagePreviewModal = ImagePreviewModal;
