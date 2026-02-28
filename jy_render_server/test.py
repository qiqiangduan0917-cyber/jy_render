import pyautogui
from PIL import Image
img = pyautogui.screenshot()
img.save("screen.png")
import os
print("当前工作目录:", os.getcwd())
# 模板路径
template_path = "templates/.png"

# 匹配
location = pyautogui.locateOnScreen(
    template_path,
    confidence=0.8   # 需要cv2
)

if location:
    print("找到位置:", location)

    center = pyautogui.center(location)
    print("中心点:", center)

    pyautogui.click(center)
else:
    print("没找到")