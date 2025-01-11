// State management.
const state = {
    isGenerating: false,
    generatedImages: [],
    sourceImage: null,
    model: null
};

// DOM Elements.
const elements = {
    promptInput: document.getElementById('promptInput'),
    generateBtn: document.getElementById('generateBtn'),
    dropZone: document.getElementById('dropZone'),
    fileInput: document.getElementById('fileInput'),
    imageGrid: document.getElementById('imageGrid'),
    loadingIndicator: document.getElementById('loadingIndicator'),
    sourceImagePreview: document.createElement('div')
};

// Initialize source image preview.
elements.sourceImagePreview.className = 'source-image-preview';
elements.dropZone.appendChild(elements.sourceImagePreview);

// Validate all elements are found.
Object.entries(elements).forEach(([key, element]) => {
    if (!element) {
        console.error(`Element not found: ${key}`);
    }
});

// Logging utility.
const logger = {
    info: (message, data) => {
        console.log(`[INFO] ${message}`, data || '');
        console.trace();
    },
    error: (message, error) => {
        console.error(`[ERROR] ${message}`, error);
        console.trace();
    },
    debug: (message, data) => {
        console.debug(`[DEBUG] ${message}`, data || '');
    }
};

// Load saved images from server-side rendered data.
function loadSavedImages() {
    // Assumes the server is providing the `saved_images` data in a script tag.
    if (typeof saved_images !== 'undefined') {
        state.generatedImages = saved_images;

        const fragment = document.createDocumentFragment();
        saved_images.forEach(image => {
            const imageElement = createImageElement(image);
            fragment.appendChild(imageElement);
        });

        elements.imageGrid.appendChild(fragment);
    }
}

function createImageElement(image) {
    const imageElement = document.createElement('div');
    imageElement.className = 'image-item';

    const imgElement = document.createElement('img');
    imgElement.src = image.url;
    imgElement.alt = image.prompt || 'Generated image';

    imageElement.addEventListener('click', () => {
        const index = state.generatedImages.findIndex(img => img.url === image.url);
        if (index !== -1) {
            showImagePreview(index);
        }
    });

    const promptElement = document.createElement('div');
    promptElement.className = 'image-prompt';
    promptElement.textContent = image.prompt || '';

    imageElement.appendChild(imgElement);
    imageElement.appendChild(promptElement);
    return imageElement;
}

async function generateImages() {
    if (state.isGenerating) {
        console.debug('Generation already in progress...');
        return;
    }

    const prompt = elements.promptInput.value.trim();
    const batchSize = Math.max(1, Math.min(4,
        parseInt(document.getElementById('batchSize').value) || 1)
    );
    const seedValue = document.getElementById('seedValue').value;

    if (!prompt) {
        alert('Please enter a prompt!');
        return;
    }

    try {
        state.isGenerating = true;
        elements.loadingIndicator.style.display = 'block';

        const response = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prompt: prompt,
                batch_size: batchSize,
                seed: parseInt(seedValue),
                model: state.model,
                image: state.sourceImage
            })
        });

        const data = await response.json();

        if (data.success) {
            const fragment = document.createDocumentFragment();

            data.images.forEach(image => {
                const imageWithModel = {
                    ...image,
                    model: state.model
                };
                state.generatedImages.unshift(imageWithModel);
                const imageElement = createImageElement(imageWithModel);
                fragment.appendChild(imageElement);
            });

            elements.imageGrid.insertBefore(fragment, elements.imageGrid.firstChild);
        } else {
            throw new Error(data.error);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to generate images: ' + error.message);
    } finally {
        state.isGenerating = false;
        elements.loadingIndicator.style.display = 'none';
    }
}

async function handleImageUpload(file) {
    logger.debug('Handling image upload:', file.name);
    elements.loadingIndicator.style.display = 'block';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        logger.debug('Upload response:', data);

        if (data.success) {
            logger.info('Image uploaded successfully:', data.filename);
            state.sourceImage = data.filename;
            updateSourceImagePreview(file);
        } else {
            throw new Error(data.error || 'Upload failed.');
        }
    } catch (error) {
        logger.error('Error uploading image:', error);
        clearSourceImage();
    } finally {
        elements.loadingIndicator.style.display = 'none';
    }
}

function updateSourceImagePreview(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        elements.sourceImagePreview.innerHTML = `
            <div class="preview-container">
                <img src="${e.target.result}" alt="Source image">
                <button class="remove-btn" onclick="clearSourceImage()">×</button>
            </div>
        `;
        elements.dropZone.classList.add('has-image');
    };
    reader.readAsDataURL(file);
}

function clearSourceImage() {
    state.sourceImage = null;
    elements.sourceImagePreview.innerHTML = '';
    elements.dropZone.classList.remove('has-image');
    elements.fileInput.value = '';
}

function showImagePreview(index) {
    if (!state.generatedImages || !state.generatedImages[index]) {
        logger.error('Invalid image index.');
        return;
    }

    const modalRoot = document.getElementById('previewModalRoot');
    if (!modalRoot) return;

    const root = ReactDOM.createRoot(modalRoot);
    root.render(
        React.createElement(ImagePreviewModal, {
            images: state.generatedImages,
            initialIndex: index,
            onClose: () => {
                root.unmount();
            }
        })
    );
}

async function fetchModelInfo() {
    try {
        const response = await fetch('/model-info');
        const data = await response.json();
        state.model = data.model;
    } catch (error) {
        logger.error('Error fetching model info:', error);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadSavedImages();
    fetchModelInfo();
    const generateBtn = document.getElementById('generateBtn');
    generateBtn.addEventListener('click', (e) => {
        e.preventDefault();
        generateImages();
    });
});
