# Script to define data structures and functions to manipulate them
# Author: Sandeep Damera
# Date: 02/13/2024

# Define a struct to hold the sensor design data

# Indices for the sensor choices

N_LIDARS = 4;
N_RGB_CAMERAS = 2;
N_RGB_DEPTH_CAMERAS = 3;
N_LASERS = 4;
N_SENSORS = N_LASERS + N_LIDARS + N_RGB_CAMERAS + N_RGB_DEPTH_CAMERAS
CARDINALITY = 6;
H_PLATFORM = 0.5; # Height of the Sensor platform on the robot.
# Custom data structures to hold the sensor design data

"""
    lidar

A struct representing a lidar sensor.

# Fields
- `model::String`: The model name of the lidar.
- `position`: The position of the lidar.
- `orientation`: The orientation of the lidar.
- `update_rate::Float64`: The update rate of the lidar.
- `h_fov::Float64`: The horizontal field of view of the lidar.
- `v_fov::Float64`: The vertical field of view of the lidar.
- `channels::Int32`: The number of channels of the lidar.
- `samples::Int32`: The number of samples per scan.
- `max_range::Float64`: The maximum range of the lidar.
- `cost::Float64`: The cost of the lidar.
- `power::Float64`: The power consumption of the lidar.
"""
mutable struct lidar
    model::String
    position
    orientation
    update_rate::Real
    h_fov::Real
    v_fov::Real
    channels::Real
    samples::Real
    max_range::Real
    cost::Real
    power::Real
end


mutable struct laser
    model::String
    position
    orientation
    update_rate::Real
    h_fov::Real
    v_fov::Real
    min_range::Real
    max_range::Real
    cost::Real
    power::Real
end

"""
    depth_camera

A struct representing a depth camera sensor.

# Fields
- `model::String`: The model name of the depth camera.
- `position`: The position of the depth camera.
- `orientation`: The orientation of the depth camera.
- `width::Int32`: The width of the depth camera's field of view.
- `height::Int32`: The height of the depth camera's field of view.
- `update_rate::Float64`: The update rate of the depth camera.
- `h_fov::Float64`: The horizontal field of view of the depth camera.
- `v_fov::Float64`: The vertical field of view of the depth camera.
- `max_range::Float64`: The maximum range of the depth camera.
- `cost::Float64`: The cost of the depth camera.
- `power::Float64`: The power consumption of the depth camera.
"""
mutable struct depth_camera
    model::String
    position
    orientation
    width::Real
    height::Real
    update_rate::Real
    h_fov::Real
    v_fov::Real
    max_range::Real
    cost::Real
    power::Real
end

"""
    camera

A struct representing a camera sensor.

# Fields
- `model::String`: The model name of the camera.
- `position`: The position of the camera.
- `orientation`: The orientation of the camera.
- `width::Int32`: The width of the camera's field of view.
- `height::Int32`: The height of the camera's field of view.
- `update_rate::Float64`: The update rate of the camera.
- `h_fov::Float64`: The horizontal field of view of the camera.
- `min_range::Float64`: The minimum range of the camera.
- `max_range::Float64`: The maximum range of the camera.
- `cost::Float64`: The cost of the camera.
- `power::Float64`: The power consumption of the camera.
"""
mutable struct camera
    model::String
    position
    orientation
    width::Real
    height::Real
    update_rate::Real
    h_fov::Real
    min_range::Real
    max_range::Real
    cost::Real
    power::Real
    # v_fov depends on lens. Inferred from the FOV calculator for tyi[pical FLIR camera
    # https://flir.custhelp.com/app/utils/fl_fovCalc/pn/29440-200/ret_url/%252Fapp%252Ffl_download_datasheets%252Fid%252F1068
    # Model 29440-200; FLIR A6700 (f/2.5, 1-5µm, 60Hz)
    # V_fov ≈ arctan(range/vfov) (in m)
    # default   v_fov_camera = 1.273
end

#----------------------------------------------
# Design struct to hold the sensor design data
#----------------------------------------------

design_id = Vector{Bool}(undef, N_SENSORS);


#----------------------------------------------

# Testing the data structures
#----------------------------------------------

a1 = lidar("vlp16", [0.0 0.0 0.0], [0.0 0.0 0.0], 15, 2 * π, 0.526, 16, 1875, 100.0, 10000, 80);# VLP-16-A
a2 = lidar("vlp16", [0.0 0.0 0.0], [0.0 0.0 0.0], 20, 2 * π, 0.526, 16, 1875, 100.0, 12000, 80);# VLP-16-B
a3 = lidar("hdl32e", [0.0 0.0 0.0], [0.0 0.0 0.0], 15, 2 * π, 0.526, 32, 2187, 120.0, 15000, 100);# VLP-32E-A
a4 = lidar("hdl32e", [0.0 0.0 0.0], [0.0 0.0 0.0], 20, 2 * π, 0.526, 32, 2187, 120.0, 16000, 100);# VLP-32E-B


b1 = laser("lms1xx", [0.0 0.0 0.0], [0.0 0.0 -1.57], 25, 4.71, 1.57, 0.1, 20.0, 1000, 30);# 111-a2
b2 = laser("lms1xx", [0.0 0.0 0.0], [0.0 0.0 -1.57], 50, 4.71, 1.57, 0.1, 20.0, 1500, 30);# 111-b1
b3 = laser("lms1xx", [0.0 0.0 0.0], [0.0 0.0 -1.57], 25, 4.71, 1.57, 0.1, 50.0, 1500, 50);# 151-a2
b4 = laser("lms1xx", [0.0 0.0 0.0], [0.0 0.0 -1.57], 50, 4.71, 1.57, 0.1, 50.0, 2000, 50);# 151-b2

c1 = depth_camera("d415", [0.0 0.0 0.0], [0.0 0.0 0.0], 540, 360, 60, 1.1345, 0.6981, 6.0, 2000, 8); # d415
c2 = depth_camera("d435", [0.0 0.0 0.0], [0.0 0.0 0.0], 1280, 720, 30, 1.5184, 1.0122, 6.0, 2500, 8); # d435
c3 = depth_camera("d455", [0.0 0.0 0.0], [0.0 0.0 0.0], 1920, 1080, 15, 1.501, 0.9948, 6.0, 3000, 10);# d455

d1 = camera("blackfly", [0.0 0.0 0.0], [0.0 0.0 0.0], 720, 540, 30, 1.047, 0.5, 50.0, 1500, 3); # blackfly-A
d2 = camera("blackfly", [0.0 0.0 0.0], [0.0 0.0 0.0], 1540, 1080, 15, 1.047, 0.5, 60.0, 3000, 6);# blackfly-B
# v_fov depends on lens. Inferred from the FOV calculator for tyi[pical FLIR camera
# https://flir.custhelp.com/app/utils/fl_fovCalc/pn/29440-200/ret_url/%252Fapp%252Ffl_download_datasheets%252Fid%252F1068
# Model 29440-200; FLIR A6700 (f/2.5, 1-5µm, 60Hz)
# V_fov ≈ arctan(range/vfov) (in m)
# default   v_fov_camera = 1.273

#----------------------------------------------
# Datastructure to map the sensor design data
sensors = [a1, a2, a3, a4, b1, b2, b3, b4, c1, c2, c3, d1, d2];



############################################

# Some helper functions

function list_spec(sensor)
    for i ∈ fieldnames(typeof(sensor))
        println(i, " : ", getfield(sensor, i))
    end
end



#= using HTTP



############################################################################################
# Define the endpoint URL
url = "your_webapp_url"

# Make a GET request to the endpoint
response = HTTP.get(url)

# Check if the request was successful
if response.status == 200
    # Extract the data from the response
    data = JSON.parse(response.body)

    # Print the data
    println(data)
else
    # Print an error message
    println("Error retrieving data: ", response.status)
end =#