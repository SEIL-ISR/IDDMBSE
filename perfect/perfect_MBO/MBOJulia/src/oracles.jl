#----------------------------------------------
# Sensor Cost Oracles- Single Dispatch

function sensor_cost_oracle(sensor::Union{lidar,laser,depth_camera,camera})
    return sensor.cost
end
#----------------------------------------------
# Sensor RAM Oracles- Multiple Dispatch

function sensor_ram_oracle(sensor::lidar)
    # nb_lidar = Int8--> 1 Byte
    ram = sensor.update_rate * sensor.samples * sensor.channels / 1000_000 # in MBytes (8 bits to a byte)
    return ram
end

function sensor_ram_oracle(sensor::laser)
    n_samples_laser = 720
    # sample rate set in urdf xacro file
    # https://github.com/proboscisjoe/roslab/blob/master/src/lms1xx/urdf/sick_lms1xx.urdf.xacro
    # Each Laser point scan has range and intensity data, so we multiply by 2. Each data point is 8 bit Int8.
    ram = sensor.update_rate * n_samples_laser * 2 / 1000_000 # in MBytes (8 bits to a byte))		
    return ram
end

function sensor_ram_oracle(sensor::depth_camera)
    nb_depthcamera = 8 # no of bits for depth image pixel- Int16
    ram = sensor.update_rate * sensor.width * sensor.height * nb_depthcamera / (8 * 1000_000) # in MBytes (8 bits to a byte)
    return ram
end

function sensor_ram_oracle(sensor::camera)
    nb_camera = 16 # no of bits for image pixel- Int8
    ram = sensor.update_rate * sensor.width * sensor.height * nb_camera / (8 * 1000_000) # in MBytes (8 bits to a byte)
    return ram
end

#----------------------------------------------
# Sensor Power Oracles- Single Dispatch
function sensor_power_oracle(sensor::Union{lidar,laser,depth_camera,camera})
    return sensor.power
end
#----------------------------------------------

# Sensor Coverage Oracles- Multiple Dispatch

function sensor_coverage_oracle(sensor::lidar)
    # sen_cov = 4 * π / 3 * (sensor.max_range)^3 * (cos(sensor.v_fov / 2))^2 * sin(sensor.v_fov / 2)
    # considering ground plane,
    sen_cov = 2 * (π / 3) * (sensor.h_fov / (2 * π)) * (sensor.max_range)^3 * (cos(sensor.v_fov / 2))^2 * sin(sensor.v_fov / 2) +
              (π / 3) * (sensor.max_range)^2 * H_PLATFORM * (cos(sensor.v_fov / 2))^2 -
              (π / 3) * H_PLATFORM^3 * (cot(sensor.v_fov / 2))^2
end

function sensor_coverage_oracle(sensor::laser)
    #h_box = 0.5 # Height of the Sensor platform on the robot. 
    # Laser only works on a 2D plane, so we only consider the sub-surface volume
    sen_cov = (sensor.h_fov / 2) * (sensor.max_range)^2 * H_PLATFORM
    return sen_cov
end

function sensor_coverage_oracle(sensor::depth_camera)
    # tan function misbehaves at exactly θ==π/2, so we need to check for that
    @assert sensor.v_fov < π / 2
    @assert sensor.h_fov < π / 2

    # sen_cov = (π / 3) * (sensor.max_range)^3 * tan(sensor.h_fov / 2) * tan(sensor.v_fov / 2)

    # considering ground plane,
    sen_cov = (π / 6) * (sensor.max_range) * tan(sensor.h_fov / 2) * ((sensor.max_range^2) * tan(sensor.v_fov / 2) + 2 * H_PLATFORM * sensor.max_range) - (H_PLATFORM^2) * cot(sensor.v_fov / 2) # in m^3
    return sen_cov
end

function sensor_coverage_oracle(sensor::camera)
    # tan function misbehaves at exactly θ==π/2, so we need to check for that
    @assert sensor.h_fov < π / 2

    # v_fov depends on lens. Inferred from the FOV calculator for tyi[pical FLIR camera
    # https://flir.custhelp.com/app/utils/fl_fovCalc/pn/29440-200/ret_url/%252Fapp%252Ffl_download_datasheets%252Fid%252F1068
    # Model 29440-200; FLIR A6700 (f/2.5, 1-5µm, 60Hz)
    # V_fov ≈ arctan(range/vfov) (in m)

    v_fov_camera = 1.273
    # sen_cov = (π / 3) * (sensor.max_range)^3 * tan(sensor.h_fov / 2) * tan(v_fov_camera / 2)

    # considering ground plane,
    sen_cov = (π / 6) * (sensor.max_range) * tan(sensor.h_fov / 2) * ((sensor.max_range^2) * tan(v_fov_camera / 2) + 2 * H_PLATFORM * sensor.max_range) - (H_PLATFORM^2) * cot(v_fov_camera / 2) # in m^3
    return sen_cov
end

#----------------------------------------------
# Oracles to estimate the cost, ram, power and coverage of the sensor suite design_ids
#----------------------------------------------

"""
	cost_oracle(design_id::Vector{Bool})

Calculate the total cost of the selected sensors in the design.

# Arguments
- `design_id::Vector{Bool}`: A boolean vector representing the selection of sensors in the design.

# Returns
- The total cost of the selected sensors.
"""
function cost_oracle(design_id::Vector{Bool})
    cost = 0
    for i in 1:length(design_id)
        if design_id[i]
            cost += sensor_cost_oracle(sensors[i])
        end
    end
    return cost
end

"""
	ram_oracle(design_id::Vector{Bool},T_storage::Float64)

Calculate the total RAM usage of the selected sensors in the design.

# Arguments
- `design_id::Vector{Bool}`: A boolean vector representing the selection of sensors in the design.
- `T_storage::Float64`: The storage time.

# Returns
- The total RAM usage of the selected sensors.
"""
function ram_oracle(design_id::Vector{Bool}, T_storage::Float64)
    ram = 0
    for i in 1:length(design_id)
        if design_id[i]
            ram = ram + T_storage * sensors[i].update_rate * sensor_ram_oracle(sensors[i]) # in MB, for T_storage in seconds
        end
    end
    return ram
end

"""
	power_oracle(design_id::Vector{Bool})

Calculate the total power consumption of the selected sensors in the design.

# Arguments
- `design_id::Vector{Bool}`: A boolean vector representing the selection of sensors in the design.

# Returns
- The total power consumption of the selected sensors.
"""
function power_oracle(design_id::Vector{Bool})
    passive_power = 0
    storage_power = 0
    for i in 1:length(design_id)
        if design_id[i]
            passive_power += sensor_power_oracle(sensors[i])
            storage_power += sensor_ram_oracle(sensors[i])
        end
    end
    power = passive_power + (0.77 * 2.67 * storage_power / 1000_000)
    return power
end

"""
	coverage_oracle(design_id::Vector{Bool})

Calculate the total coverage of the selected sensors in the design.

# Arguments
- `design_id::Vector{Bool}`: A boolean vector representing the selection of sensors in the design.

# Returns
- The total coverage of the selected sensors.
"""
function coverage_oracle(design_id::Vector{Bool})
    coverage = 0
    for i in 1:length(design_id)
        if design_id[i]
            coverage += sensor_coverage_oracle(sensors[i])
        end
    end
    return coverage
end


"""
    effective_coverage_oracle(design_id::Vector{Bool})

Calculate the effective coverage of a set of sensors.

# Arguments
- `design_id::Vector{Bool}`: A boolean vector where each element represents whether a sensor is included in the set.

# Returns
- The effective coverage of the set of sensors.

# Notes
- The function assumes that the `sensors` array is defined in the global scope.
- The function modifies the `sensors` array, which could lead to unexpected side effects if the array is used elsewhere.
"""
function effective_coverage_oracle(design_id::Vector{Bool})

    eff_coverage = 0

    for i in 1:length(design_id)
        # First sensor in the set. 
        if eff_coverage == 0 && design_id[i]
            eff_coverage = sensor_coverage_oracle(sensors[i])
        end

        if eff_coverage != 0
            # Flag the existing types of sensors in the set so far
            lid_flag, las_flag, dep_flag, cam_flag = false, false, false, false
			for k = 1:i
                lid_flag = typeof(sensors[k]) == lidar
                las_flag = typeof(sensors[k]) == laser
                dep_flag = typeof(sensors[k]) == depth_camera
                cam_flag = typeof(sensors[k]) == camera                
            end

            # Now compute the addition of the ith sensor based on its type and availability of the same type in the set
            # basically have 2 branches per sensor type

            # Since the design enums are ordered, resolve ordering the unions from the lidar-->lasers-->depth_cameras-->cameras
            # This way, we can resolve the type of the sensor in the set and the type of the sensor being added to the set

            # if design_id[i] && typeof(sensors[i]) == lidar && !lid_flag
            # this case shouldn't happen since the first sensor in the set is a lidar. if it's not then there are no lidars.

            # adding an additional lidar to the set containing a lidar(s)
            if design_id[i] && typeof(sensors[i]) == lidar && lid_flag
                rmax, vfov = -Inf, -Inf
				for j = 1:i
                    if typeof(sensors[j]) == lidar
                        rmax = max(sensors[i].max_range, sensors[j].max_range)
                        vfov = max(sensors[i].v_fov, sensors[j].v_fov)
                        
                    end
                end
                sensors[i].max_range = rmax
                sensors[i].v_fov = vfov
                eff_coverage = sensor_coverage_oracle(sensors[i])
            end

            #----------------------------------------------
            # adding the first laser to the set without existing lidar or laser
            if design_id[i] && typeof(sensors[i]) == laser && !lid_flag && !las_flag
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i])
            end

            # adding an additional laser to the set containing a lidar but no laser
            if design_id[i] && typeof(sensors[i]) == laser && lid_flag && !las_flag

                local_copy = sensors[1]
                local_copy.max_range = sensors[i].max_range # cone to the max range of the laser
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i]) - (3 / 8) * sensor_coverage_oracle(local_copy)
            end

            # adding an additional laser to the set containing a laser(s) but no lidar
            if design_id[i] && typeof(sensors[i]) == laser && las_flag && !lid_flag
                rmax, hfov = -Inf, -Inf
				for j = 1:i
                    if typeof(sensors[j]) == laser
                        rmax = max(sensors[i].max_range, sensors[j].max_range)
                        hfov = max(sensors[i].h_fov, sensors[j].h_fov)
                        
                    end
                end
                sensors[i].max_range = rmax
                sensors[i].h_fov = hfov
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i])
            end

            # adding an additional laser to the set containing a laser(s) and lidar(s)
            if design_id[i] && typeof(sensors[i]) == laser && las_flag && lid_flag
                # maximal Laser
                rmax, hfov, vfov = -Inf, -Inf, -Inf
				for j = 1:i
                    if typeof(sensors[j]) == laser
                        rmax = max(sensors[i].max_range, sensors[j].max_range)
                        hfov = max(sensors[i].h_fov, sensors[j].h_fov)
                        vfov = max(sensors[i].v_fov, sensors[j].v_fov)
                        
                    end
                end
                sensors[i].max_range = rmax
                sensors[i].h_fov = hfov
                sensors[i].v_fov = vfov
                # Fuse Laser with existing Lidar
                local_copy = sensors[1]
                local_copy.max_range = sensors[i].max_range # cone to the max range of the laser
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i]) - (3 / 8) * sensor_coverage_oracle(local_copy)
            end

            #----------------------------------------------
            # adding the first depth_camera to the set without existing lidar, laser or depth_camera
            if design_id[i] && typeof(sensors[i]) == depth_camera && !lid_flag && !las_flag && !dep_flag
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i])
            end

            # adding an additional depth_camera to the set containing a lidar but no depth_camera or laser
            if design_id[i] && typeof(sensors[i]) == depth_camera && lid_flag && !las_flag && !dep_flag
                local_copy = sensors[1] # Lidar boilerplate
                local_copy.max_range = sensors[i].max_range # cone to the max range of the depth_camera
                local_copy.h_fov = sensors[i].h_fov # cone to the h_fov of the depth_camera
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i]) - sensor_coverage_oracle(local_copy)
            end

            # adding an additional depth_camera to the set containing a laser but no depth_camera or lidar
            if design_id[i] && typeof(sensors[i]) == depth_camera && las_flag && !lid_flag && !dep_flag
                eff_coverage = eff_coverage + 0.5 * sensor_coverage_oracle(sensors[i])
            end

            # adding an additional depth_camera to the set containing a depth_camera(s) but no lidar or laser
            if design_id[i] && typeof(sensors[i]) == depth_camera && dep_flag && !lid_flag && !las_flag
                rmax, hfov, vfov = -Inf, -Inf, -Inf
				for j = 1:i
                    if typeof(sensors[j]) == depth_camera
                        rmax = max(sensors[i].max_range, sensors[j].max_range)
                        hfov = max(sensors[i].h_fov, sensors[j].h_fov)
                        vfov = max(sensors[i].v_fov, sensors[j].v_fov)
                        
                    end
                end
                sensors[i].max_range = rmax
                sensors[i].h_fov = hfov
                sensors[i].v_fov = vfov
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i])
            end

            # adding an additional depth_camera to the set containing a depth_camera(s) and lidar(s)
            if design_id[i] && typeof(sensors[i]) == depth_camera && dep_flag && lid_flag && !las_flag

                # maximal depth camera				
                rmax, hfov, vfov = -Inf, -Inf, -Inf
				for j = 1:i
                    if typeof(sensors[j]) == depth_camera
                        rmax = max(sensors[i].max_range, sensors[j].max_range)
                        hfov = max(sensors[i].h_fov, sensors[j].h_fov)
                        vfov = max(sensors[i].v_fov, sensors[j].v_fov)
                        
                    end
                end
                sensors[i].max_range = rmax
                sensors[i].h_fov = hfov
                sensors[i].v_fov = vfov

                # Fuse Depth Camera with existing Lidar
                local_copy = sensors[1] # Lidar boilerplate
                local_copy.max_range = sensors[i].max_range # cone to the max range of the depth_camera
                local_copy.h_fov = sensors[i].h_fov # cone to the h_fov of the depth_camera
                local_copy.v_fov = sensors[i].v_fov # cone to the v_fov of the depth_camera

                eff_coverage = eff_coverage + (0.5 * sensor_coverage_oracle(sensors[i])) - (0.5 * sensor_coverage_oracle(local_copy))
            end

            #----------------------------------------------
            # adding the first camera to the set without existing lidar, laser, depth_camera or camera
            if design_id[i] && typeof(sensors[i]) == camera && !lid_flag && !las_flag && !dep_flag && !cam_flag
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i])
            end

            # adding an additional camera to the set containing a lidar but no camera, depth_camera or laser
            if design_id[i] && typeof(sensors[i]) == camera && lid_flag && !las_flag && !dep_flag && !cam_flag
                local_copy = sensors[1] # Lidar boilerplate
                local_copy.max_range = sensors[i].max_range # cone to the max range of the camera
                local_copy.h_fov = sensors[i].h_fov # cone to the h_fov of the camera
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i]) - sensor_coverage_oracle(local_copy)
            end

            # adding an additional camera to the set containing a laser but no camera or depth_camera or lidar
            if design_id[i] && typeof(sensors[i]) == camera && las_flag && !lid_flag && !dep_flag && !cam_flag
                eff_coverage = eff_coverage + 0.5 * sensor_coverage_oracle(sensors[i])
            end

            # adding an additional camera to the set containing a camera(s) but no lidar or laser or depth_camera
            if design_id[i] && typeof(sensors[i]) == camera && !dep_flag && !lid_flag && !las_flag && cam_flag
                rmax, hfov, vfov = -Inf, -Inf, -Inf
				for j = 1:i
                    if typeof(sensors[j]) == camera
                        rmax = max(sensors[i].max_range, sensors[j].max_range)
                        hfov = max(sensors[i].h_fov, sensors[j].h_fov)
                        #vfov = max(sensors[i].v_fov, sensors[j].v_fov)
                        
                    end
                end
                sensors[i].max_range = rmax
                sensors[i].h_fov = hfov
                #sensors[i].v_fov = vfov
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i])
            end

            # adding an additional camera to the set containing a camera(s) and lidar(s)
            if design_id[i] && typeof(sensors[i]) == camera && !dep_flag && lid_flag && !las_flag && cam_flag

                # maximal camera				
                rmax, hfov, vfov = -Inf, -Inf, -Inf
				for j = 1:i
                    if typeof(sensors[j]) == camera
                        rmax = max(sensors[i].max_range, sensors[j].max_range)
                        hfov = max(sensors[i].h_fov, sensors[j].h_fov)
                        vfov = max(sensors[i].v_fov, sensors[j].v_fov)
                        
                    end
                end
                sensors[i].max_range = rmax
                sensors[i].h_fov = hfov
                sensors[i].v_fov = vfov

                # Fuse Camera with existing Lidar
                local_copy = sensors[1] # Lidar boilerplate
                local_copy.max_range = sensors[i].max_range # cone to the max range of the camera
                local_copy.h_fov = sensors[i].h_fov # cone to the h_fov of the camera
                local_copy.v_fov = sensors[i].v_fov # cone to the v_fov of the camera

                eff_coverage = eff_coverage + (0.5 * sensor_coverage_oracle(sensors[i])) - (0.5 * sensor_coverage_oracle(local_copy))
            end

            # adding an additional camera to the set containing a depth camera(s) but no lidar or laser or camera
            if design_id[i] && typeof(sensors[i]) == camera && dep_flag && !lid_flag && !las_flag && !cam_flag
                rmax, hfov, vfov = -Inf, -Inf, -Inf
				for j = 1:i
                    if typeof(sensors[j]) == depth_camera
                        rmax = max(sensors[i].max_range, sensors[j].max_range)
                        hfov = max(sensors[i].h_fov, sensors[j].h_fov)
                        vfov = max(sensors[i].v_fov, sensors[j].v_fov)
                        
                    end
                end
                sensors[i].max_range = rmax
                sensors[i].h_fov = hfov
                sensors[i].v_fov = vfov
                eff_coverage = eff_coverage + sensor_coverage_oracle(sensors[i])
            end

            # adding an additional camera to the set containing a depth_camera(s) and lidar(s) but no camera
            if design_id[i] && typeof(sensors[i]) == camera && dep_flag && lid_flag && !las_flag && !cam_flag

                # maximal camera				
                rmax, hfov, vfov = -Inf, -Inf, -Inf
				for j = 1:i
                    if typeof(sensors[j]) == depth_camera
                        rmax = max(sensors[i].max_range, sensors[j].max_range)
                        hfov = max(sensors[i].h_fov, sensors[j].h_fov)
                        vfov = max(sensors[i].v_fov, sensors[j].v_fov)
                        
                    end
                end
                sensors[i].max_range = rmax
                sensors[i].h_fov = hfov
                sensors[i].v_fov = vfov

                # Fuse Camera with existing Lidar
                local_copy = sensors[1] # Lidar boilerplate
                local_copy.max_range = sensors[i].max_range # cone to the max range of the camera
                local_copy.h_fov = sensors[i].h_fov # cone to the h_fov of the camera
                local_copy.v_fov = sensors[i].v_fov # cone to the v_fov of the camera

                eff_coverage = eff_coverage + (0.5 * sensor_coverage_oracle(sensors[i])) - (0.5 * sensor_coverage_oracle(local_copy))
            end
        end
    end

    return eff_coverage
end

#----------------------------------------------
#----------------------------------------------
#----------------------------------------------


#= function effective_coverage_oracle2(design_id::Vector{Bool})
    eff_coverage = sum(design_id)
    lid_flag, las_flag, dep_flag, cam_flag = false, false, false, false

	for i ∈ eachindex(design_id)
        for k = 1:i
            lid_flag = typeof(sensors[k]) == lidar
            las_flag = typeof(sensors[k]) == laser
            dep_flag = typeof(sensors[k]) == depth_camera
            cam_flag = typeof(sensors[k]) == camera            
        end
	end

    return eff_coverage
end
 =#


#= sd = cost_oracle(design_id)
asd = coverage_oracle(design_id)

sl = effective_coverage_oracle(design_id)

sl2 = effective_coverage_oracle2(design_id) =#