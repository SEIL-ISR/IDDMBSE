function mat_fun_out = DemoMatFun(parA1, parA2, parB1, parB2)


% Uncomment the section below to route the instance data to ROS

% dict = struct("parA1", parA1, "parA2", parA2, "parB1", parB1, "parB2", parB2)
% server = string(getenv("PERFECT_SERVER_URL"));
% if strlength(server) == 0
%     server = "http://127.0.0.1:5000";
% end
% uri = matlab.net.URI(server + "/run");
% method = matlab.net.http.RequestMethod.POST;
% 
% ws = string(getenv("AUTO_STACK_WS"));
% if strlength(ws) == 0
%     ws = "~/auto_stack_ws";
% end
% launch_file = ws + "/src/hardware_launch/launch/navigation_rosbridge.launch";
% s = struct("launch_file", launch_file, "sensor_update", struct("data", dict))
% 
% options = weboptions("MediaType", "application/json", "Timeout", 2000);
% 
% response = webwrite(uri, s, options)




mat_fun_out = 1parA1+parA2+parB1+parB2

end
