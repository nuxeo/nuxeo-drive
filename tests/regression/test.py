import pyautogui
import time
import os
import subprocess
import cv2
import numpy as np

# ----------------------------
# CONFIGURATION
# ----------------------------
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.5

CONFIDENCE = float(os.environ.get("CONFIDENCE", 0.85))
TIMEOUT = 90
CHECK_INTERVAL = 1

# IMAGE DIRECTORY PATH
IMAGE_DIR = os.path.dirname(os.path.abspath(__file__))


# ----------------------------
# UTIL FUNCTIONS
# ----------------------------

def get_image_path(image_name):
    """Return full path of image from image folder."""
    return os.path.join(IMAGE_DIR, image_name)


def wait_and_click(image_name, timeout=TIMEOUT):
    """Wait until image appears and click it."""
    print(f"Waiting for {image_name}...")

    start_time = time.time()
    image_path = get_image_path(image_name)

    while time.time() - start_time < timeout:
        try:
            location = pyautogui.locateCenterOnScreen(
                image_path,
                confidence=CONFIDENCE,
                grayscale=False,
            )
        except Exception:
            location = None

        if not location:
            try:
                location = pyautogui.locateCenterOnScreen(
                    image_path,
                    confidence=max(0.5, CONFIDENCE - 0.1),
                    grayscale=True,
                )
            except Exception:
                location = None

        if location:
            print(f"Found {image_name} at {location}, clicking...")
            pyautogui.click(location)
            return True

        try:
            loc = search_image_opencv(image_path, CONFIDENCE)
            if loc:
                print(f"OpenCV found {image_name} at {loc}, clicking...")
                pyautogui.click(loc)
                return True
        except Exception as exc:
            print(f"OpenCV fallback failed: {exc}")

        time.sleep(CHECK_INTERVAL)

    pyautogui.screenshot(os.path.join(IMAGE_DIR, f"screenshot_timeout_{image_name}.png"))

    raise FileNotFoundError(
        f"{image_name} not found within {timeout} seconds."
    )


def search_image_opencv(template_path, threshold=0.8, scales=(1.0, 0.9, 0.8, 1.1)):
    screenshot = pyautogui.screenshot()
    screen = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(f"Template image not found at {template_path}")

    th, tw = template.shape[:2]

    for scale in scales:
        try:
            resized = cv2.resize(
                template,
                (int(tw * scale), int(th * scale)),
                interpolation=cv2.INTER_AREA,
            )
        except Exception:
            continue

        if resized.shape[0] >= screen_gray.shape[0] or resized.shape[1] >= screen_gray.shape[1]:
            continue

        res = cv2.matchTemplate(screen_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            top_left = max_loc
            h, w = resized.shape[:2]
            center_x = top_left[0] + w // 2
            center_y = top_left[1] + h // 2
            return (center_x, center_y)

    return None


def wait_and_type(image_name, text):
    wait_and_click(image_name)
    pyautogui.write(text, interval=0.05)


# ----------------------------
# INSTALLATION FLOW
# ----------------------------

def launch_installer(installer_path):
    print("Launching installer.....")

    if not os.path.exists(installer_path):
        raise FileNotFoundError(f"Installer not found at '{installer_path}'")

    subprocess.Popen(installer_path)
    time.sleep(12)


def install_nuxeo():
    wait_and_click("OK.png")
    wait_and_click("I_Accept_The_Aggrement.png")
    wait_and_click("Next.png")
    time.sleep(2)
    wait_and_click("Next.png")

    wait_and_click("Install.png", timeout=TIMEOUT)

    print("Installing... please wait")
    time.sleep(15)

    wait_and_click("Finish.png", timeout=TIMEOUT)

    time.sleep(5)
    wait_and_click("Apply.png", timeout=TIMEOUT)
    time.sleep(2)

    pyautogui.press("enter")
    






    





# ----------------------------
# MAIN
# ----------------------------

if __name__ == "__main__":

    installer_path = os.environ.get(
        "INSTALLER_PATH",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "nuxeo-drive-6.0.0.exe"),
    )

    launch_installer(installer_path)
    install_nuxeo()
    