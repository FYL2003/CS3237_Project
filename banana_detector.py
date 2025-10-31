import cv2
import numpy as np

# returns (visual: img, meanRGB: int tuple)
def detect_banana_and_avg_color(img):
    vis = img.copy()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hsv = cv2.GaussianBlur(hsv, (7, 7), 0)

    # yellow banana
    lower_yellow = np.array([10, 60, 60])
    upper_yellow = np.array([35, 255, 255])
    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)

    # lower threshold for browner/darker banana
    lower_yellow2 = np.array([8, 40, 40])
    upper_yellow2 = np.array([40, 255, 255])
    mask_yellow = cv2.bitwise_or(mask_yellow, cv2.inRange(hsv, lower_yellow2, upper_yellow2))

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask_yellow, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)

    # Find contours and pick the largest
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return vis, None

    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    banana_cnt = contours[0]
    if cv2.contourArea(banana_cnt) < 500:
        return vis, None

    # Create mask for chosen contour
    banana_mask = np.zeros(mask.shape, dtype=np.uint8)
    cv2.drawContours(banana_mask, [banana_cnt], -1, 255, thickness=-1)

    # Compute average color inside banana mask
    mean_bgr = cv2.mean(img, mask=banana_mask)[:3]
    mean_bgr = tuple(int(round(c)) for c in mean_bgr)
    mean_rgb = (mean_bgr[2], mean_bgr[1], mean_bgr[0])

    # Draw bounding box for the banana
    cv2.drawContours(vis, [banana_cnt], -1, (0, 255, 0), 3)
    x, y, w, h = cv2.boundingRect(banana_cnt)
    cv2.rectangle(vis, (x, y), (x + w, y + h), (255, 0, 0), 2)

    # label the average RGB
    text = f"Avg RGB: {mean_rgb}"
    cv2.putText(vis, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)

    return vis, mean_rgb

def detect_banana_and_avg_color_from_path(image_path: str):
    img = cv2.imread(image_path)
    return detect_banana_and_avg_color(img)

if __name__ == "__main__":
    image_path = "test_imgs/IMG_7173.JPG"
    detected_img, avg_rgb = detect_banana_and_avg_color_from_path(image_path)
    if avg_rgb is None:
        print("No banana detected.")
    else:
        print("Average banana color (R,G,B):", avg_rgb)
    cv2.imwrite("banana_detected.png", detected_img)
