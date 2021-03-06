import platform
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from subprocess import run
import base64
import io
import importlib
import warnings


def get_system():
    system = platform.system().lower()
    if system in ['darwin', 'linux', 'windows']:
        return system
    else:
        raise OSError(f"Unsupported OS - {system}")


def get_chrome_path(chrome_path=None):
    system = get_system()
    if chrome_path:
        return chrome_path

    if system == "darwin":
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
        for path in paths:
            if Path(path).exists():
                return path
        raise OSError("Chrome executable not able to be found on your machine")
    elif system == "linux":
        paths = [
            None,
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
            "/sbin",
            "/bin",
            "/opt/google/chrome",
        ]
        commands = ["google-chrome", "chrome", "chromium", "chromium-browser", "brave-browser"]
        for path in paths:
            for cmd in commands:
                chrome_path = shutil.which(cmd, path=path)
                if chrome_path:
                    return chrome_path
        raise OSError("Chrome executable not able to be found on your machine")
    elif system == "windows":
        import winreg
        locs = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\brave.exe",
        ]
        for loc in locs:
            handle = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, loc)
            num_values = winreg.QueryInfoKey(handle)[1]
            if num_values > 0:
                return winreg.EnumValue(handle, 0)[1]
        raise OSError("Cannot find chrome.exe on your windows machine")


class Screenshot:

    def __init__(self, max_rows, max_cols, ss_width, ss_height, resize, chrome_path):
        self.max_rows = max_rows
        self.max_cols = max_cols
        self.ss_width = ss_width
        self.ss_height = ss_height
        self.resize = resize
        self.chrome_path = get_chrome_path(chrome_path)
        self.css = self.get_css()

    def get_css(self):
        mod_dir = Path(__file__).resolve().parent
        css_file = mod_dir / "static" / "style.css"
        with open(css_file) as f:
            css = "<style>" + f.read() + "</style>"
        return css

    def take_screenshot(self, html):
        temp_dir = TemporaryDirectory()
        temp_html = Path(temp_dir.name) / "temp.html"
        temp_img = Path(temp_dir.name) / "temp.png"
        open(temp_html, "w").write(html)
        open(temp_img, "wb")            

        args = [
            "--enable-logging",
            "--disable-gpu",
            "--headless",
            f"--window-size={self.ss_width},{self.ss_height}",
            "--hide-scrollbars",
            f"--screenshot={str(temp_img)}",
            str(temp_html),
        ]
        run(executable=self.chrome_path, args=args)
        img_bytes = open(temp_img, 'rb').read()
        buffer = io.BytesIO(img_bytes)
        return buffer

    def finalize_image(self, buffer):
        from PIL import Image, ImageChops

        img = Image.open(buffer)
        img_gray = img.convert('L')
        bg = Image.new('L', img.size, 255)
        diff = ImageChops.difference(img_gray, bg)
        diff = ImageChops.add(diff, diff, 2.0, -100)
        bbox = diff.getbbox()
        new_y_max = bbox[-1] + 10
        x_max = img.size[0]
        img = img.crop((0, 0, x_max, new_y_max))

        if self.resize != 1:
            w, h = img.size
            w, h = int(w // self.resize), int(h // self.resize)
            img = img.resize((w, h), Image.ANTIALIAS)
        return img

    def save_image(self, img):
        buffer = io.BytesIO()
        img.save(buffer, format="png", quality=95)
        return buffer

    def get_base64_image_str(self, buffer):
        return base64.b64encode(buffer.getvalue()).decode()

    def run(self, html):
        buffer = self.take_screenshot(html)
        
        if importlib.util.find_spec('PIL'):
            img = self.finalize_image(buffer)
            buffer = self.save_image(img)
        else:
            warnings.warn('The pillow library is not installed. Unable to crop table images. '
                          'Install it so that the white space around tables gets removed.')
        img_str = self.get_base64_image_str(buffer)
        return img_str

    def repr_png_wrapper(self):
        def _repr_png_(data):
            html = self.css + data
            return self.run(html)
        return _repr_png_

def make_repr_png(max_rows=30, max_cols=10, ss_width=1000, ss_height=900, 
                  resize=1, chrome_path=None):
    """
    Creates a function that can be assigned to `pd.DataFrame._repr_png_` 
    so that you can test out the appearances of the images in a notebook 
    before you convert.

    >>> import pandas as pd
    >>> from dataframe_image import repr_png_maker
    >>> pd.DataFrame._repr_png_ = repr_png_maker() # pass desired arguments
    >>> df = pd.DataFrame({'a': [1, 5, 6]})
    >>> from IPython.display import display_png
    >>> display_png(df)

    There is no need to use this function in the notebook that you want to 
    convert to pdf or markdown. Use `dataframe_image.convert` in a separate 
    script for that.

    Parameters
    ----------
    max_rows : int, default 30
        Maximum number of rows to output from DataFrame. This is forwarded to 
        the `to_html` DataFrame method.

    max_cols : int, default 10
        Maximum number of columns to output from DataFrame. This is forwarded 
        to the `to_html` DataFrame method.

    ss_width : int, default 1000
        Width of the screenshot. This may need to be increased for larger 
        monitors. If this value is too small, then smaller DataFrames will 
        appear larger. It's best to keep this value at least as large as the 
        width of the output section of a Jupyter Notebook.

    ss_height : int, default 900
        Height of the screen shot. The height of the image is automatically 
        cropped so that only the relevant parts of the DataFrame are shown.

    resize : int or float, default 1
        Relative resizing of image. Higher numbers produce smaller images. 
        The Pillow `Image.resize` method is used for this.

    chrome_path : str, default None
        Path to your machine's chrome executable. When `None`, it is 
        automatically found. Use this when chrome is not automatically found.
    """
    ss = Screenshot(max_rows, max_cols, ss_width, ss_height, resize, chrome_path)
    return ss.repr_png_wrapper()
