// Constants
const DEFAULT_SETTINGS = {
    batchSize: 1,
    seed: '',
    guidanceScale: 5,
    num_inference_steps: 50,
    negativePrompt: '',
    height: 1024,
    width: 1024,
};

const API_ENDPOINTS = {
    UPLOAD: '/upload',
    GENERATE: '/generate',
    MODEL_INFO: '/model-info'
};

class ProgressTracker {
    constructor() {
        this.isRunning = false;
        this.startTime = null;
        this.estimatedDuration = 30;
        this.animationFrame = null;
        this.elements = {
            container: document.getElementById('progressContainer'),
            fill: document.getElementById('progressFill'),
            percentage: document.getElementById('progressPercentage'),
            elapsed: document.getElementById('elapsedTime'),
            remaining: document.getElementById('remainingTime')
        };
    }

    start(estimatedDuration = 30) {
        if (this.isRunning) return;

        this.estimatedDuration = estimatedDuration;
        this.isRunning = true;
        this.startTime = Date.now();

        if (this.elements.container) {
            this.elements.container.classList.add('show');
        }
        this.updateProgress();
    }

    stop() {
        if (!this.isRunning) return;

        this.isRunning = false;
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
        }

        // Complete the progress bar
        if (this.elements.fill) this.elements.fill.style.width = '100%';
        if (this.elements.percentage) this.elements.percentage.textContent = '100%';
        if (this.elements.remaining) this.elements.remaining.textContent = '0s';

        // Hide after a short delay
        setTimeout(() => {
            if (this.elements.container) {
                this.elements.container.classList.remove('show');
            }
            this.reset();
        }, 1000);
    }

    cancel() {
        if (!this.isRunning) return;

        this.isRunning = false;
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
        }

        if (this.elements.container) {
            this.elements.container.classList.remove('show');
        }
        this.reset();
    }

    reset() {
        if (this.elements.fill) this.elements.fill.style.width = '0%';
        if (this.elements.percentage) this.elements.percentage.textContent = '0%';
        if (this.elements.elapsed) this.elements.elapsed.textContent = '0s';
        if (this.elements.remaining) this.elements.remaining.textContent = '--s';
    }

    updateProgress() {
        if (!this.isRunning) return;

        const elapsed = (Date.now() - this.startTime) / 1000;

        // Cap progress at 99% until we know the request is complete
        const progressPercent = Math.min(elapsed / this.estimatedDuration, 0.99) * 100;
        const remaining = Math.max(this.estimatedDuration - elapsed, 0);

        if (this.elements.fill) this.elements.fill.style.width = `${progressPercent}%`;
        if (this.elements.percentage) this.elements.percentage.textContent = `${Math.round(progressPercent)}%`;
        if (this.elements.elapsed) this.elements.elapsed.textContent = `${Math.round(elapsed)}s`;
        if (this.elements.remaining) this.elements.remaining.textContent = `${Math.round(remaining)}s`;

        // Continue updating
        this.animationFrame = requestAnimationFrame(() => this.updateProgress());
    }
}

class ImageGenerator {
    constructor() {
        this.elements = this.initializeElements();
        this.progressTracker = new ProgressTracker();

        this.state = {
            isGenerating: false,
            generatedImages: [],
            sourceImage: null,
            settings: {
                ...DEFAULT_SETTINGS,
                batchSize: this.getBatchSizeFromDOM(),
                seed: this.getSeedFromDOM()
            }
        };

        this.initializeApp();
    }

    getBatchSizeFromDOM() {
        const batchSize = document.getElementById('batchSize')?.value;
        return batchSize ? parseInt(batchSize) : DEFAULT_SETTINGS.batchSize;
    }

    getSeedFromDOM() {
        const seedValue = document.getElementById('seedValue')?.value;
        return seedValue ? parseInt(seedValue) : DEFAULT_SETTINGS.seed;
    }

    initializeElements() {
        const elements = {
            promptInput: document.getElementById('promptInput'),
            generateBtn: document.getElementById('generateBtn'),
            dropZone: document.getElementById('dropZone'),
            fileInput: document.getElementById('fileInput'),
            imageGrid: document.getElementById('imageGrid'),
            loadingIndicator: document.getElementById('loadingIndicator'),
            sourceImagePreview: document.createElement('div'),
            batchSizeInput: document.getElementById('batchSize'),
            seedInput: document.getElementById('seedValue')
        };

        Object.entries(elements).forEach(([key, element]) => {
            if (!element) {
                console.error(`Required element not found: ${key}`);
            }
        });

        elements.sourceImagePreview.className = 'source-image-preview';
        if (elements.dropZone) {
            elements.dropZone.appendChild(elements.sourceImagePreview);
        }
        return elements;
    }

    calculateEstimatedWait(batchSize, numInferenceSteps) {
        // Estimate based on your model's performance
        const baseTimePerImage = 8; // seconds per image
        const stepMultiplier = numInferenceSteps / 50; // normalize to 50 steps
        const batchMultiplier = Math.sqrt(batchSize); // batch processing is more efficient

        return Math.round(baseTimePerImage * stepMultiplier * batchMultiplier);
    }

    async initializeApp() {
        await this.fetchModelInfo();
        this.initializeSettingsPanel();
        this.setupEventListeners();
        this.loadSavedImages();
    }

    handleSettingsChange(newSettings) {
        const parsedSettings = { ...newSettings };

        if ('width' in newSettings) {
            parsedSettings.width = parseInt(newSettings.width) || 1024;
        }
        if ('height' in newSettings) {
            parsedSettings.height = parseInt(newSettings.height) || 1024;
        }
        if ('num_inference_steps' in newSettings) {
            parsedSettings.num_inference_steps = parseInt(newSettings.num_inference_steps) || 50;
        }
        if ('guidanceScale' in newSettings) {
            parsedSettings.guidanceScale = parseFloat(newSettings.guidanceScale) || 7.5;
        }

        this.state.settings = {
            ...this.state.settings,
            ...parsedSettings
        };

        if (newSettings.model !== undefined) {
            this.state.model = newSettings.model;
        }
    }

    setupEventListeners() {
        // Generate button events
        this.elements.generateBtn.addEventListener('click', this.handleGenerate.bind(this));
        this.elements.promptInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleGenerate();
            }
        });

        // Batch size input
        this.elements.batchSizeInput?.addEventListener('change', (e) => {
            const value = Math.max(1, Math.min(4, parseInt(e.target.value) || 1));
            e.target.value = value;
            this.handleSettingsChange({ batchSize: value });
        });

        // Seed input
        this.elements.seedInput?.addEventListener('change', (e) => {
            const value = parseInt(e.target.value) || '';
            this.handleSettingsChange({ seed: value });
        });

        this.setupFileUploadListeners();
    }

    setupFileUploadListeners() {
        const { dropZone, fileInput } = this.elements;

        if (!dropZone || !fileInput) return;

        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file) this.handleImageUpload(file);
        });

        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) this.handleImageUpload(file);
        });
    }

    async handleImageUpload(file) {
        this.showLoading(true);

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(API_ENDPOINTS.UPLOAD, {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error || 'Upload failed');
            }

            this.state.sourceImage = data.filename;
            this.updateSourceImagePreview(file);
        } catch (error) {
            console.error('Upload error:', error);
            this.clearSourceImage();
            alert('Failed to upload image: ' + error.message);
        } finally {
            this.showLoading(false);
        }
    }

    updateSourceImagePreview(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            this.elements.sourceImagePreview.innerHTML = `
                <div class="preview-container">
                    <img src="${e.target.result}" alt="Source image">
                    <button class="remove-btn" onclick="app.clearSourceImage()">×</button>
                </div>
            `;
            this.elements.dropZone.classList.add('has-image');
        };
        reader.readAsDataURL(file);
    }

    clearSourceImage() {
        this.state.sourceImage = null;
        this.elements.sourceImagePreview.innerHTML = '';
        this.elements.dropZone.classList.remove('has-image');
        this.elements.fileInput.value = '';
    }

    async handleGenerate() {
        if (this.state.isGenerating) {
            console.debug('Generation in progress...');
            return;
        }

        const prompt = this.elements.promptInput.value.trim();
        if (!prompt) {
            alert('Please enter a prompt!');
            return;
        }

        try {
            this.state.isGenerating = true;
            this.elements.generateBtn.disabled = true;
            this.elements.generateBtn.textContent = 'Generating...';

            // Calculate estimated wait time
            const estimatedWait = this.calculateEstimatedWait(
                this.state.settings.batchSize,
                this.state.settings.num_inference_steps
            );

            // Start progress tracking
            this.progressTracker.start(estimatedWait);

            const response = await fetch(API_ENDPOINTS.GENERATE, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  prompt,
                  batch_size: this.state.settings.batchSize,
                  seed: this.state.settings.seed || undefined,
                  guidance_scale: this.state.settings.guidanceScale,
                  num_inference_steps: this.state.settings.num_inference_steps,
                  negative_prompt: this.state.settings.negativePrompt,
                  model: this.state.model,
                  height: this.state.settings.height,
                  width: this.state.settings.width,
                  image: this.state.sourceImage
                })
            });

            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error || 'Generation failed');
            }

            // Stop progress and show completion
            this.progressTracker.stop();

            // Add generated images after a short delay to show completion
            setTimeout(() => {
                this.addGeneratedImages(data.images);
            }, 1200);

        } catch (error) {
            console.error('Generation error:', error);
            this.progressTracker.cancel();
            alert('Failed to generate images: ' + error.message);
        } finally {
            this.state.isGenerating = false;
            this.elements.generateBtn.disabled = false;
            this.elements.generateBtn.textContent = 'Generate';
        }
    }

    addGeneratedImages(images) {
        const fragment = document.createDocumentFragment();

        images.forEach(image => {
            const imageWithMetadata = {
                ...image,
                model: this.state.model,
                settings: { ...this.state.settings }
            };

            this.state.generatedImages.push(imageWithMetadata);
            fragment.appendChild(this.createImageElement(imageWithMetadata));
        });

        this.elements.imageGrid.insertBefore(fragment, this.elements.imageGrid.firstChild);
    }

    createImageElement(image) {
        const imageElement = document.createElement('div');
        imageElement.className = 'image-item';

        const imgElement = document.createElement('img');
        imgElement.src = image.url;
        imgElement.alt = image.prompt || 'Generated image';

        const promptElement = document.createElement('div');
        promptElement.className = 'image-prompt';
        promptElement.textContent = image.prompt || '';

        imageElement.appendChild(imgElement);
        imageElement.appendChild(promptElement);

        imageElement.addEventListener('click', () => {
            const index = this.state.generatedImages.findIndex(img => img.url === image.url);
            if (index !== -1) {
                this.showImagePreview(index);
            }
        });

        return imageElement;
    }

    showImagePreview(index) {
        if (!this.state.generatedImages?.[index]) return;

        const modalRoot = document.getElementById('previewModalRoot');
        if (!modalRoot) return;

        ReactDOM.createRoot(modalRoot).render(
            React.createElement(ImagePreviewModal, {
                images: this.state.generatedImages,
                initialIndex: index,
                onClose: () => {
                    ReactDOM.createRoot(modalRoot).unmount();
                }
            })
        );
    }

    async fetchModelInfo() {
        try {
            const response = await fetch(API_ENDPOINTS.MODEL_INFO);
            const data = await response.json();

            this.state.model = data.model;
            this.state.settings = {
                ...this.state.settings,
                model: data.model
            };

            return data;
        } catch (error) {
            console.error('Error fetching model info:', error);
            throw error;
        }
    }

    initializeSettings() {
        const batchSize = document.getElementById('batchSize')?.value;
        const seedValue = document.getElementById('seedValue')?.value;

        return {
            ...DEFAULT_SETTINGS,
            batchSize: batchSize ? parseInt(batchSize) : DEFAULT_SETTINGS.batchSize,
            seed: seedValue ? parseInt(seedValue) : DEFAULT_SETTINGS.seed,
            model: this.state.model || DEFAULT_SETTINGS.model,
        };
    }

    initializeSettingsPanel() {
        const settingsPanelRoot = document.getElementById('settingsPanelRoot');
        if (!settingsPanelRoot) return;

        ReactDOM.createRoot(settingsPanelRoot).render(
            React.createElement(SettingsPanel, {
                initialSettings: {
                    ...this.state.settings,
                    model: this.state.model
                },
                onSettingsChange: this.handleSettingsChange.bind(this)
            })
        );
    }

    loadSavedImages() {
        if (typeof saved_images === 'undefined') return;

        this.state.generatedImages = saved_images;
        const fragment = document.createDocumentFragment();

        saved_images.forEach(image => {
            fragment.appendChild(this.createImageElement(image));
        });

        this.elements.imageGrid.appendChild(fragment);
    }

    showLoading(show) {
        if (this.elements.loadingIndicator) {
            this.elements.loadingIndicator.style.display = show ? 'block' : 'none';
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new ImageGenerator();
});
