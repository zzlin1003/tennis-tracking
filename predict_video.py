import argparse
import queue
import pandas as pd 
import pickle
import imutils
import os
from PIL import Image, ImageDraw
import cv2 
import numpy as np
import torch
import sys
import time

from sktime.datatypes._panel._convert import from_2d_array_to_nested
# (change2) add 'line_intersection' method
from court_detector import CourtDetector, line_intersection
from Models.tracknet import trackNet
from TrackPlayers.trackplayers import *
# # (change3) add this line
# from TrackRackets.trackrackets import *
# (change4) import mediapipe and PoseEstimation
import mediapipe as mp
from PoseEstimation.pose_estimation import draw_circle_using_landmark

from utils import get_video_properties, get_dtype
from detection import *
from pickle import load


# parse parameters
parser = argparse.ArgumentParser()

parser.add_argument("--input_video_path", type=str)
parser.add_argument("--output_video_path", type=str, default="")
parser.add_argument("--minimap", type=int, default=0)
parser.add_argument("--bounce", type=int, default=0)

args = parser.parse_args()

input_video_path = args.input_video_path
output_video_path = args.output_video_path
minimap = args.minimap
bounce = args.bounce

n_classes = 256
# (change)
save_weights_path = 'WeightsTracknet/model.h5'

yolo_classes = 'Yolov3/yolov3.txt'
yolo_weights = 'Yolov3/yolov3.weights'
yolo_config = 'Yolov3/yolov3.cfg'

if output_video_path == "":
    # output video in same path
    output_video_path = input_video_path.split('.')[0] + "VideoOutput/video_output.mp4"

# get video fps&video size
video = cv2.VideoCapture(input_video_path)
fps = int(video.get(cv2.CAP_PROP_FPS))
print('fps : {}'.format(fps))
output_width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
output_height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))

# try to determine the total number of frames in the video file
if imutils.is_cv2() is True :
    prop = cv2.cv.CV_CAP_PROP_FRAME_COUNT
else : 
    prop = cv2.CAP_PROP_FRAME_COUNT
total = int(video.get(prop))

# start from first frame
currentFrame = 0

# width and height in TrackNet
width, height = 640, 360
img, img1, img2 = None, None, None

# load TrackNet model
modelFN = trackNet
m = modelFN(n_classes, input_height=height, input_width=width)
m.compile(loss='categorical_crossentropy', optimizer='adadelta', metrics=['accuracy'])
m.load_weights(save_weights_path)

# In order to draw the trajectory of tennis, we need to save the coordinate of previous 7 frames
q = queue.deque()
for i in range(0, 8):
    q.appendleft(None)

# save prediction images as videos
fourcc = cv2.VideoWriter_fourcc(*'XVID')
output_video = cv2.VideoWriter(output_video_path, fourcc, fps, (output_width, output_height))

# # load yolov3 labels
# # (change3)
# yolo_net, classes, _, output_layers = load_yolo(yolo_weights,
#                                                 yolo_config,
#                                                 yolo_classes)
# LABELS = open(yolo_classes).read().strip().split("\n")
# # yolo net
# net = cv2.dnn.readNet(yolo_weights, yolo_config) 


# court
court_detector = CourtDetector()

# players tracker
dtype = get_dtype()
detection_model = DetectionModel(dtype=dtype)

# get videos properties
fps, length, v_width, v_height = get_video_properties(video)

frame_i = 0
frames = []

while True:
  ret, frame = video.read()
  frame_i += 1

  if ret:
    if frame_i == 1:
      print('Detecting the court and the players...')
      lines = court_detector.detect(frame)
    else: # then track it
      lines = court_detector.track_court(frame)
    detection_model.detect_player_1(frame, court_detector)
    detection_model.detect_top_persons(frame, court_detector, frame_i)
    
    for i in range(0, len(lines), 4):
      x1, y1, x2, y2 = lines[i],lines[i+1], lines[i+2], lines[i+3]
      cv2.line(frame, (int(x1),int(y1)),(int(x2),int(y2)), (0,0,255), 2)

    # --- (change2) draw key court reference points ---
    def helper(input_line):
      return ((input_line[0],input_line[1]),(input_line[2],input_line[3]))

    def get_intersection_pt(line1,line2):
      pt = line_intersection(line1,line2)
      return tuple(map(int,pt))

    baseline_top = helper(lines[:4])
    baseline_bottom = helper(lines[4:8])
    net = helper(lines[8:12])
    left_court_line = helper(lines[12:16])
    right_court_line = helper(lines[16:20])
    left_inner_line = helper(lines[20:24])
    right_inner_line = helper(lines[24:28])
    middle_line = helper(lines[28:32])
    top_inner_line = helper(lines[32:36])
    bottom_inner_line = helper(lines[36:40])

    top_left_outer_pt = get_intersection_pt(baseline_top,left_court_line)
    top_left_inner_pt = get_intersection_pt(baseline_top,left_inner_line)
    top_middle_pt = get_intersection_pt(baseline_top,middle_line)
    top_right_inner_pt = get_intersection_pt(baseline_top,right_inner_line)
    top_right_outer_pt = get_intersection_pt(baseline_top,right_court_line)
    top_serve_left_pt = get_intersection_pt(top_inner_line,left_inner_line)
    top_serve_middle_pt = get_intersection_pt(top_inner_line,middle_line)
    top_serve_right_pt = get_intersection_pt(top_inner_line,right_inner_line)
    
    bottom_left_outer_pt = get_intersection_pt(baseline_bottom,left_court_line)
    bottom_left_inner_pt = get_intersection_pt(baseline_bottom,left_inner_line)
    bottom_middle_pt = get_intersection_pt(baseline_bottom,middle_line)
    bottom_right_inner_pt = get_intersection_pt(baseline_bottom,right_inner_line)
    bottom_right_outer_pt = get_intersection_pt(baseline_bottom,right_court_line)
    bottom_serve_left_pt = get_intersection_pt(bottom_inner_line,left_inner_line)
    bottom_serve_middle_pt = get_intersection_pt(bottom_inner_line,middle_line)
    bottom_serve_right_pt = get_intersection_pt(bottom_inner_line,right_inner_line)

    ref_pts = {'tlo': top_left_outer_pt,
               'tli': top_left_inner_pt,
               'tm': top_middle_pt,
               'tri': top_right_inner_pt,
               'tro': top_right_outer_pt,
               'tsl': top_serve_left_pt,
               'tsm': top_serve_middle_pt,
               'tsr': top_serve_right_pt,
               'blo': bottom_left_outer_pt,
               'bli': bottom_left_inner_pt,
               'bm': bottom_middle_pt,
               'bri': bottom_right_inner_pt,
               'bro': bottom_right_outer_pt,
               'bsl': bottom_serve_left_pt,
               'bsm': bottom_serve_middle_pt,
               'bsr': bottom_serve_right_pt}
    # not drawing circles here; avoid distracting ball detection
    # for key, val in ref_pts.items():
    #   cv2.circle(frame,val,2,(0,255,0),5)
    #   cv2.putText(frame,f"{key}",val,cv2.FONT_HERSHEY_SIMPLEX,1,(255,0,0),2,cv2.LINE_AA)
    # --- (change2 end) ---
    # # --- (change3) draw rectangles around the racket of player 1
    # frame = cv2.resize(frame,None,fx=0.4,fy=0.4)
    # height, width, channels = frame.shape

    # blobs, outputs = detect_objects(frame,yolo_net,output_layers)
    # boxes, confs, class_ids = get_box_dimensions(outputs, height, width)
    # frame = draw_one_label(boxes, confs,(255,0,0),class_ids, classes, frame, obj_name="tennis racket")
    # # --- (change3 end)
    new_frame = cv2.resize(frame, (v_width, v_height))
    frames.append(new_frame)
  else:
    break
video.release()
print('Finished!')

detection_model.find_player_2_box()

# second part 
player1_boxes = detection_model.player_1_boxes
player2_boxes = detection_model.player_2_boxes

# (change4) add pose estimation object
mpPose = mp.solutions.pose
pose = mpPose.Pose()
mpDraw = mp.solutions.drawing_utils
dominant_hand = "right"

video = cv2.VideoCapture(input_video_path)
frame_i = 0
coords = []
t = []

# # --- (change5) use previous position as the current prediction ---
# dt = 1
# sigma = 1
# state_dim = 4
# kf = cv2.KalmanFilter(state_dim,2)
# kf.measurementMatrix = np.array([[1,0,0,0],[0,1,0,0]],np.float32)
# kf.transitionMatrix = np.array([[1,0,dt,0],[0,1,0,dt],[0,0,1,0],[0,0,0,1]],np.float32)
# kf.processNoiseCov = np.eye(state_dim,dtype=np.float32) * sigma
ball_coords_cur_pred = [0,0]
# # --- change5 ends ---

last = time.time() # start counting 
# while (True):
for img in frames:
    print('Tracking the ball: {}'.format(round( (currentFrame / total) * 100, 2)))
    frame_i += 1

    # detect the ball
    # img is the frame that TrackNet will predict the position
    # since we need to change the size and type of img, copy it to output_img
    output_img = img

    # resize it
    img = cv2.resize(img, (width, height))
    # input must be float type
    img = img.astype(np.float32)

    # since the odering of TrackNet  is 'channels_first', so we need to change the axis
    X = np.rollaxis(img, 2, 0)
    # prdict heatmap
    pr = m.predict(np.array([X]))[0]

    # since TrackNet output is ( net_output_height*model_output_width , n_classes )
    # so we need to reshape image as ( net_output_height, model_output_width , n_classes(depth) )
    pr = pr.reshape((height, width, n_classes)).argmax(axis=2)

    # cv2 image must be numpy.uint8, convert numpy.int64 to numpy.uint8
    pr = pr.astype(np.uint8)

    # reshape the image size as original input image
    heatmap = cv2.resize(pr, (output_width, output_height))

    # heatmap is converted into a binary image by threshold method.
    ret, heatmap = cv2.threshold(heatmap, 127, 255, cv2.THRESH_BINARY)

    # find the circle in image with 2<=radius<=7
    circles = cv2.HoughCircles(heatmap, cv2.HOUGH_GRADIENT, dp=1, minDist=1, param1=50, param2=2, minRadius=2,
                              maxRadius=7)

    # (change4) fix the BUG: currentFrame-1 -> currentFrame
    output_img = mark_player_box(output_img, player1_boxes, currentFrame)
    output_img = mark_player_box(output_img, player2_boxes, currentFrame)
    # --- (change4) draw pose estimation landmark on the frame
    # the reason for cropping the image is to estimate pose on specific player
    # TODO: analyze opponents
    player_1_box = player1_boxes[currentFrame]
    img_player_1_crop = output_img[int(player_1_box[1]):int(player_1_box[3]),
                                   int(player_1_box[0]):int(player_1_box[2])]
    
    imgRGB = cv2.cvtColor(img_player_1_crop, cv2.COLOR_BGR2RGB)
    results = pose.process(imgRGB)
    if results.pose_landmarks is not None:
      if dominant_hand == "right":
        draw_circle_using_landmark(img_player_1_crop,
                                  results.pose_landmarks.landmark,
                                  pose_id=16, # right wrist
                                  ) 
      else: # TODO: consider lefty
        pass
    # --- (end change4)

    # check if there have any tennis be detected
    if circles is not None and len(circles) == 1:
      x = int(circles[0][0][0])
      y = int(circles[0][0][1])
    else:
      x = ball_coords_cur_pred[0]
      y = ball_coords_cur_pred[1]

    coords.append([x,y])
    t.append(time.time()-last)
    # push x,y to queue
    q.appendleft([x, y])
    # pop x,y from queue
    q.pop()

    cv2.circle(output_img,(x,y),2,(0,0,255),5)
    ball_coords_cur_pred = [x,y]

    PIL_image = cv2.cvtColor(output_img, cv2.COLOR_BGR2RGB)
    PIL_image = Image.fromarray(PIL_image)

    # draw current frame prediction and previous 7 frames as yellow circle, total: 8 frames
    for i in range(0, 8):
        if q[i] is not None:
            draw_x = q[i][0]
            draw_y = q[i][1]
            bbox = (draw_x - 2, draw_y - 2, draw_x + 2, draw_y + 2)
            draw = ImageDraw.Draw(PIL_image)
            draw.ellipse(bbox, outline='yellow')
            del draw

    # Convert PIL image format back to opencv image format
    opencvImage = cv2.cvtColor(np.array(PIL_image), cv2.COLOR_RGB2BGR)

    output_video.write(opencvImage)

    # next frame
    currentFrame += 1

# everything is done, release the video
video.release()
output_video.release()

if minimap == 1:
  game_video = cv2.VideoCapture(output_video_path)

  fps1 = int(game_video.get(cv2.CAP_PROP_FPS))

  output_width = int(game_video.get(cv2.CAP_PROP_FRAME_WIDTH))
  output_height = int(game_video.get(cv2.CAP_PROP_FRAME_HEIGHT))
  print('game ', fps1)
  output_video = cv2.VideoWriter('VideoOutput/video_with_map.mp4', fourcc, fps, (output_width, output_height))
  
  print('Adding the mini-map...')

  # Remove Outliers 
  x, y = diff_xy(coords)
  remove_outliers(x, y, coords)
  # Interpolation
  coords = interpolation(coords)
  create_top_view(court_detector, detection_model, coords, fps)
  minimap_video = cv2.VideoCapture('VideoOutput/minimap.mp4')
  fps2 = int(minimap_video.get(cv2.CAP_PROP_FPS))
  print('minimap ', fps2)
  while True:
    ret, frame = game_video.read()
    ret2, img = minimap_video.read()
    if ret:
      output = merge(frame, img)
      output_video.write(output)
    else:
      break
  game_video.release()
  minimap_video.release()

output_video.release()

for _ in range(3):
  x, y = diff_xy(coords)
  remove_outliers(x, y, coords)

# interpolation
coords = interpolation(coords)

# velocty 
Vx = []
Vy = []
V = []
frames = [*range(len(coords))]

for i in range(len(coords)-1):
  p1 = coords[i]
  p2 = coords[i+1]
  t1 = t[i]
  t2 = t[i+1]
  x = (p1[0]-p2[0])/(t1-t2)
  y = (p1[1]-p2[1])/(t1-t2)
  Vx.append(x)
  Vy.append(y)

for i in range(len(Vx)):
  vx = Vx[i]
  vy = Vy[i]
  v = (vx**2+vy**2)**0.5
  V.append(v)

xy = coords[:]

if bounce == 1:
  # Predicting Bounces 
  test_df = pd.DataFrame({'x': [coord[0] for coord in xy[:-1]], 'y':[coord[1] for coord in xy[:-1]], 'V': V})

  # df.shift
  for i in range(20, 0, -1): 
    test_df[f'lagX_{i}'] = test_df['x'].shift(i, fill_value=0)
  for i in range(20, 0, -1): 
    test_df[f'lagY_{i}'] = test_df['y'].shift(i, fill_value=0)
  for i in range(20, 0, -1): 
    test_df[f'lagV_{i}'] = test_df['V'].shift(i, fill_value=0)

  test_df.drop(['x', 'y', 'V'], 1, inplace=True)

  Xs = test_df[['lagX_20', 'lagX_19', 'lagX_18', 'lagX_17', 'lagX_16',
        'lagX_15', 'lagX_14', 'lagX_13', 'lagX_12', 'lagX_11', 'lagX_10',
        'lagX_9', 'lagX_8', 'lagX_7', 'lagX_6', 'lagX_5', 'lagX_4', 'lagX_3',
        'lagX_2', 'lagX_1']]
  Xs = from_2d_array_to_nested(Xs.to_numpy())

  Ys = test_df[['lagY_20', 'lagY_19', 'lagY_18', 'lagY_17',
        'lagY_16', 'lagY_15', 'lagY_14', 'lagY_13', 'lagY_12', 'lagY_11',
        'lagY_10', 'lagY_9', 'lagY_8', 'lagY_7', 'lagY_6', 'lagY_5', 'lagY_4',
        'lagY_3', 'lagY_2', 'lagY_1']]
  Ys = from_2d_array_to_nested(Ys.to_numpy())

  Vs = test_df[['lagV_20', 'lagV_19', 'lagV_18',
        'lagV_17', 'lagV_16', 'lagV_15', 'lagV_14', 'lagV_13', 'lagV_12',
        'lagV_11', 'lagV_10', 'lagV_9', 'lagV_8', 'lagV_7', 'lagV_6', 'lagV_5',
        'lagV_4', 'lagV_3', 'lagV_2', 'lagV_1']]
  Vs = from_2d_array_to_nested(Vs.to_numpy())

  X = pd.concat([Xs, Ys, Vs], 1)

  # load the pre-trained classifier  
  clf = load(open('clf.pkl', 'rb'))

  predcted = clf.predict(X)
  idx = list(np.where(predcted == 1)[0])
  idx = np.array(idx) - 10
  
  if minimap == 1:
    video = cv2.VideoCapture('VideoOutput/video_with_map.mp4')
  else:
    video = cv2.VideoCapture(output_video_path)

  output_width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
  output_height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
  fps = int(video.get(cv2.CAP_PROP_FPS))
  length = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
  fourcc = cv2.VideoWriter_fourcc(*'XVID')

  print(fps)
  print(length)

  output_video = cv2.VideoWriter('VideoOutput/final_video.mp4', fourcc, fps, (output_width, output_height))
  i = 0
  while True:
    ret, frame = video.read()
    if ret:
      # if coords[i] is not None:
      if i in idx:
        center_coordinates = int(xy[i][0]), int(xy[i][1])
        radius = 3
        color = (255, 0, 0)
        thickness = -1
        cv2.circle(frame, center_coordinates, 10, color, thickness)
      i += 1
      output_video.write(frame)
    else:
      break

  video.release()
  output_video.release()
