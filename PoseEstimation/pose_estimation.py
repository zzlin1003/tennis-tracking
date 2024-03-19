import cv2

def draw_circle_using_landmark(img,landmarks,pose_id):
  lm = landmarks[pose_id]
  h, w, c = img.shape
  cx, cy = int(lm.x * w), int(lm.y * h)

  cv2.circle(img, (cx,cy),5, (255,255,0), cv2.FILLED)