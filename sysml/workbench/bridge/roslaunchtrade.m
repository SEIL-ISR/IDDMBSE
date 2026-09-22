function mat_out= roslaunchtrade(envkey, lpkey, gpkey)

env_names = ["inspection" "playpen" "orchard" "agriculture"];
env_keys = [1 2 3 4];
env_dict= dictionary(env_keys, env_names)

lp_names = ["dwa_local_planner/DWAPlannerROS" "teb_local_planner/TebLocalPlannerROS" "base_local_planner/TrajectoryPlannerROS"];
lp_keys = [1 2 3];
lp_dict= dictionary(lp_keys, lp_names)

gp_names = ["navfn/NavfnROS" "global_planner/GlobalPlanner"];
gp_keys = [1 2];
gp_dict= dictionary(gp_keys, gp_names)

server = string(getenv("PERFECT_SERVER_URL"));
if strlength(server) == 0
    server = "http://127.0.0.1:5000";
end
uri = matlab.net.URI(server + "/run");
method = matlab.net.http.RequestMethod.POST;
lp_dict(lpkey)
gp_dict(gpkey)
env_dict(envkey)
ws = string(getenv("AUTO_STACK_WS"));
if strlength(ws) == 0
    ws = "~/auto_stack_ws";
end
launch_file = ws + "/src/hardware_launch/launch/navigation_rosbridge.launch";
s = struct("launch_file", launch_file, "launch_args", struct("base_global_planner", gp_dict(gpkey), "base_local_planner", lp_dict(lpkey), "domain", env_dict(envkey)));
options = weboptions("MediaType", "application/json", "Timeout", 2000);

response = webwrite(uri, s, options)


mat_out = 1.0 


end