check_uri = matlab.net.URI("http://127.0.0.1:5000/experiments/check");
get_uri = matlab.net.URI("http://127.0.0.1:5000/experiments/observe");
%get = matlab.net.http.RequestMethod.GET;
%post = matlab.net.http.RequestMethod.POST;
s.topics = ["stamped_linear_vel", "stamped_angular_vel"];
options = weboptions("MediaType", "application/json", "Timeout", 1200);


while 1  % app loop
    while 1  % wait loop
        check = webwrite(check_uri, struct([]), options);
        if check.experiment_running
            break
        end
        disp("No PERFECT experiment running.");
        disp("Waiting 5 seconds and trying again...");
        pause(5);
    end
    disp("There is a PERFECT experiment running! Getting data now...")

    % initialize for new experiment
    L = 901;
    l = 0;
    T = zeros([2 length(s.topics)]);  % time, x-axis
    C = zeros([2 length(s.topics)]);  % channels, y-axis
    p = plot(T, C);
    xlim([0 1]);
    ylim([-1 3]);
    xlabel("Time (s)");
    legend("Linear vel", "Angular vel")
    p(1).XDataSource = "T(:, 1)";
    p(2).XDataSource = "T(:, 2)";
    p(1).YDataSource = "C(:, 1)";
    p(2).YDataSource = "C(:, 2)";
    t0 = 0;

    while 1  % experiment loop
        response = webwrite(get_uri, s, options);
        c = response.result(:, 2);
        t = response.result(:, 1);
        if l == 0
            t0 = min(t);
        end
        t = t - t0;
        if l >= L
            T(1, :) = t;
            C(1, :) = c;
            T = circshift(T,-1);
            C = circshift(C,-1);
        else
            l = l+1;
            T(l, :) = t;
            C(l, :) = c;
        end
        xlim([T(1) T(l)+1])
        ylim([min(C, [], "all")-1 max(C, [], "all")+1])
        refreshdata
        drawnow
        pause(.2);
        check = webwrite(check_uri, struct([]), options);
        if ~check.experiment_running
            disp("Experiment has ended.")
            break
        end
    end  % experiment loop
    disp("Waiting 10 seconds before next experiment. The plot will reset!")
    pause(10)
end  % app loop