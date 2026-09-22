clear all
close all

% NORMAL Config

% Oracle bag

bag =rosbag('test_run_1-001.bag')
%%

rosbag info 'test_run_1-001.bag'

test_topic = select(bag, 'Topic','/backfly/image_raw')
test_msg_structs = readMessages(test_topic,'DataFormat','struct');
 %%
img = test_msg_structs(1)

matimg = cell2mat(img)

imshow(matimg)

%%

warty_pose_oracle = select(bag_oracle, 'Topic','/warty/pose')
warty_pose_msgStructs_oracle = readMessages(warty_pose_oracle,'DataFormat','struct');

xPoints = cellfun(@(m) double(m.Pose.Position.X),warty_pose_msgStructs_oracle);
yPoints = cellfun(@(m) double(m.Pose.Position.Y),warty_pose_msgStructs_oracle);
zPoints = cellfun(@(m) double(m.Pose.Position.Z),warty_pose_msgStructs_oracle);
plot3(xPoints,yPoints,zPoints,'LineWidth',2, 'LineStyle','--', 'Color',[0 0 0])
grid on
hold on 

title('Trajectory Plots for the Lidar-only Sensor Configurations in the NORMAL Test Case')

[arclen_oracle,seglen_oracle] = arclength(xPoints,yPoints,zPoints);

%%
% Base-configuration, multiple runs

bag_dir = 'lidar bags\lidar normal bags';
filePattern = fullfile(bag_dir, '*.bag');
theFiles = dir(filePattern);

%%

% Read all Pose Topics

for k = 1 : length(theFiles)
    run_bag = rosbag(theFiles(k).name);
    runs_poseTopics = select(run_bag, 'Topic','/umdwarty_lidar/pose');
    runs_pose_bags(k) = runs_poseTopics;
end