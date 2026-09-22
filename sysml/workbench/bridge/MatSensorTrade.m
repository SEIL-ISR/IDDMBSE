function mat_fun_out = MatSensorTrade(Amod, Arate, Ahfov, Avfov, Ah, Av, Bh, Bv, Bhfov, Brate, Bmax, Cmax, Crate, Dmod, Drate)

Amodels = ["d435" "d455" "d415"];
Amod_keys = [1 2 3];
Amod_dict= dictionary(Amod_keys, Amodels)

Dmodels = ["vlp16" "hdl32e"];
Dmod_keys = [1 2];
Dmod_dict= dictionary(Amod_keys, Amodels)


Amodel_tag= Amodels(Amod);

Dmodel_tag = Dmodels(Dmod);



% rgbd_tags = [Amodel_tag Ah Av Arate Ahfov Avfov]
% rgbd_keys = ["model" "width" "height" "update_rate" "h_fov" "v_fov"]

rgbdepth_dict = struct("model", Amodel_tag, "width", Ah, "height", Av, "update_rate", Arate, "h_fov", Ahfov, "v_fov", Avfov)

%rgbdepth_dict = dictionary(rgbd_keys, rgbd_tags)

% cam_tags = [Bh Bv Brate Bhfov Bmax]
% cam_keys = 

cam_dict = struct("width", Bh, "height", Bv, "update_rate", Brate, "h_fov", Bhfov, "max_range", Bmax)

% las2d_tags = [Crate Cmax]
% las2d_keys = ["update_rate" "max_range"]
las2d_dict = struct("update_rate", Crate, "max_range", Cmax)

% lidar_tags = [Dmodel_tag Drate]
% lidar_keys = ["model" "update_rate"]
lidar_dict = struct("model", Dmodel_tag, "update_rate", Drate)


server = string(getenv("PERFECT_SERVER_URL"));
if strlength(server) == 0
    server = "http://127.0.0.1:5000";
end
uri = matlab.net.URI(server + "/api/v1/run");
method = matlab.net.http.RequestMethod.POST;

ws = string(getenv("AUTO_STACK_WS"));
if strlength(ws) == 0
    ws = "~/auto_stack_ws";
end
launch_file = ws + "/src/hardware_launch/launch/navigation_rosbridge.launch";
s = struct("launch_file", launch_file, "sensor_update", struct("laser_3d", lidar_dict, "camera", cam_dict, "laser_2d", las2d_dict,"depth_camera",rgbdepth_dict))

options = weboptions("MediaType", "application/json", "Timeout", 2000);

response = webwrite(uri, s, options)

% webwrite decodes an application/json reply into a struct; when the reply
% arrives as text, decode it here. The reply is
% {"experiment_id": N, "trial_ids": [M], "status_url": "..."}.
if ischar(response) || isstring(response)
    response = jsondecode(response);
end

mat_fun_out = response.experiment_id;



end
