// Constants
const DEFAULT_SETTINGS = {
    batchSize: 1,
    seed: '',
    guidanceScale: 7.5,
    num_inference_steps: 50,
    negativePrompt: ''
};

const API_ENDPOINTS = {
    UPLOAD: '/upload',
    GENERATE: '/generate',
    MODEL_INFO: '/model-info'
};

class ImageGenerator {
    constructor() {
        this.state = {
            isGenerating: false,
            generatedImages: [],
            sourceImage: null,
            model: null,
            settings: this.initializeSettings()
        };

        this.elements = this.initializeElements();
        this.initializeApp();
    }

    initializeSettings() {
        const batchSize = document.getElementById('batchSize')?.value;
        const seedValue = document.getElementById('seedValue')?.value;

        return {
            ...DEFAULT_SETTINGS,
            batchSize: batchSize ? parseInt(batchSize) : DEFAULT_SETTINGS.batchSize,
            seed: seedValue ? parseInt(seedValue) : DEFAULT_SETTINGS.seed
        };
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

        // Validate elements
        Object.entries(elements).forEach(([key, element]) => {
            if (!element) {
                console.error(`Required element not found: ${key}`);
            }
        });

        elements.sourceImagePreview.className = 'source-image-preview';
        elements.dropZone.appendChild(elements.sourceImagePreview);

        return elements;
    }

    initializeApp() {
        this.initializeSettingsPanel();
        this.setupEventListeners();
        this.loadSavedImages();
        this.fetchModelInfo();
    }

    initializeSettingsPanel() {
        const settingsPanelRoot = document.getElementById('settingsPanelRoot');
        if (!settingsPanelRoot) return;

        ReactDOM.createRoot(settingsPanelRoot).render(
            React.createElement(SettingsPanel, {
                initialSettings: this.state.settings,
                onSettingsChange: this.handleSettingsChange.bind(this)
            })
        );
    }

    handleSettingsChange(newSettings) {
        this.state.settings = {
            ...this.state.settings,
            ...newSettings
        };
    }

    setupEventListeners() {
        // Generate button events.
        this.elements.generateBtn.addEventListener('click', this.handleGenerate.bind(this));
        this.elements.promptInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleGenerate();
            }
        });

        // Batch size input.
        this.elements.batchSizeInput?.addEventListener('change', (e) => {
            const value = Math.max(1, Math.min(4, parseInt(e.target.value) || 1));
            e.target.value = value;
            this.handleSettingsChange({ batchSize: value });
        });

        // Seed input.
        this.elements.seedInput?.addEventListener('change', (e) => {
            const value = parseInt(e.target.value) || '';
            this.handleSettingsChange({ seed: value });
        });

        this.setupFileUploadListeners();
    }

    setupFileUploadListeners() {
        const { dropZone, fileInput } = this.elements;

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
            this.showLoading(true);
            this.elements.generateBtn.disabled = true;

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
                    image: this.state.sourceImage
                })
            });

            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error || 'Generation failed');
            }

            this.addGeneratedImages(data.images);
        } catch (error) {
            console.error('Generation error:', error);
            alert('Failed to generate images: ' + error.message);
        } finally {
            this.state.isGenerating = false;
            this.showLoading(false);
            this.elements.generateBtn.disabled = false;
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
        } catch (error) {
            console.error('Error fetching model info:', error);
        }
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
        this.elements.loadingIndicator.style.display = show ? 'block' : 'none';
    }
}

// Initialize app when DOM is ready...
document.addEventListener('DOMContentLoaded', () => {
    window.app = new ImageGenerator();
});
