from PIL import Image

def what(file, h=None):
    try:
        img = Image.open(file)
        return img.format.lower()
    except Exception:
        return None
