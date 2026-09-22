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
s = struct("launch_file", launch_file, "launch_args", struct("rtabmap_viz", "true", "camera", "true", "lidar3d", "true", "slam2d", "true", "icp_odometry", "true"));
options = weboptions("MediaType", "application/json", "Timeout", 1200);
response = webwrite(uri, s, options)

% webwrite decodes an application/json reply into a struct; when the reply
% arrives as text, decode it here. The reply is
% {"experiment_id": N, "trial_ids": [M], "status_url": "..."}.
if ischar(response) || isstring(response)
    response = jsondecode(response);
end

experiment_id = response.experiment_id