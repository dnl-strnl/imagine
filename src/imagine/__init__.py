from PIL.PngImagePlugin import PngInfo

def save_with_metadata(image_path, output_path, metadata=dict()):
    # Open the image
    img = Image.open(image_path)

    # Create a PngInfo object to store the metadata
    metadata = PngInfo()

    # Add the prompt text as metadata
    metadata.add_text("prompt", prompt_text)

    # Save the image with the embedded metadata
    img.save(output_path, "PNG", pnginfo=metadata)
